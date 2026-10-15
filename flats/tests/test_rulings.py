"""The rulings register: validation on load and which lots an entry speaks to."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from flats import rulings

TLID = "1S2E08BA  -09500"

VALID = f"""
- id: statewide-note
  kind: ruling
  date: 2026-10-01
  scope: {{}}
  question: Does it hold everywhere?
  ruling: Yes.
  effect: Nothing changes.
  source: Steph 2026-10-01
- id: split-zones
  kind: ruling
  date: 2026-10-14
  scope:
    county: multnomah
    city: portland
    zones: [R5, r2.5]
  question: Which zone rules a split lot?
  ruling: The larger share.
  effect: The screen uses it.
  source: Steph 2026-10-14
  encoded_in: [flats/score/screen.py]
- id: lot-only
  kind: ruling
  date: 2026-10-14
  scope:
    tlids: ["{TLID}", "1N1E29DD  -05600"]
  question: q
  ruling: r
  effect: e
  source: s
- id: old-way
  kind: ruling
  date: 2026-09-01
  scope: {{county: multnomah}}
  question: q
  ruling: r
  effect: e
  source: s
  superseded_by: split-zones
- id: new-code
  kind: adopted_change
  date: 2026-08-01
  effective: 2027-01-01
  scope: {{county: clackamas, city: milwaukie}}
  question: q
  ruling: r
  effect: e
  source: Ordinance 1, Exhibit A p. 3
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "rulings.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _ids(found: list[rulings.Entry]) -> list[str]:
    return [e.id for e in found]


def _entry(**over: str) -> str:
    base = {
        "id": "a", "kind": "ruling", "date": "2026-10-14", "question": "q",
        "ruling": "r", "effect": "e", "source": "s",
    }
    base.update(over)
    lines = [f"{'- ' if i == 0 else '  '}{k}: {v}" for i, (k, v) in enumerate(base.items())]
    return "\n".join(lines) + "\n  scope: {}\n"


def test_a_valid_file_loads(tmp_path):
    entries = rulings.load(_write(tmp_path, VALID))
    assert len(entries) == 5
    split = entries[1]
    assert split.date == dt.date(2026, 10, 14)
    assert split.scope.zones == ("R5", "r2.5")
    assert split.encoded_in == ("flats/score/screen.py",)
    assert entries[4].effective == dt.date(2027, 1, 1)
    assert split.as_dict()["scope"] == {"county": "multnomah", "city": "portland", "zones": ["R5", "r2.5"]}


def test_a_missing_file_is_an_empty_register(tmp_path):
    assert rulings.load(tmp_path / "nope.yaml") == ()
    assert rulings.load(_write(tmp_path, "")) == ()


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ("- id: x\n  kind: ruling\n", "entry 'x': missing key(s)"),
        (_entry(color="red"), "entry 'a': unknown key(s) color"),
        (_entry(date="14/10/2026"), "entry 'a': date must be a YYYY-MM-DD"),
        (_entry(date="2026-13-45"), "entry 'a': date must be a YYYY-MM-DD"),
        (_entry(kind="opinion"), "entry 'a': kind must be one of"),
        (_entry(effective="2027-01-01"), "effective belongs to adopted_change"),
        (_entry(kind="adopted_change", effective="soon"), "entry 'a': effective must be"),
        (_entry() + "- 3\n", "entry #2: must be a mapping"),
        (_entry() + _entry(), "entry 'a': duplicate id"),
        (_entry(superseded_by="ghost"), "entry 'a': superseded_by names no entry 'ghost'"),
        ("a: b\n", "must be a YAML list"),
    ],
)
def test_each_validation_error_names_the_entry(tmp_path, body, needle):
    with pytest.raises(ValueError, match=re.escape(needle)):
        rulings.load(_write(tmp_path, body))


def test_an_unknown_scope_key_and_a_bad_scope_value_raise(tmp_path):
    bad_key = _entry().replace("scope: {}", "scope: {town: x}")
    with pytest.raises(ValueError, match="entry 'a': unknown scope key"):
        rulings.load(_write(tmp_path, bad_key))
    bad_zones = _entry().replace("scope: {}", "scope: {zones: R5}")
    with pytest.raises(ValueError, match="entry 'a': scope.zones must be a list"):
        rulings.load(_write(tmp_path, bad_zones))


def test_a_scope_matches_only_when_every_key_it_sets_matches(tmp_path):
    entries = rulings.load(_write(tmp_path, VALID))
    portland = rulings.match("multnomah", "portland", "R5", "X", entries)
    assert _ids(portland) == ["statewide-note", "split-zones", "old-way"]
    # zone matching ignores case, and a zone outside the list does not match
    assert "split-zones" in _ids(rulings.match("Multnomah", "Portland", "R2.5", "X", entries))
    assert "split-zones" not in _ids(rulings.match("multnomah", "portland", "R1", "X", entries))
    assert "split-zones" not in _ids(rulings.match("multnomah", "gresham", "R5", "X", entries))
    assert "split-zones" not in _ids(rulings.match("clackamas", "portland", "R5", "X", entries))


def test_a_tlid_with_spaces_matches_whole(tmp_path):
    entries = rulings.load(_write(tmp_path, VALID))
    assert "lot-only" in _ids(rulings.match("multnomah", "portland", "R5", TLID, entries))
    assert "lot-only" in _ids(rulings.match("multnomah", "portland", "R5", "1N1E29DD  -05600", entries))
    # one space instead of two is a different lot, and no word of it matches
    assert "lot-only" not in _ids(rulings.match("multnomah", "portland", "R5", "1S2E08BA -09500", entries))
    assert "lot-only" not in _ids(rulings.match("multnomah", "portland", "R5", "1S2E08BA", entries))


def test_a_statewide_entry_matches_every_lot(tmp_path):
    entries = rulings.load(_write(tmp_path, VALID))
    assert _ids(rulings.match("washington", "beaverton", "R7", "T", entries)) == ["statewide-note"]
    assert _ids(rulings.match(None, None, None, None, entries)) == ["statewide-note"]


def test_superseded_entries_come_last_and_are_marked(tmp_path):
    entries = rulings.load(_write(tmp_path, VALID))
    found = rulings.match("multnomah", "portland", "R5", TLID, entries)
    assert _ids(found) == ["statewide-note", "split-zones", "lot-only", "old-way"]
    assert [e.superseded for e in found] == [False, False, False, True]
    assert found[-1].as_dict()["superseded_by"] == "split-zones"


def test_match_reads_the_register_file_when_given_no_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(rulings, "PATH", _write(tmp_path, VALID))
    assert _ids(rulings.match("clackamas", "milwaukie", "R1", "T")) == ["statewide-note", "new-code"]


def test_browse_drops_only_what_a_filter_contradicts(tmp_path):
    entries = rulings.load(_write(tmp_path, VALID))
    assert _ids(rulings.browse(entries=entries)) == ["statewide-note", "split-zones", "lot-only", "new-code", "old-way"]
    assert _ids(rulings.browse(county="clackamas", entries=entries)) == ["statewide-note", "lot-only", "new-code"]
    assert _ids(rulings.browse(county="multnomah", zone="R1", entries=entries)) == ["statewide-note", "lot-only", "old-way"]
    assert _ids(rulings.browse(tlid=TLID, city="portland", entries=entries)) == [
        "statewide-note", "split-zones", "lot-only", "old-way",
    ]
