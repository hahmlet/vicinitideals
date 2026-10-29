"""Gresham Table 4.0430: row C's width/depth ratio, and note 12's gateways
(FOLLOWUPS 104(e) and (b), 2026-10-21).

Row C asks a residential lot in the corridor districts to be at least half as
wide as it is deep -- "0.5 : 1", width over depth (4.0431.A). The registry's
field is the other way round (``max_lot_depth_ratio``, depth over width), so
the file states the 0.5 the table prints (``width_to_depth``) and the loader
makes the 2 it comes to. Note 6 lifts it for lots created for townhouses.

Note 12 points at 7.0512.B.6, three storeys at the Rockwood gateways. It does
not reach the pod: B.6 sits under "All Development", which 7.0512 defines to
leave out townhouses, and 7.0502(B) takes quadplexes out of 7.0501-7.0512
altogether. The tests pin that the stored text still says so -- if Gresham
rewords either sentence, the dismissal has to be read again.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flats.encode.readiness import _printed
from flats.rules.loader import RuleLoadError, load_rules

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs" / "or" / "multnomah" / "gresham"
FOOTNOTES = Path(__file__).resolve().parents[1] / "config" / "footnotes" / "or" / "multnomah" / "gresham.yaml"


def _layer(root: Path, body: str) -> Path:
    (root / "or" / "multnomah").mkdir(parents=True)
    (root / "or" / "or.yaml").write_text("layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8")
    (root / "or" / "multnomah" / "somewhere.yaml").write_text(
        "layer: or/multnomah/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  SC:\n"
        "    cite_default:\n"
        "      cite: GDC Table 4.0430\n"
        "      url: https://example.invalid/4.0400\n"
        "      retrieved: '2026-10-21'\n" + body,
        encoding="utf-8",
    )
    return root


def test_a_width_depth_ratio_is_held_as_the_depth_it_allows(tmp_path: Path) -> None:
    root = _layer(
        tmp_path,
        "    max_lot_depth_ratio:\n"
        "      width_to_depth: 0.5\n"
        "      quote: 'or/multnomah/somewhere/4.0400.txt#L306'\n",
    )
    held = load_rules(root, strict=True)["or/multnomah/somewhere"].zones["SC"].values["max_lot_depth_ratio"]
    assert held.value == 2.0
    assert held.width_to_depth == 0.5
    # The citation check looks for the figure the table prints, not the 2.
    assert _printed(held) == 0.5


@pytest.mark.parametrize(
    "body",
    [
        # Only the depth ratio is a ratio of the lot's two sides.
        "    min_lot_width_ft:\n      width_to_depth: 0.5\n      quote: 'x.txt#L1'\n",
        # Both a number and the ratio it inverts.
        "    max_lot_depth_ratio:\n      value: 2\n      width_to_depth: 0.5\n      quote: 'x.txt#L1'\n",
        "    max_lot_depth_ratio:\n      width_to_depth: 0\n      quote: 'x.txt#L1'\n",
    ],
)
def test_a_width_depth_ratio_is_refused_where_it_cannot_mean_anything(tmp_path: Path, body: str) -> None:
    with pytest.raises(RuleLoadError):
        load_rules(_layer(tmp_path, body), strict=True)


@pytest.mark.parametrize("zone", ["SC", "SC-RJ", "CMU", "CMF"])
def test_gresham_corridor_zones_hold_row_c(zone: str) -> None:
    held = load_rules()[GRESHAM].zones[zone].values["max_lot_depth_ratio"]
    assert held.width_to_depth == 0.5 and held.value == 2.0
    # Proof copy 4.0400.corridor.txt L295,L306-L310 until Gresham was cut into
    # sections (FOLLOWUPS 73, batch 5).
    assert held.prov.quote == f"{GRESHAM}/4/4.0430.txt#L8,L19-L23"
    # One lot: twice as deep as wide at most. Townhouse lots: note 6 lifts it.
    assert held.under().value == 2.0
    assert held.under({"unit_lots"}).exempt is True


def test_row_c_and_note_6_still_say_what_the_encoding_reads() -> None:
    text = (DOCS / "4.0400.corridor.txt").read_text(encoding="utf-8").splitlines()
    squash = lambda i: " ".join(text[i - 1].split())  # noqa: E731
    assert squash(306).startswith("C. Minimum Lot 0.5 : 1 for 0.5 : 1 for 0.5 : 1 for 0.5 : 1 for 0.5 : 1 for")
    assert "lot width/depth ratio standards do not apply to lots or parcels created for Townhouses" in squash(445)
    assert "dividing the lot width" in squash(502) and "by the lot depth dimension" in squash(503)


def test_the_rockwood_gateways_do_not_reach_the_pod() -> None:
    text = (DOCS / "7.0500.rockwood-design.txt").read_text(encoding="utf-8").splitlines()
    squash = lambda i: " ".join(text[i - 1].split())  # noqa: E731
    # 7.0502(B): plexes are out of 7.0501-7.0512 altogether.
    assert "Section 7.0501-7.0512 do not apply to" in squash(44)
    assert squash(45).startswith("• Single detached dwellings, duplexes, triplexes, and quadplexes")
    # "All Development" leaves townhouses out, and B.6 is All Development.
    assert squash(214).startswith("• All Development: All developments, except townhouses")
    assert squash(3431) == "B.6. Gateways"
    assert squash(3447) == "All Development All Development"
    # Two columns share each line: the standard's half ends "no less" on one
    # line and resumes "than 3 stories in height" on the next.
    assert squash(3457).endswith("shall be no less")
    assert "than 3 stories in height" in squash(3458)
    # A quadplex split onto unit lots is still a quadplex.
    defs = (DOCS / "3.0100.definitions.txt").read_text(encoding="utf-8").splitlines()
    assert "considered a quadplex" in defs[963]


def test_note_12_stays_dismissed_on_applicability() -> None:
    notes = yaml.safe_load(FOOTNOTES.read_text(encoding="utf-8"))
    # Proof copy 4.0400.corridor.txt L465 until the cut (FOLLOWUPS 73, batch 5).
    entries = [n for n in notes["notes"] if n["quote"] == f"{GRESHAM}/4/4.0430.txt#L147"]
    assert len(entries) == 1
    (note,) = entries
    assert note["state"] == "dismissed"
    assert "7.0502(B)" in note["reason"] and "All Development" in note["reason"]


def test_cmf_townhouse_path_is_open_only_on_the_corridor() -> None:
    # Table 4.0420 note 2: no middle housing land division in CMF off the
    # NE Glisan / NE 162nd corridors. Without this, note 6's exemptions let
    # an off-corridor CMF lot go GREEN as townhouses (the 104 bound).
    use = load_rules()[GRESHAM].zones["CMF"].values["quadplex_allowed"]
    assert use.under().value is True
    assert use.under({"civic_corridor"}).value is True
    assert use.under({"unit_lots"}).value is False
    assert use.under({"unit_lots", "civic_corridor"}).value is True
    text = (DOCS / "4.0400.corridor.txt").read_text(encoding="utf-8").splitlines()
    note = " ".join(" ".join(text[i - 1].split()) for i in (217, 218))
    assert "Middle housing land divisions are not permitted in the CMF land use district outside these areas" in note


@pytest.mark.parametrize("zone", ["MDR-12", "MDR-24", "OFR"])
def test_the_corridor_design_district_residential_zones_face_the_street(zone: str) -> None:
    """7.0420(J)(1)(a)'s 50 percent frontage occupation reaches plexes in the
    Corridor Design District, and 3.0100 puts MDR-12, MDR-24 and OFR in it
    (2026-10-21; it had been carried on the corridor zones only)."""
    held = load_rules()[GRESHAM].zones[zone].values["orientation_constraint"]
    assert held.value == "axis_required"
    definitions = (DOCS / "3.0100.definitions.txt").read_text(encoding="utf-8").splitlines()
    text = " ".join(definitions[833:837])
    assert "Corridor Design District" in text
    for named in ("MDR-12", "MDR-24", "OFR"):
        assert named in text
