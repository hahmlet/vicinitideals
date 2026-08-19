"""A footnote nobody can answer has to reach the verdict, or it decided nothing.

The disposition register can call a footnote ``unmeasured`` all day; unless
the fact it names arrives at the screen, the value under it resolves looking
exactly like one nothing qualifies, and Oregon City certifies lots against a
setback its own code calls a floor. This is the join, end to end: ledger ->
resolution -> lever -> unknown fact -> not GREEN.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flats.encode.qualified import caps, qualified, write_caps
from flats.rules import caps as caps_module
from flats.rules.caps import LEDGER, caps_for
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def fresh() -> None:
    caps_module.reload()
    yield
    caps_module.reload()


# --- the ledger --------------------------------------------------------


def test_the_shipped_ledger_matches_what_the_corpus_says(tmp_path: Path) -> None:
    # The one failure mode a generated file has: somebody rules on a footnote
    # and forgets to regenerate, so the screen goes on certifying values a
    # ruling already qualified.
    written = write_caps(qualified(), tmp_path / "caps.json")
    assert json.loads(written.read_text(encoding="utf-8")) == json.loads(
        LEDGER.read_text(encoding="utf-8")
    ), "flats/config/caps.json is stale — run python -m flats.encode.qualified --write-caps"


def test_oregon_city_setbacks_carry_the_easement(tmp_path: Path) -> None:
    fields = caps_for("or/clackamas/oregon-city", "R-5")
    assert "utility_easement" in fields["setback_front_ft"]


def test_a_layer_nobody_capped_is_absent() -> None:
    assert caps_for("or/multnomah/gresham", "R-5") == {}
    assert caps_for("nowhere", "nothing") == {}


def test_a_missing_ledger_caps_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A checkout with no encoding work in it still resolves.
    monkeypatch.setattr(caps_module, "LEDGER", tmp_path / "absent.json")
    caps_module.reload()
    assert caps_for("or/clackamas/oregon-city", "R-5") == {}


def test_only_unmeasured_notes_cap(tmp_path: Path) -> None:
    # Dismissed notes were read and ruled irrelevant, and unread ones stop the
    # value being signed at all. Neither belongs here: this file is for the
    # third case, where the reading is done and the data is missing.
    rows = qualified()
    ledger = caps(rows)
    capped = {
        (row.layer, row.zone, row.standard)
        for row in rows
        if row.standard in ledger.get(row.layer, {}).get(row.zone, {})
    }
    for row in rows:
        key = (row.layer, row.zone, row.standard)
        if key in capped:
            continue
        assert not row.capping, f"{key} turns on {row.capping[0].fact} and is not in the ledger"


# --- and what it does to a verdict -------------------------------------


def test_the_cap_becomes_a_lever_on_the_standard() -> None:
    # levers is what the screen consults. A fact that never gets there is a
    # ruling in a file nobody reads.
    rules = RuleSet(load_rules())
    got = rules.resolve("or/clackamas/oregon-city", "R-5")
    assert "utility_easement" in got.levers
    assert "utility_easement" in got.values["setback_front_ft"].levers


def test_an_uncapped_jurisdiction_gains_no_levers() -> None:
    rules = RuleSet(load_rules())
    got = rules.resolve("or/multnomah/gresham", "R-5")
    assert "utility_easement" not in got.levers


def test_the_lever_is_one_nothing_measures() -> None:
    # The whole cap rests on this: configure lists a fact with no assumption
    # as unknown, and a standard turning on an unknown cannot be certified.
    # A fact carrying an assumption would be answered by default and cap
    # nothing, which is why the disposition loader refuses one.
    from flats.rules.conditions import condition

    for layer, zones in json.loads(LEDGER.read_text(encoding="utf-8")).items():
        for zone, fields in zones.items():
            for field, facts in fields.items():
                for fact in facts:
                    defn = condition(fact)
                    assert defn.kind == "site_fact", f"{layer}/{zone}/{field}: {fact}"
                    assert defn.assume is None, f"{layer}/{zone}/{field}: {fact}"
