"""Tualatin's Washington County side: the ten codes run 51's gate named.

Washington County went live as run 51 (2026-10-01), and its map put lots under
ten Tualatin codes the Clackamas corner of the city never carried. The gate's
"zone codes nobody has ruled on" row listed all ten. Each is ruled here once,
with the reason in the layer:

- **Six refusals, read off their own use tables.** IN lists no residential
  category at all; CN allows "one (1) dwelling unit for each business located
  on the lot"; CR allows only Multi-Family Structures (five or more units, TDC
  31.060) and manufactured dwelling parks, and only as a conditional use; MP,
  MBP and BCE allow a caretaker residence and nothing else. Each table closes
  its list: "Use categories which are not listed are prohibited".
- **Three that permit only townhouses.** RH, RH/HR (RH-HR in its own chapter)
  and MUC permit the building only as townhouses on unit lots -- their
  Multi-Family Structure is five or more units and none has a Quadplex row.
  They waited as `to_read` until 2026-10-08 and are zone blocks now, with the
  `unit_lots` Townhouse row as the way in (test_tualatin_high_density.py).
- **CC, a block since 2026-10-02.** It refuses on its base table and permits
  Quadplexes by name on the ten Residential Sub-District blocks of the
  Central Tualatin Overlay, drawn on Comprehensive Plan Map 10-3. Steph
  supplied the map; the blocks are traced in the layer's ``drawn_areas`` and
  the permission is a variant on ``inside_mapped_use_area``
  (test_drawn_areas.py).
"""

from __future__ import annotations

import pytest

from flats.ingest.normalize import ruling_for, zone_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

TUALATIN = "or/clackamas/tualatin"

#: The ten codes run 51's gate listed, with the words each refusal turns on.
REFUSED = {
    "IN": "Use categories which are not listed are prohibited",
    "CN": "one (1) dwelling unit for each business located on the lot",
    "CR": "Conditional uses limited to:",
    "MP": "caretaker resi- dence when necessary for security",
    "MBP": "caretaker residence if located in the Tonquin",
    "BCE": "caretaker residence when necessary for security purposes",
}
TOWNHOUSE_ONLY = ("RH", "RH/HR", "MUC")


@pytest.fixture(scope="module")
def tualatin() -> Layer:
    return load_rules()[TUALATIN]


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


def test_every_code_the_gate_named_is_now_ruled(tualatin: Layer) -> None:
    """The gate counts a code that is neither a block nor a ruling as new."""
    for code in (*REFUSED, *TOWNHOUSE_ONLY, "CC"):
        normalised, held = zone_for(tualatin, code)
        assert normalised == code, code
        assert held is not None or ruling_for(tualatin, normalised), code


def test_the_six_refusals_quote_their_own_use_tables(tualatin: Layer) -> None:
    for zone, words in REFUSED.items():
        use = tualatin.zones[zone].values["quadplex_allowed"]
        assert use.value is False, zone
        text = _text(use.prov.quote)
        assert words in text, (zone, text)
        assert "Use categories which are not listed are prohibited" in text, zone


def test_the_three_that_permit_only_townhouses_are_blocks_now(tualatin: Layer) -> None:
    """Each permits the building only as townhouses on unit lots: the base
    answer is refused and the Townhouse row is a `unit_lots` variant."""
    for code in TOWNHOUSE_ONLY:
        assert code in tualatin.zones, code
        assert code not in tualatin.zone_rulings, code
        use = tualatin.zones[code].values["quadplex_allowed"]
        assert use.value is False, code
        (townhouse,) = use.variants
        assert townhouse.value is True and townhouse.when == ("unit_lots",), code


def test_rh_and_muc_have_no_quadplex_row() -> None:
    """The reading behind three of the four: a townhouse row and a five-plus
    Multi-Family row, and nothing between."""
    store = ProvenanceStore()
    rh = " ".join(store.quote("or/clackamas/tualatin/43.rh.txt#L94-L104").split())
    muc = " ".join(store.quote("or/clackamas/tualatin/57.muc.txt#L155-L166").split())
    for table in (rh, muc):
        assert "Townhouse (or Rowhouse) P" in table
        assert "Multi-Family Structure P" in table
        assert "Quadplex" not in table
    assert "Single-Family Dwelling N" in rh


def test_cc_permits_quadplexes_only_through_the_overlay() -> None:
    store = ProvenanceStore()
    base = " ".join(store.quote("or/clackamas/tualatin/53.cc.txt#L21-L27").split())
    overlay = " ".join(
        store.quote(
            "or/clackamas/tualatin/58.central-tualatin-overlay.txt#L34,L43-L48"
        ).split()
    )
    assert "Household Living" not in base
    assert "Blocks 2, 3, 15, 16, 17, 18, 19, 20, 22 and 23" in overlay
    assert "Quadplexes" in overlay


def test_cc_is_a_block_whose_permission_is_the_overlay(tualatin: Layer) -> None:
    assert "CC" not in tualatin.zone_rulings
    use = tualatin.zones["CC"].values["quadplex_allowed"]
    assert use.value is False
    assert "Household Living" not in _text(use.prov.quote)
    (inside,) = use.variants
    assert inside.value is True and inside.when == ("inside_mapped_use_area",)
    assert "Quadplexes" in _text(inside.prov.quote)
