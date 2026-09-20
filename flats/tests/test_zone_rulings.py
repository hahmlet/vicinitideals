"""``zone_rulings`` -- the county map's zone codes that are not zone blocks, read and ruled.

Steph, 2026-09-20, reading the first refreshed copy's list of 128 unencoded
codes: *"We need to document why these zones don't work for us and then they
should never appear to the user again. Only if a new zone appears that we've
never seen before should we flag for user."* So a forbidden use is a zone
block (``quadplex_allowed: false`` with its quote -- RED at the use gate), a
permitted-but-unread zone is a zone block with the gaps ledger holding the
rest, and everything else the map can say is one of four rulings held here:
an alias, a pocket of another jurisdiction's zoning, an unholdable district,
a use table still to read. What is tested is the ledger's parse and its
refusals, how normalize reads a ruled code (an alias screens under the zone
it names; the rest gate on their outcome and are counted as ruled, never as
new), and how the assign stage answers a forbidden zone without a measurement.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from flats.ingest import assign as az
from flats.ingest import normalize as nz
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import ZONE_RULING_OUTCOMES, ZoneRuling

NOTE = "One lot on the 2026-09 map carries the city's own casing of a code the rules hold."


def _corpus(root: Path, block: str, zones: str = "zones: {}\n") -> Path:
    d = root / "or" / "clackamas"
    d.mkdir(parents=True, exist_ok=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/clackamas/somewhere\nkind: city\nlabel: Somewhere\n" + zones + block,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text("layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8")
    return root


R5 = """zones:
  R5:
    quadplex_allowed:
      value: true
      cite: "1.2.3"
      url: https://example.test/code
      retrieved: '2026-09-20'
      quote: "or/clackamas/somewhere/1.txt#L1"
"""


# -- the ledger --------------------------------------------------------------


def test_the_four_outcomes_and_a_parsed_ledger(tmp_path: Path) -> None:
    assert set(ZONE_RULING_OUTCOMES) == {"alias", "pocket", "unencodable", "to_read"}
    block = f"""zone_rulings:
  r5:
    outcome: alias
    of: R5
    note: >-
      {NOTE}
  RRFF5:
    outcome: pocket
    of: or/clackamas/_unincorporated
    note: >-
      County zoning inside the city line; the county's code governs the lot until the city rezones it.
  HDR:
    outcome: unencodable
    note: >-
      Read 2026-09-09; the setback is measured from the northern lot line, which nothing here measures.
  NSA:
    outcome: to_read
    note: >-
      Seen on the 2026-09 map; the chapter that lists its uses is not in the store yet.
"""
    layer = load_rules(_corpus(tmp_path, block, R5), strict=True)["or/clackamas/somewhere"]
    assert set(layer.zone_rulings) == {"r5", "RRFF5", "HDR", "NSA"}
    assert layer.zone_rulings["r5"] == ZoneRuling(outcome="alias", of="R5", note=NOTE)
    assert layer.zone_rulings["RRFF5"].of == "or/clackamas/_unincorporated"
    assert layer.zone_rulings["HDR"].of is None
    # holds(): a zone block, or what an alias names -- never a ruled-out code.
    assert layer.holds("R5") == "R5" and layer.holds("r5") == "R5"
    assert layer.holds("RRFF5") is None and layer.holds("HDR") is None and layer.holds("QQ9") is None


@pytest.mark.parametrize(
    "block, complaint",
    [
        ("zone_rulings:\n  R5:\n    outcome: pocket\n    of: or/x\n    note: " + NOTE + "\n", "a zone or a ruling, never both"),
        ("zone_rulings:\n  QQ:\n    outcome: alias\n    of: ZZ\n    note: " + NOTE + "\n", "names a zone block this layer holds"),
        ("zone_rulings:\n  QQ:\n    outcome: pocket\n    note: " + NOTE + "\n", "whose zoning it is"),
        ("zone_rulings:\n  QQ:\n    outcome: to_read\n    note: n/a\n", "at least"),
        ("zone_rulings:\n  QQ:\n    outcome: forbidden\n    note: " + NOTE + "\n", "unknown outcome"),
        ("zone_rulings:\n  QQ:\n    outcome: to_read\n    cite: x\n    note: " + NOTE + "\n", "unexpected cite"),
        ("zone_rulings:\n  QQ: just a string\n", "an outcome, a note"),
    ],
)
def test_a_ruling_that_does_not_hold_together_is_refused(tmp_path: Path, block: str, complaint: str) -> None:
    with pytest.raises(RuleLoadError, match=complaint):
        load_rules(_corpus(tmp_path, block, R5), strict=True)


# -- normalize -----------------------------------------------------------------


@pytest.fixture
def somewhere(tmp_path: Path):
    block = f"""zone_rulings:
  r5:
    outcome: alias
    of: R5
    note: >-
      {NOTE}
  RRFF5:
    outcome: pocket
    of: or/clackamas/_unincorporated
    note: >-
      County zoning inside the city line; the county's code governs the lot until the city rezones it.
  HDR:
    outcome: unencodable
    note: >-
      Read 2026-09-09; the setback is measured from the northern lot line, which nothing here measures.
  NSA:
    outcome: to_read
    note: >-
      Seen on the 2026-09 map; the chapter that lists its uses is not in the store yet.
"""
    return load_rules(_corpus(tmp_path, block, R5), strict=True)["or/clackamas/somewhere"]


def test_an_alias_screens_under_the_zone_it_names(somewhere) -> None:
    assert nz.zone_for(somewhere, " r5 ") == ("r5", "R5")
    assert nz.ruling_for(somewhere, "r5") is None, "an alias is a held zone, not a gate"
    assert nz.gate_for(somewhere, on=True, inside_ugb=True, zone_raw="r5", zone="R5") is None


def test_a_ruled_code_gates_on_its_outcome_and_an_unruled_one_is_new(somewhere) -> None:
    for code, outcome, gate in (
        ("RRFF5", "pocket", "ZONE_POCKET"),
        ("HDR", "unencodable", "ZONE_UNENCODABLE"),
        ("NSA", "to_read", "ZONE_TO_READ"),
    ):
        assert nz.zone_for(somewhere, code) == (code, None)
        assert nz.ruling_for(somewhere, code) == outcome
        assert nz.gate_for(somewhere, on=True, inside_ugb=True, zone_raw=code, zone=None, ruling=outcome) == gate
        assert gate in nz.GATES and nz.RULED_GATES[outcome] == gate
    assert nz.ruling_for(somewhere, "QQ9") is None
    assert nz.gate_for(somewhere, on=True, inside_ugb=True, zone_raw="QQ9", zone=None, ruling=None) == "ZONE_NOT_ENCODED"
    assert nz.ruling_for(None, "QQ9") is None and nz.ruling_for(somewhere, None) is None
    # The other gates still come first: a ruling never answers for a switched-off layer.
    assert nz.gate_for(somewhere, on=False, inside_ugb=True, zone_raw="HDR", zone=None, ruling="unencodable") == "JURISDICTION_OFF"


# -- assign: the use gate ----------------------------------------------------


class _Resolved:
    def __init__(self, value, levers=frozenset()):
        self.value = value
        self.levers = levers


class _Resolution:
    def __init__(self, allowed, *, trusted: bool, levers=frozenset()):
        from flats.rules.resolver import Verdict

        self.values = {} if allowed is None else {"quadplex_allowed": _Resolved(allowed, levers)}
        self.verdict = Verdict.trusted if trusted else Verdict.unverified
        self.reason = None if trusted else "RULE_UNVERIFIED"


class _Rules:
    def __init__(self, table):
        self.table = table
        self.calls = 0

    def resolve(self, layer_id, zone):
        self.calls += 1
        if (layer_id, zone) not in self.table:
            raise KeyError(zone)
        return self.table[(layer_id, zone)]


class _Relief:
    def __init__(self, available: set[str]):
        self.available = available

    def for_use(self, layer_id):
        return type("O", (), {"available": layer_id in self.available})()


def test_the_use_gate_mirrors_the_screen() -> None:
    rules = _Rules(
        {
            ("or/a", "C3"): _Resolution(False, trusted=False),
            ("or/a", "R5"): _Resolution(True, trusted=False),
            ("or/a", "R7"): _Resolution(None, trusted=False),
            ("or/a", "LR7"): _Resolution(False, trusted=False, levers=frozenset({"conditional_use"})),
            ("or/b", "C3"): _Resolution(False, trusted=True),
            ("or/c", "C3"): _Resolution(False, trusted=True),
        }
    )
    gate = az.use_gate_for(rules, _Relief({"or/c"}))
    # Forbidden, unsigned: unknown as screened (the resolution's reason), red if signed.
    assert gate("or/a", "C3") == ("unknown", "RULE_UNVERIFIED", "red", "USE_PROHIBITED")
    # Permitted, no answer, or a prohibition some condition can lift: no answer here.
    assert gate("or/a", "R5") is None and gate("or/a", "R7") is None and gate("or/a", "LR7") is None
    # A zone the resolver does not hold is not an answer either.
    assert gate("or/a", "ZZ") is None
    # Signed: the same colour both ways.
    assert gate("or/b", "C3") == ("red", "USE_PROHIBITED", "red", "USE_PROHIBITED")
    # A conditional-use path listed for the use: yellow, as the screen says.
    assert gate("or/c", "C3") == ("yellow", "USE_PROHIBITED", "yellow", "USE_PROHIBITED")
    # Memoised per (layer, zone).
    n = rules.calls
    gate("or/a", "C3")
    gate("or/b", "C3")
    assert rules.calls == n


def test_assign_answers_a_forbidden_zone_without_a_measurement(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    pd.DataFrame([{**{c: None for c in az.ROW_COLUMNS}, "TLID": "M1", "design": "d1", "triage": "unknown", "if_signed": "green"}]).to_parquet(
        bridge / "lots.parquet", index=False
    )
    (bridge / "meta.json").write_text(json.dumps({"lots": 1, "rows": 1}), encoding="utf-8")
    normalized = tmp_path / "normalized"
    normalized.mkdir()
    lots = [
        {"county": "clackamas", "tlid": "M1", "jurisdiction": "or/a", "zone": "R5", "zone_raw": "R5", "area_sqft": 5000.0, "gate": None},
        {"county": "clackamas", "tlid": "F1", "jurisdiction": "or/a", "zone": "C3", "zone_raw": "C3", "area_sqft": 5000.0, "gate": None},
        {"county": "clackamas", "tlid": "U1", "jurisdiction": "or/a", "zone": "R5", "zone_raw": "R5", "area_sqft": 5000.0, "gate": None},
        {"county": "clackamas", "tlid": "P1", "jurisdiction": "or/a", "zone": None, "zone_raw": "RRFF5", "area_sqft": 5000.0, "gate": "ZONE_POCKET"},
    ]
    pd.DataFrame(lots).to_parquet(normalized / "lots.parquet", index=False)
    (normalized / "summary.json").write_text(
        json.dumps({"snapshot": "2026-09-18", "new_zones": {}, "ruled_zones": {"or/a": {"pocket": {"RRFF5": 1}}}, "funnel": []}),
        encoding="utf-8",
    )
    rules = _Rules({("or/a", "C3"): _Resolution(False, trusted=False), ("or/a", "R5"): _Resolution(True, trusted=False)})
    meta = az.assign(normalized, bridge, tmp_path / "out", use_gate=az.use_gate_for(rules, _Relief(set())))

    frame = pd.read_parquet(tmp_path / "out" / "lots.parquet").set_index("TLID")
    forbidden = frame.loc["F1"]
    assert (forbidden["triage"], forbidden["reasons"], forbidden["if_signed"], forbidden["if_signed_reasons"]) == (
        "unknown", "RULE_UNVERIFIED", "red", "USE_PROHIBITED"
    )
    assert forbidden["zone"] == "C3" and forbidden["fits"] is False or forbidden["fits"] == False  # noqa: E712 -- parquet bool
    unclaimed = frame.loc["U1"]
    assert (unclaimed["if_signed"], unclaimed["reasons"]) == ("unknown", "NOT_MEASURED,quadfit:unknown")
    pocket = frame.loc["P1"]
    assert (pocket["if_signed"], pocket["reasons"]) == ("unknown", "ZONE_POCKET")
    assert meta["assign"]["by_reason"] == {"NOT_MEASURED": 1, "USE_PROHIBITED": 1, "ZONE_POCKET": 1}
    assert meta["assign"]["prohibited_by_zone"] == {"or/a/C3": 1}
    assert meta["ruled_zones"] == {"or/a": {"pocket": {"RRFF5": 1}}}
    text = (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")
    assert "USE_PROHIBITED, by zone (red at the use gate, no measurement needed): or/a/C3 1" in text
    assert "Zone codes ruled:" in text and "- or/a pocket: RRFF5 (1)" in text
    assert "nobody has ruled on" not in text


def test_without_a_use_gate_the_stage_is_the_pure_join(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    pd.DataFrame(columns=list(az.ROW_COLUMNS)).to_parquet(bridge / "lots.parquet", index=False)
    (bridge / "meta.json").write_text(json.dumps({"lots": 0, "rows": 0}), encoding="utf-8")
    normalized = tmp_path / "normalized"
    normalized.mkdir()
    pd.DataFrame(
        [{"county": "clackamas", "tlid": "F1", "jurisdiction": "or/a", "zone": "C3", "zone_raw": "C3", "area_sqft": 5000.0, "gate": None}]
    ).to_parquet(normalized / "lots.parquet", index=False)
    meta = az.assign(normalized, bridge, tmp_path / "out")
    assert meta["assign"]["by_reason"] == {"NOT_MEASURED": 1} and meta["assign"]["prohibited_by_zone"] == {}
