"""The rulings register, flats/config/rulings.yaml, is well formed.

The register lists every decision Steph has made that changes how a lot is
judged. The loader validates its shape exactly; this test holds the same shape
against the real file with plain yaml, and checks that every place an entry
names exists: a city scope names a jurisdiction file, a zone names a zone that
file holds (under ``zones`` or ``zone_rulings``), a ``superseded_by`` names
another entry, and an ``encoded_in`` path is a real file.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ROOT / "flats" / "config" / "rulings.yaml"
JURISDICTIONS = ROOT / "flats" / "config" / "jurisdictions" / "or"

REQUIRED = {"id", "kind", "date", "scope", "question", "ruling", "effect", "source"}
OPTIONAL = {"effective", "encoded_in", "superseded_by"}
KINDS = {"ruling", "adopted_change"}
SCOPE_KEYS = {"county", "city", "zones", "tlids"}
COUNTIES = {"multnomah", "clackamas", "washington"}


@lru_cache(maxsize=1)
def entries() -> list[dict]:
    data = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))
    assert isinstance(data, list), "the register is a list of entries"
    return data


def _ids(entry_list: list[dict]) -> list[str]:
    return [e.get("id") for e in entry_list]


def _as_date(value) -> dt.date:
    # yaml hands back a date for an unquoted YYYY-MM-DD and a str for a quoted one.
    if isinstance(value, dt.datetime):
        raise AssertionError(f"{value!r} carries a time; a date only")
    if isinstance(value, dt.date):
        return value
    assert isinstance(value, str), f"{value!r} is not a date"
    return dt.date.fromisoformat(value)


def _city_file(scope: dict) -> Path | None:
    city = scope.get("city")
    if city is None:
        return None
    county = scope.get("county")
    if county is not None:
        path = JURISDICTIONS / county / f"{city}.yaml"
        return path if path.is_file() else None
    found = sorted(JURISDICTIONS.glob(f"*/{city}.yaml"))
    return found[0] if len(found) == 1 else None


@lru_cache(maxsize=None)
def _zone_codes(path: Path) -> frozenset[str]:
    layer = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    codes: set[str] = set()
    for block in ("zones", "zone_rulings"):
        codes.update(str(k) for k in (layer.get(block) or {}))
    return frozenset(codes)


def test_the_register_has_entries():
    assert len(entries()) > 0


def test_ids_are_unique_slugs():
    ids = _ids(entries())
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"duplicate ids: {dupes}"
    for i in ids:
        assert isinstance(i, str) and i, f"bad id {i!r}"
        assert i == i.strip().lower() and " " not in i, f"id is not a slug: {i!r}"


@pytest.mark.parametrize("entry", entries(), ids=_ids(entries()))
def test_entry_shape(entry):
    keys = set(entry)
    assert not REQUIRED - keys, f"missing {sorted(REQUIRED - keys)}"
    assert not keys - REQUIRED - OPTIONAL, f"unknown keys {sorted(keys - REQUIRED - OPTIONAL)}"
    assert entry["kind"] in KINDS
    for key in ("id", "question", "ruling", "effect", "source"):
        assert isinstance(entry[key], str) and entry[key].strip(), f"{key} is empty"

    date = _as_date(entry["date"])
    if "effective" in entry:
        assert entry["kind"] == "adopted_change", "effective belongs to an adopted_change"
        _as_date(entry["effective"])
    # the id leads with the date it was decided
    assert entry["id"].startswith(date.isoformat()), "id does not start with its date"

    scope = entry["scope"]
    assert isinstance(scope, dict), "scope is a mapping ({} = statewide)"
    assert not set(scope) - SCOPE_KEYS, f"unknown scope keys {sorted(set(scope) - SCOPE_KEYS)}"
    if "county" in scope:
        assert scope["county"] in COUNTIES
    for key in ("zones", "tlids"):
        if key in scope:
            assert isinstance(scope[key], list) and scope[key], f"{key} is a non-empty list"
            assert all(isinstance(v, str) and v for v in scope[key])
    if "zones" in scope:
        assert "city" in scope, "a zone scope names the city whose file holds the zone"

    if "encoded_in" in entry:
        assert isinstance(entry["encoded_in"], list) and entry["encoded_in"]
        assert all(isinstance(p, str) and p for p in entry["encoded_in"])
    if "superseded_by" in entry:
        assert isinstance(entry["superseded_by"], str)


def test_every_superseded_by_names_a_later_entry():
    by_id = {e["id"]: e for e in entries()}
    for e in entries():
        target = e.get("superseded_by")
        if target is None:
            continue
        assert target in by_id, f"{e['id']}: superseded_by {target!r} names no entry"
        assert target != e["id"], f"{e['id']} supersedes itself"
        assert _as_date(by_id[target]["date"]) >= _as_date(e["date"]), (
            f"{e['id']} is superseded by an earlier ruling {target}"
        )


def test_every_city_names_a_jurisdiction_file():
    for e in entries():
        scope = e["scope"]
        if "city" not in scope:
            continue
        path = _city_file(scope)
        assert path is not None, (
            f"{e['id']}: no single jurisdiction file for city {scope['city']!r}"
            f" (county {scope.get('county')!r})"
        )


def test_every_zone_exists_in_its_city_file():
    for e in entries():
        scope = e["scope"]
        if "zones" not in scope:
            continue
        path = _city_file(scope)
        assert path is not None, f"{e['id']}: zone scope without a jurisdiction file"
        missing = [z for z in scope["zones"] if z not in _zone_codes(path)]
        assert not missing, (
            f"{e['id']}: zones {missing} are not in {path.relative_to(ROOT).as_posix()}"
        )


def test_every_encoded_in_path_exists():
    for e in entries():
        for rel in e.get("encoded_in", []):
            assert (ROOT / rel).exists(), f"{e['id']}: encoded_in {rel!r} does not exist"
