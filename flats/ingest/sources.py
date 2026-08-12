"""The data-source registry — what the screen reads, and from where.

Every county GIS endpoint is declared in ``flats/config/pipeline.yaml`` rather
than embedded in a downloader. A rotted URL becomes a config edit instead of a
code change, a jurisdiction can be switched off without touching anything that
runs, and the question "what is Gresham's zoning read from" has an answer that
does not require reading Python.

Loading validates. The checks are few and each one exists because getting it
wrong is silent:

* **One CRS.** Every dataset must arrive in the working CRS. A service that
  publishes something else declares ``native_srid`` and is reprojected on the
  way in; a mismatch that slipped through would put every lot in the wrong
  place without raising anything.
* **Attributes are not optional.** A zoning layer fetched without its fields is
  geometry nobody can zone, and a zoning dataset must name the field its codes
  live in — they are called ZONE, zonecode, DESIGNATION and ``PLANDIST.CZONE``
  across fourteen cities, and guessing is not a strategy.
* **Nothing serves nowhere.** Every dataset names the jurisdictions it covers,
  so an enabled city with no zoning source is a finding rather than a silence.

Switching a jurisdiction off leaves its rules, history and review decisions
alone. That is the whole point of the toggle: turning a city back on re-runs
that city, not the county.
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "pipeline.yaml"


class Kind(str, enum.Enum):
    """How a dataset is fetched."""

    #: ArcGIS REST layer, objectId-paginated, reprojected server-side.
    arcgis = "arcgis"
    #: Member of the Metro RLIS quarterly ZIP, pulled by HTTP range request.
    rlis_zip = "rlis_zip"
    #: USGS National Map product API — DEM tiles for slope.
    tnm_dem = "tnm_dem"


class Provides(str, enum.Enum):
    """What role a dataset plays in the screen."""

    lots = "lots"
    streets = "streets"
    zoning = "zoning"
    boundary = "boundary"
    overlay = "overlay"
    utility = "utility"
    terrain = "terrain"


class Geometry(str, enum.Enum):
    polygon = "polygon"
    polyline = "polyline"


class Defaults(BaseModel):
    """Measurement settings shared by every jurisdiction."""

    model_config = ConfigDict(frozen=True)

    street_threshold_ft: float = Field(default=40.0, gt=0)
    simplify_tolerance_ft: float = Field(default=1.0, ge=0)
    grid_resolution_ft: float = Field(default=0.5, gt=0)


class Dataset(BaseModel):
    """One fetchable source."""

    model_config = ConfigDict(frozen=True)

    key: str
    kind: Kind
    label: str
    provides: Provides
    url: str = Field(min_length=8)
    #: Jurisdiction or county paths this dataset covers. A county path covers
    #: every jurisdiction under it.
    serves: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    #: Attribute holding the zone code. Required for zoning; the name differs
    #: in every city.
    zone_field: str | None = None
    #: Member path inside the RLIS ZIP.
    member: str | None = None
    #: Server-side attribute filter, verbatim.
    where: str | None = None
    filter: str | None = None
    geometry: Geometry = Geometry.polygon
    #: CRS the service publishes in, when it is not the working CRS. Recorded
    #: so the fetch knows to ask for a reprojection.
    native_srid: int | None = None
    bbox_4326: tuple[float, float, float, float] | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _fetchable(self) -> Dataset:
        if self.kind is Kind.arcgis and not self.fields:
            raise ValueError(
                f"{self.key}: an ArcGIS layer with no fields returns geometry nobody can use"
            )
        if self.kind is Kind.rlis_zip and not self.member:
            raise ValueError(f"{self.key}: an RLIS dataset must name the member to extract")
        if self.provides is Provides.zoning and not self.zone_field:
            raise ValueError(
                f"{self.key}: a zoning dataset must name the field its zone codes live in"
            )
        if self.provides is Provides.zoning and self.fields and self.zone_field not in self.fields:
            raise ValueError(f"{self.key}: zone_field {self.zone_field!r} is not among its fields")
        if not self.serves:
            raise ValueError(f"{self.key}: a dataset that serves nothing should not be declared")
        return self

    def covers(self, layer_id: str) -> bool:
        """Does this dataset apply to a jurisdiction?

        A dataset serving ``or/multnomah`` covers every jurisdiction in the
        county, which is how the regional fallbacks reach the cities that
        publish nothing of their own.
        """
        return any(layer_id == s or layer_id.startswith(f"{s}/") for s in self.serves)


class PipelineError(Exception):
    """The source registry does not describe a runnable pipeline."""


class Pipeline(BaseModel):
    """The whole registry."""

    model_config = ConfigDict(frozen=True)

    version: int = 1
    working_srid: int
    display_srid: int
    defaults: Defaults = Defaults()
    #: Jurisdiction path → whether this run covers it.
    jurisdictions: dict[str, bool] = Field(default_factory=dict)
    datasets: dict[str, Dataset] = Field(default_factory=dict)

    def enabled(self, layer_id: str) -> bool:
        """Unknown jurisdictions are off. Coverage is claimed, never assumed."""
        return self.jurisdictions.get(layer_id, False)

    def active(self) -> tuple[str, ...]:
        return tuple(sorted(j for j, on in self.jurisdictions.items() if on))

    def for_layer(self, layer_id: str, provides: Provides | None = None) -> tuple[Dataset, ...]:
        """Datasets covering one jurisdiction, most specific first.

        A city's own zoning service outranks the regional fallback, so the
        caller can take the head of the list and be right.
        """
        found = [
            d
            for d in self.datasets.values()
            if d.covers(layer_id) and (provides is None or d.provides is provides)
        ]
        found.sort(key=lambda d: (-max(len(s) for s in d.serves if layer_id.startswith(s)), d.key))
        return tuple(found)

    def unserved(self, provides: Provides = Provides.zoning) -> tuple[str, ...]:
        """Enabled jurisdictions with no dataset of this role.

        The point of the registry: a city nobody wired up is a named finding,
        not an empty result set that reads like an answer.
        """
        return tuple(j for j in self.active() if not self.for_layer(j, provides))


def load_pipeline(path: Path | None = None) -> Pipeline:
    """Read and validate the registry, reporting every problem at once."""
    raw: Any = yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise PipelineError("pipeline config must be a mapping")

    working = int(raw.get("working_srid", 0))
    if not working:
        raise PipelineError("pipeline config must declare working_srid")

    problems: list[str] = []
    datasets: dict[str, Dataset] = {}
    for key, spec in (raw.get("datasets") or {}).items():
        if not isinstance(spec, dict):
            problems.append(f"{key}: dataset must be a mapping")
            continue
        try:
            datasets[key] = Dataset(key=key, **spec)
        except Exception as exc:  # pydantic validation, reported not raised
            problems.append(f"{key}: {exc}")

    for key, ds in datasets.items():
        if ds.native_srid is not None and ds.native_srid == working:
            problems.append(
                f"{key}: native_srid equals working_srid — drop it rather than "
                f"implying a reprojection that does not happen"
            )

    jurisdictions = {str(k): bool(v) for k, v in (raw.get("jurisdictions") or {}).items()}
    served = {s for d in datasets.values() for s in d.serves}
    for layer_id in jurisdictions:
        if not any(layer_id == s or layer_id.startswith(f"{s}/") for s in served):
            problems.append(f"{layer_id}: declared as a jurisdiction but no dataset covers it")

    if problems:
        raise PipelineError(
            "pipeline config is not runnable:\n  " + "\n  ".join(sorted(problems))
        )

    return Pipeline(
        version=int(raw.get("version", 1)),
        working_srid=working,
        display_srid=int(raw.get("display_srid", 4326)),
        defaults=Defaults(**(raw.get("defaults") or {})),
        jurisdictions=jurisdictions,
        datasets=datasets,
    )


def describe(pipeline: Pipeline, layers: Iterable[str] | None = None) -> list[str]:
    """One line per enabled jurisdiction naming its zoning source.

    Used by the coverage report and worth reading before any run: a city
    silently falling back to regional zoning is a legitimate choice, but not
    one anybody should make by accident.
    """
    out = []
    for layer_id in layers or pipeline.active():
        zoning = pipeline.for_layer(layer_id, Provides.zoning)
        source = zoning[0].label if zoning else "NOTHING"
        out.append(f"{layer_id}: {source}")
    return out
