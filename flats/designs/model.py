"""The design catalog.

A screen that answers for one building has a one-building shelf life. The
catalog is a first-class entity: results are keyed ``(lot, design, run)`` from
the start, so adding design #11 is a re-run of two stages rather than a schema
migration.

**The cost asymmetry is what makes this affordable.** Design-*independent* facts
— buildable envelope, the max-depth-per-width fit frontier, slope, sewer,
frontage class, acquisition economics — are computed once per lot and shared
across every design. Because the frontier stores the deepest rectangle that fits
at each width, asking whether a new W x D pod fits is a table lookup, not a
re-run. Only the site plan and set-access stages genuinely fan out.

**Designs are immutable once run.** A design is identified by ``(id, version)``,
and changing dimensions means bumping the version, never editing in place. Two
runs of the same design id at the same version must be comparable; if the
footprint could drift underneath, they would not be. ``archived`` designs stay
loadable so historical results remain interpretable.

Nothing here decides GREEN/REVIEW/RED. This module describes buildings; the fit
and site-plan stages decide whether one lands on a lot.
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATALOG_ROOT = Path(__file__).resolve().parents[1] / "config" / "pods"


class Typology(str, enum.Enum):
    """Which site-plan generator lays this design out.

    A typology is not decoration — it selects real geometry code. Adding one
    means writing that generator, so the enum is closed and an unknown value
    fails at load rather than producing an unlaid-out plan.
    """

    #: Attached townhomes at the front, one side driveway to a rear parking
    #: court, forward in-and-out. Gresham 7.0431 governs.
    townhome_rear_court = "townhome_rear_court"


class ParkingConfig(str, enum.Enum):
    rear_court = "rear_court"
    side_drive = "side_drive"
    tuck_under = "tuck_under"
    #: No off-street parking provided — legal where the minimum is zero.
    street_only = "street_only"


class Delivery(str, enum.Enum):
    panelized = "panelized"
    modular = "modular"
    site_built = "site_built"


class DesignStatus(str, enum.Enum):
    #: Evaluated by new runs.
    active = "active"
    #: Not evaluated by new runs, but still loadable so old results read.
    archived = "archived"


class Orientation(str, enum.Enum):
    """How the footprint sits relative to the front lot line."""

    #: Long dimension parallel to the street.
    width_facing = "width_facing"
    #: Long dimension perpendicular to the street.
    depth_facing = "depth_facing"


class Footprint(BaseModel):
    model_config = ConfigDict(frozen=True)

    #: Dimension parallel to the front lot line before any rotation.
    width_ft: float = Field(gt=0)
    depth_ft: float = Field(gt=0)

    @property
    def area_sqft(self) -> float:
        return self.width_ft * self.depth_ft


class Parking(BaseModel):
    model_config = ConfigDict(frozen=True)

    #: Marketability target, not a legal floor. The legal minimum comes from the
    #: rule set and may be lower — Gresham LDR-5 requires zero.
    stalls_per_unit: float = Field(ge=0)
    config: ParkingConfig


class DeliverySpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: Delivery
    #: Widest single module that must reach the site. Drives the set-access
    #: stage: street width, turning radius, overhead clearance.
    module_max_width_ft: float | None = Field(default=None, gt=0)
    crane_required: bool = False
    #: Reach needed from the nearest placeable crane position.
    crane_reach_ft: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _crane_reach_needs_a_crane(self) -> DeliverySpec:
        if self.crane_reach_ft is not None and not self.crane_required:
            raise ValueError("crane_reach_ft set but crane_required is false")
        return self


class Design(BaseModel):
    """One building the screen can try to place."""

    model_config = ConfigDict(frozen=True)

    id: str
    #: Bumped on any dimensional change. Editing in place breaks run comparison.
    version: int = Field(ge=1)
    label: str
    typology: Typology
    footprint: Footprint
    units: int = Field(gt=0)
    stories: int = Field(gt=0)
    height_ft: float = Field(gt=0)
    parking: Parking
    delivery: DeliverySpec
    status: DesignStatus = DesignStatus.active
    notes: str = ""
    #: Values taken as product intent rather than from a drawing set. Surfaced
    #: so a result is never read as more precise than its inputs.
    assumptions: tuple[str, ...] = ()

    @field_validator("id")
    @classmethod
    def _id_is_a_slug(cls, v: str) -> str:
        if not v or not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError(f"design id {v!r} must be alphanumeric with - or _")
        return v

    @property
    def key(self) -> str:
        """Stable identity for result rows: ``id@version``."""
        return f"{self.id}@{self.version}"

    @property
    def ground_sqft(self) -> float:
        return self.footprint.area_sqft

    @property
    def unit_ground_sqft(self) -> float:
        return self.footprint.area_sqft / self.units

    @property
    def stalls_required(self) -> float:
        """Stalls this design wants. The zone's legal minimum is separate."""
        return self.parking.stalls_per_unit * self.units

    def oriented(
        self, *, axis_required: bool = False
    ) -> tuple[tuple[Orientation, float, float], ...]:
        """(orientation, width, depth) triples the fit stage should try.

        A square footprint yields one entry: rotating it produces the same
        rectangle, and testing it twice would double-count a lot's fit.
        ``axis_required`` is the zoning case where the building must face the
        street, which halves the orientations rather than changing them.
        """
        w, d = self.footprint.width_ft, self.footprint.depth_ft
        first = (Orientation.width_facing, w, d)
        if axis_required or w == d:
            return (first,)
        return (first, (Orientation.depth_facing, d, w))


class CatalogError(Exception):
    """One or more designs failed to load. Reports every problem at once."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("\n".join(f"- {p}" for p in problems))


class DesignCatalog:
    """Loaded designs, keyed ``id@version``."""

    def __init__(self, designs: Iterable[Design]) -> None:
        self._by_key: dict[str, Design] = {}
        for d in designs:
            if d.key in self._by_key:
                raise CatalogError([f"duplicate design {d.key} — bump version instead of editing"])
            self._by_key[d.key] = d

    def __len__(self) -> int:
        return len(self._by_key)

    def __iter__(self) -> Iterator[Design]:
        return iter(sorted(self._by_key.values(), key=lambda d: (d.id, d.version)))

    def __contains__(self, key: object) -> bool:
        return key in self._by_key

    def get(self, key: str) -> Design:
        """Look up by ``id@version``, failing loudly.

        A result row naming a design the catalog cannot produce is unreadable,
        so a miss is an error rather than None.
        """
        try:
            return self._by_key[key]
        except KeyError:
            raise KeyError(
                f"unknown design {key!r} — expected id@version, one of {sorted(self._by_key)}"
            ) from None

    def latest(self, design_id: str) -> Design:
        """Highest version of one design id."""
        matches = [d for d in self._by_key.values() if d.id == design_id]
        if not matches:
            raise KeyError(f"no design with id {design_id!r}")
        return max(matches, key=lambda d: d.version)

    def active(self) -> list[Design]:
        """Designs new runs evaluate. Archived ones stay loadable, not run."""
        return [d for d in self if d.status is DesignStatus.active]


def load_catalog(root: Path | None = None, *, strict: bool = True) -> DesignCatalog:
    """Load every ``*.yaml`` under the pods directory.

    Accumulates problems rather than failing on the first one — a rejected
    catalog should report all of its errors in a single pass.
    """
    root = root or CATALOG_ROOT
    problems: list[str] = []
    designs: list[Design] = []

    for path in sorted(root.rglob("*.yaml")):
        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(f"{path.name}: invalid YAML — {exc}")
            continue
        if not isinstance(raw, dict):
            problems.append(f"{path.name}: expected a mapping, got {type(raw).__name__}")
            continue
        raw.setdefault("id", path.stem)
        try:
            designs.append(Design(**raw))
        except Exception as exc:  # pydantic ValidationError and friends
            problems.append(f"{path.name}: {exc}")

    seen: set[str] = set()
    for d in designs:
        if d.key in seen:
            problems.append(f"duplicate design {d.key} — bump version instead of editing")
        seen.add(d.key)

    if problems and strict:
        raise CatalogError(problems)

    # Non-strict keeps the first of a duplicate pair so a partial catalog still
    # loads for inspection; strict mode has already refused it above.
    unique: dict[str, Design] = {}
    for d in designs:
        unique.setdefault(d.key, d)
    return DesignCatalog(unique.values())
