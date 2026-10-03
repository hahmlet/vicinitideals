"""Flags and binding parameters -- the two kinds of reason a lot is not green.

Steph's flag plan (``FLATS Flag System Plan.md``, 2026-10-02) splits what we
do not know from what we know:

* A **flag** is an unknown: "look at this". It carries no colour. Its type,
  in the registry (``flats/config/flags.yaml``), holds the risk, the
  severity, how it gets resolved and who owns it.
* A **binding parameter** (:class:`Bind`) is a known that blocks: a
  confirmed standard this lot misses with this pod. Only the screen makes
  one, and only binds make a lot RED.

The colour is never stored as an input. :func:`colour` derives it from the
binds, the flags, the registry and the rule set (``flats/config/colour.yaml``),
so changing a tolerance or a severity is an edit to a setting, not a
re-screen.

Steph's answers of 2026-10-02, which this module encodes:

1. *"We aren't accepting variances at all at this time. We need to log these,
   but for now, items requiring variance go red."* Every miss is a bind; the
   path round it rides on the bind (:attr:`Bind.relief`) so it can be
   reviewed later, and ``accept_approvals`` in the rule set is empty.
2. A flag a lot clears even at its worst reading stays a flag at severity 0
   (:attr:`Flag.severity`), and *"items with risk < 3 (or whatever we decide)
   are still green"* -- ``yellow_at_severity``.
3. A minimum density missed is a flag, not a bind: *"Everything is a flag if
   it could potentially harm a lot. It would just be a low risk flag. Maybe
   a 2."* (``DENSITY-MIN``.)
4. The colour shown stays the "as if signed" one.

Everything human-owned -- risk, severity, resolution, scope, priority, the
rule set -- is a file a person edits. A type nobody approved yet counts at its
proposed values (``status: pending``), as the plan says.
"""

from __future__ import annotations

import enum
import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from flats.rules.conditions import CONDITIONS

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
REGISTRY_PATH = CONFIG_DIR / "flags.yaml"
COLOUR_PATH = CONFIG_DIR / "colour.yaml"


class Colour(str, enum.Enum):
    """The traffic light the flag plan asks for: three colours, no fourth.

    Today's UNKNOWN is a lot with open flags, which is YELLOW here; today's
    YELLOW (a miss with a path round it) is a bind, which is RED until the
    rule set accepts that path."""

    green = "green"
    yellow = "yellow"
    red = "red"


class Kind(str, enum.Enum):
    #: A value with a range: the instance must carry its bounds.
    parametric = "parametric"
    #: Something that holds or does not.
    categorical = "categorical"


class Risk(str, enum.Enum):
    """How likely the bad answer is the true one. The number each band
    stands for lives in the rule set (``risk_bands``), human-owned."""

    remote = "remote"
    unlikely = "unlikely"
    possible = "possible"
    likely = "likely"
    near_certain = "near_certain"


class Resolution(str, enum.Enum):
    #: An email or a call to an agency.
    external_inquiry = "external_inquiry"
    #: A handful of shared documents somebody reads.
    document_review = "document_review"
    #: A person looks at each lot (a deed, a survey, the site).
    per_lot_review = "per_lot_review"
    #: A map layer we acquire, or a measurement we take ourselves. Proposed
    #: 2026-10-02 as the plan's fourth type: most of today's unknowns are a
    #: fact no layer answered yet, not a question for anybody.
    measurement = "measurement"


class Scope(str, enum.Enum):
    #: One answer resolves every lot with the same key.
    shared = "shared"
    per_lot = "per_lot"


class Priority(str, enum.Enum):
    now = "now"
    next = "next"
    later = "later"
    parked = "parked"


class TypeStatus(str, enum.Enum):
    #: Proposed; counts at its proposed values until a person approves it.
    pending = "pending"
    approved = "approved"


#: The parts a resolution key may be built from.
KEY_PARTS = frozenset({"jurisdiction", "zone", "field", "check", "fact", "lot", "design"})

#: Pod dimensions an unfavourable answer could be absorbed by.
POD_DIMENSIONS = frozenset(
    {"footprint_width", "footprint_depth", "height", "stories", "units", "parking", "ground_story"}
)

_CODE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$")

#: The ``lot`` part of a key, as the screen writes it: the screen never
#: knows which parcel it is measuring. :func:`dumps` puts the lot's id in.
LOT = "@"

#: Between the parts of a key. Not "/": a jurisdiction is a path
#: (``or/multnomah/portland``).
SEP = "|"


class FlagType(BaseModel):
    """One row of the registry. Every field is required; nothing defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    description: str = Field(min_length=10)
    kind: Kind
    risk: Risk
    #: 1-10: the chance the lot goes red if the answer goes against us
    #: (10 = 100%). Human-owned.
    severity: int = Field(ge=1, le=10)
    #: The pod dimension that could absorb a bad answer, or None.
    absorbs: str | None
    resolution: Resolution
    scope: Scope
    #: What the resolution key is made of, in order.
    key: tuple[str, ...] = Field(min_length=1)
    #: Who or what answers it.
    path: str = Field(min_length=3)
    priority: Priority
    status: TypeStatus
    approved_by: str | None
    approved_on: date | None
    #: The screen reason code(s) this type replaced -- the reconciliation
    #: against the colours from before flags existed reads it.
    raised_from: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> "FlagType":
        if not _CODE.match(self.code):
            raise ValueError(f"{self.code!r}: codes are UPPER-CASE words joined by hyphens")
        bad = set(self.key) - KEY_PARTS
        if bad:
            raise ValueError(f"{self.code}: unknown key parts {sorted(bad)}")
        if self.absorbs is not None and self.absorbs not in POD_DIMENSIONS:
            raise ValueError(f"{self.code}: absorbs {self.absorbs!r} is not a pod dimension")
        if self.scope is Scope.per_lot and "lot" not in self.key:
            raise ValueError(f"{self.code}: a per-lot type's key must include the lot")
        if self.scope is Scope.shared and "lot" in self.key:
            raise ValueError(f"{self.code}: a shared type's key cannot include the lot")
        approved = self.status is TypeStatus.approved
        if approved != (self.approved_by is not None and self.approved_on is not None):
            raise ValueError(
                f"{self.code}: approved_by and approved_on are set exactly when status is approved"
            )
        return self


class ColourRules(BaseModel):
    """The rule set that turns binds and flags into a colour. Human-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: A lot with any open flag at this severity or above is YELLOW.
    yellow_at_severity: int = Field(ge=1, le=10)
    #: Relief conditions (``adjustment``, ``variance``, ``conditional_use``
    #: ...) whose path we will take. A bind whose relief is one of these is a
    #: question, not a wall. Empty: Steph 2026-10-02, no variances.
    accept_approvals: tuple[str, ...]
    #: Severity a bind carries when ``accept_approvals`` opens it.
    approval_severity: int = Field(ge=1, le=10)
    #: The number each risk band stands for. Pending approval.
    risk_bands: dict[Risk, float]
    status: TypeStatus
    approved_by: str | None
    approved_on: date | None
    note: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> "ColourRules":
        missing = set(Risk) - set(self.risk_bands)
        if missing:
            raise ValueError(f"risk_bands misses {sorted(m.value for m in missing)}")
        if any(not 0.0 < p <= 1.0 for p in self.risk_bands.values()):
            raise ValueError("a risk band is a probability above 0 and at most 1")
        for name in self.accept_approvals:
            c = CONDITIONS.get(name)
            if c is None or c.kind != "relief":
                raise ValueError(f"accept_approvals: {name!r} is not a registered relief")
        approved = self.status is TypeStatus.approved
        if approved != (self.approved_by is not None and self.approved_on is not None):
            raise ValueError("approved_by and approved_on are set exactly when status is approved")
        return self


class Registry:
    """Every flag type, by code."""

    def __init__(self, types: Iterable[FlagType]) -> None:
        self.types: dict[str, FlagType] = {}
        for t in types:
            if t.code in self.types:
                raise ValueError(f"flag type {t.code} registered twice")
            self.types[t.code] = t

    def __getitem__(self, code: str) -> FlagType:
        try:
            return self.types[code]
        except KeyError:
            raise KeyError(
                f"flag type {code} is not in the registry -- propose it in flags.yaml "
                "(status: pending) rather than raising an unregistered flag"
            ) from None

    def __contains__(self, code: object) -> bool:
        return code in self.types

    def __iter__(self):
        return iter(self.types.values())

    def __len__(self) -> int:
        return len(self.types)


def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Registry(FlagType(code=code, **body) for code, body in (data.get("types") or {}).items())


def load_rules(path: Path = COLOUR_PATH) -> ColourRules:
    return ColourRules(**yaml.safe_load(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def registry() -> Registry:
    return load_registry()


@lru_cache(maxsize=1)
def colour_rules() -> ColourRules:
    return load_rules()


def fact_code(fact: str) -> str:
    """The flag type for a site fact nobody observed: ``FACT-CORNER-LOT``."""
    return "FACT-" + fact.upper().replace("_", "-")


@dataclass(frozen=True, slots=True)
class Flag:
    """One open flag on one lot x design."""

    code: str
    #: The resolution key's value, :data:`SEP`-joined in the type's key order.
    key: str
    #: The screen reason this flag stands for (the reconciliation reads it).
    by: str
    #: Low and high, for a parametric type.
    bounds: tuple[float, float] | None = None
    #: Where it came from: the rule, the citation, the measurement.
    source: str = ""
    #: This lot's own severity where it differs from the type's -- 0 when
    #: the lot clears even at the flag's worst reading (Steph 2026-10-02).
    severity: int | None = None

    def as_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "key": self.key, "by": self.by}
        if self.bounds is not None:
            out["bounds"] = [self.bounds[0], self.bounds[1]]
        if self.source:
            out["source"] = self.source
        if self.severity is not None:
            out["severity"] = self.severity
        return out

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> "Flag":
        b = d.get("bounds")
        return cls(
            code=d["code"],
            key=d["key"],
            by=d["by"],
            bounds=(float(b[0]), float(b[1])) if b is not None else None,
            source=d.get("source", ""),
            severity=d.get("severity"),
        )


@dataclass(frozen=True, slots=True)
class Bind:
    """A confirmed standard this lot misses with this pod.

    Generated only by the screen. ``relief`` is the path the code offers
    round it -- logged, not taken, while the rule set accepts no approvals."""

    #: The check that failed (``fit_ft``, ``min_lot_area_sqft``, ``use``).
    check: str
    #: Measured and required, in the check's own units. None for the use gate.
    observed: float | None
    threshold: float | None
    #: How far short, in the check's units; None for the use gate.
    shortfall: float | None
    #: Citation of the standard, where the rule carries one.
    source: str = ""
    #: The registered relief condition that could clear it, if any.
    relief: str | None = None
    #: That path's tier (``administrative``, ``discretionary``, ``unavailable``).
    relief_tier: str | None = None
    #: Whether anybody has read the chapter granting that path.
    relief_confirmed: bool = False

    def as_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"check": self.check}
        for name in ("observed", "threshold", "shortfall"):
            v = getattr(self, name)
            if v is not None:
                out[name] = round(float(v), 3)
        if self.source:
            out["source"] = self.source
        if self.relief is not None:
            out["relief"] = self.relief
        if self.relief_tier is not None:
            out["relief_tier"] = self.relief_tier
        if self.relief_confirmed:
            out["relief_confirmed"] = True
        return out

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> "Bind":
        return cls(
            check=d["check"],
            observed=d.get("observed"),
            threshold=d.get("threshold"),
            shortfall=d.get("shortfall"),
            source=d.get("source", ""),
            relief=d.get("relief"),
            relief_tier=d.get("relief_tier"),
            relief_confirmed=bool(d.get("relief_confirmed", False)),
        )


def validate(flags: Iterable[Flag], reg: Registry | None = None) -> None:
    """The write gate: an incomplete flag fails here, before it is stored.

    A registered type, a key with one value per key part, bounds exactly
    when the type is parametric (low <= high), a severity override only in
    range and only downward -- a lot may matter less than its type, never
    more, because raising a severity is a person's call."""
    reg = reg or registry()
    for f in flags:
        t = reg[f.code]
        parts = f.key.split(SEP) if f.key else []
        if len(parts) != len(t.key) or not all(parts):
            raise ValueError(f"{f.code}: key {f.key!r} does not fill {'/'.join(t.key)}")
        if not f.by:
            raise ValueError(f"{f.code}: a flag must name the screen reason that raised it")
        if (t.kind is Kind.parametric) != (f.bounds is not None):
            raise ValueError(f"{f.code}: bounds are required for parametric types and only for them")
        if f.bounds is not None and f.bounds[0] > f.bounds[1]:
            raise ValueError(f"{f.code}: bounds {f.bounds} run backwards")
        if f.severity is not None and not 0 <= f.severity <= t.severity:
            raise ValueError(
                f"{f.code}: a lot's severity {f.severity} must lie between 0 and its type's {t.severity}"
            )


def make(
    code: str,
    by: str,
    parts: Mapping[str, Any],
    *,
    bounds: tuple[float, float] | None = None,
    source: str = "",
    reg: Registry | None = None,
) -> Flag:
    """A flag of type ``code`` with its key filled from ``parts`` in the
    order the type names them; a part the type does not use is ignored."""
    t = (reg or registry())[code]
    missing = [p for p in t.key if parts.get(p) in (None, "")]
    if missing:
        raise ValueError(f"{code}: no value for key part(s) {missing}")
    values = [str(parts[p]) for p in t.key]
    if any(SEP in v for v in values):
        raise ValueError(f"{code}: a key part holds the separator {SEP!r}: {values}")
    return Flag(code, SEP.join(values), by, bounds=bounds, source=source)


def severity_of(flag: Flag, reg: Registry | None = None) -> int:
    """The lot's own severity if it has one, else the type's."""
    if flag.severity is not None:
        return flag.severity
    return (reg or registry())[flag.code].severity


def accepted(bind: Bind, rules: ColourRules) -> bool:
    """Whether the rule set takes the path round this bind.

    A combined path (``conditional_use+state_middle_housing``) is taken only
    when every part of it is accepted."""
    if bind.relief is None or bind.relief_tier == "unavailable":
        return False
    return all(part in rules.accept_approvals for part in bind.relief.split("+"))


def colour(
    binds: Sequence[Bind],
    flags: Sequence[Flag],
    *,
    reg: Registry | None = None,
    rules: ColourRules | None = None,
) -> Colour:
    """RED on any bind the rule set does not waive; YELLOW on any open flag
    (or waived bind) at ``yellow_at_severity`` or above; else GREEN."""
    reg = reg or registry()
    rules = rules or colour_rules()
    waived = [b for b in binds if accepted(b, rules)]
    if len(waived) < len(binds):
        return Colour.red
    if waived and rules.approval_severity >= rules.yellow_at_severity:
        return Colour.yellow
    if any(severity_of(f, reg) >= rules.yellow_at_severity for f in flags):
        return Colour.yellow
    return Colour.green


def dumps(items: Sequence[Flag] | Sequence[Bind], *, lot: str | None = None) -> str:
    """The bridge column: a compact JSON list, '' when empty. ``lot`` fills
    the :data:`LOT` part of a flag's key with the parcel's id."""
    if not items:
        return ""
    rows = [i.as_json() for i in items]
    if lot is not None:
        for r in rows:
            if "key" in r:
                r["key"] = SEP.join(lot if part == LOT else part for part in r["key"].split(SEP))
    return json.dumps(rows, separators=(",", ":"))


def flags_from(text: Any) -> list[Flag]:
    if not text or not isinstance(text, str):
        return []
    return [Flag.from_json(d) for d in json.loads(text)]


def binds_from(text: Any) -> list[Bind]:
    if not text or not isinstance(text, str):
        return []
    return [Bind.from_json(d) for d in json.loads(text)]


__all__ = [
    "Bind",
    "Colour",
    "ColourRules",
    "Flag",
    "FlagType",
    "Kind",
    "LOT",
    "Priority",
    "Registry",
    "Resolution",
    "Risk",
    "SEP",
    "Scope",
    "TypeStatus",
    "accepted",
    "binds_from",
    "colour",
    "colour_rules",
    "dumps",
    "fact_code",
    "flags_from",
    "load_registry",
    "load_rules",
    "make",
    "registry",
    "severity_of",
    "validate",
]
