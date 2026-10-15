"""The rulings register: decisions people made about how a lot is read, and
code changes adopted but not yet in force.

``flats/config/rulings.yaml`` is one YAML list. Each entry is a ``ruling`` (a
decision somebody made, in plain words, and what the screen does because of
it) or an ``adopted_change`` (an ordinance adopted on one date that takes
force on another). Its ``scope`` says which lots it speaks to: every key it
sets must match the lot, and an empty scope is statewide.

The file is validated whole on load and a bad entry raises ``ValueError``
naming it -- a register an agent reads as authority must not be half-read.
A missing file is an empty register. Superseded entries are kept and returned
last from :func:`match`, marked by ``superseded_by``.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

PATH = Path(__file__).parent / "config" / "rulings.yaml"

KINDS = ("ruling", "adopted_change")

_REQUIRED = ("id", "kind", "date", "scope", "question", "ruling", "effect", "source")
_OPTIONAL = ("effective", "encoded_in", "superseded_by")
_SCOPE_KEYS = ("county", "city", "zones", "tlids")


@dataclass(frozen=True)
class Scope:
    """Which lots an entry speaks to; an unset key matches every lot."""

    county: str | None = None
    city: str | None = None
    zones: tuple[str, ...] = ()
    tlids: tuple[str, ...] = ()

    def matches(self, county: str | None, city: str | None, zone: str | None, tlid: str | None) -> bool:
        if self.county and _fold(self.county) != _fold(county):
            return False
        if self.city and _fold(self.city) != _fold(city):
            return False
        if self.zones and _fold(zone) not in {_fold(z) for z in self.zones}:
            return False
        # A TLID holds spaces ("1S2E08BA  -09500"): compared whole, never split.
        if self.tlids and (tlid or "").strip() not in self.tlids:
            return False
        return True


@dataclass(frozen=True)
class Entry:
    id: str
    kind: str
    date: dt.date
    scope: Scope
    question: str
    ruling: str
    effect: str
    source: str
    effective: dt.date | None = None
    encoded_in: tuple[str, ...] = ()
    superseded_by: str | None = None

    @property
    def superseded(self) -> bool:
        return self.superseded_by is not None

    def as_dict(self) -> dict[str, Any]:
        scope = {
            key: value
            for key, value in (
                ("county", self.scope.county),
                ("city", self.scope.city),
                ("zones", list(self.scope.zones)),
                ("tlids", list(self.scope.tlids)),
            )
            if value
        }
        return {
            "id": self.id,
            "kind": self.kind,
            "date": self.date.isoformat(),
            "effective": self.effective.isoformat() if self.effective else None,
            "scope": scope,
            "question": self.question,
            "ruling": self.ruling,
            "effect": self.effect,
            "source": self.source,
            "encoded_in": list(self.encoded_in),
            "superseded": self.superseded,
            "superseded_by": self.superseded_by,
        }


def _fold(value: str | None) -> str:
    return (value or "").strip().casefold()


def _name(raw: Any, index: int) -> str:
    if isinstance(raw, Mapping) and raw.get("id"):
        return f"entry {raw['id']!r}"
    return f"entry #{index + 1}"


def _text(raw: Mapping[str, Any], key: str, name: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: {key} must be a non-empty string")
    return value


def _day(value: Any, key: str, name: str) -> dt.date:
    if isinstance(value, dt.datetime):
        raise ValueError(f"{name}: {key} must be a YYYY-MM-DD date, got {value!r}")
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError(f"{name}: {key} must be a YYYY-MM-DD date, got {value!r}")


def _strings(value: Any, key: str, name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{name}: {key} must be a list of non-empty strings")
    return tuple(value)


def _scope(raw: Any, name: str) -> Scope:
    if raw is None:
        return Scope()
    if not isinstance(raw, Mapping):
        raise ValueError(f"{name}: scope must be a mapping")
    unknown = sorted(set(raw) - set(_SCOPE_KEYS))
    if unknown:
        raise ValueError(f"{name}: unknown scope key(s) {', '.join(map(str, unknown))}")
    for key in ("county", "city"):
        if key in raw and (not isinstance(raw[key], str) or not raw[key].strip()):
            raise ValueError(f"{name}: scope.{key} must be a non-empty string")
    return Scope(
        county=raw.get("county"),
        city=raw.get("city"),
        zones=_strings(raw.get("zones", []), "scope.zones", name),
        tlids=_strings(raw.get("tlids", []), "scope.tlids", name),
    )


def _entry(raw: Any, index: int) -> Entry:
    name = _name(raw, index)
    if not isinstance(raw, Mapping):
        raise ValueError(f"{name}: must be a mapping")
    unknown = sorted(set(raw) - set(_REQUIRED) - set(_OPTIONAL))
    if unknown:
        raise ValueError(f"{name}: unknown key(s) {', '.join(map(str, unknown))}")
    missing = [k for k in _REQUIRED if k not in raw]
    if missing:
        raise ValueError(f"{name}: missing key(s) {', '.join(missing)}")
    kind = raw["kind"]
    if kind not in KINDS:
        raise ValueError(f"{name}: kind must be one of {', '.join(KINDS)}, got {kind!r}")
    if "effective" in raw and kind != "adopted_change":
        raise ValueError(f"{name}: effective belongs to adopted_change entries only")
    superseded_by = raw.get("superseded_by")
    if superseded_by is not None and not isinstance(superseded_by, str):
        raise ValueError(f"{name}: superseded_by must be an id")
    return Entry(
        id=_text(raw, "id", name),
        kind=kind,
        date=_day(raw["date"], "date", name),
        scope=_scope(raw["scope"], name),
        question=_text(raw, "question", name),
        ruling=_text(raw, "ruling", name),
        effect=_text(raw, "effect", name),
        source=_text(raw, "source", name),
        effective=_day(raw["effective"], "effective", name) if raw.get("effective") is not None else None,
        encoded_in=_strings(raw.get("encoded_in", []), "encoded_in", name),
        superseded_by=superseded_by,
    )


class _Loader(yaml.SafeLoader):
    """SafeLoader that leaves ``2026-10-14`` a string, so a bad date is an
    error naming its entry rather than the parser's."""


_Loader.yaml_implicit_resolvers = {
    key: [(tag, rx) for tag, rx in rules if tag != "tag:yaml.org,2002:timestamp"]
    for key, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load(path: Path | None = None) -> tuple[Entry, ...]:
    """The register, validated; empty when the file is not there."""
    path = path or PATH
    if not path.exists():
        return ()
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path.name}: not valid YAML ({exc})") from exc
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{path.name}: the register must be a YAML list of entries")
    entries = tuple(_entry(item, i) for i, item in enumerate(raw))
    seen: set[str] = set()
    for entry in entries:
        if entry.id in seen:
            raise ValueError(f"entry {entry.id!r}: duplicate id")
        seen.add(entry.id)
    for entry in entries:
        if entry.superseded_by is not None and entry.superseded_by not in seen:
            raise ValueError(f"entry {entry.id!r}: superseded_by names no entry {entry.superseded_by!r}")
    return entries


def match(
    county: str | None,
    city: str | None,
    zone: str | None,
    tlid: str | None,
    entries: Sequence[Entry] | None = None,
) -> list[Entry]:
    """The entries that speak to this lot, superseded ones last. ``city`` is
    the jurisdiction slug (``portland``), not its label."""
    found = [e for e in (load() if entries is None else entries) if e.scope.matches(county, city, zone, tlid)]
    return [e for e in found if not e.superseded] + [e for e in found if e.superseded]


def browse(
    county: str | None = None,
    city: str | None = None,
    zone: str | None = None,
    tlid: str | None = None,
    entries: Sequence[Entry] | None = None,
) -> list[Entry]:
    """The register narrowed by whichever filters are given: an entry stays
    unless its scope names a value that contradicts a filter. No filters, the
    whole register. Superseded entries last."""
    found = []
    for e in load() if entries is None else entries:
        s = e.scope
        if county and s.county and _fold(s.county) != _fold(county):
            continue
        if city and s.city and _fold(s.city) != _fold(city):
            continue
        if zone and s.zones and _fold(zone) not in {_fold(z) for z in s.zones}:
            continue
        if tlid and s.tlids and tlid.strip() not in s.tlids:
            continue
        found.append(e)
    return [e for e in found if not e.superseded] + [e for e in found if e.superseded]
