"""Pointing an encoded number at the line it came from, and refusing to guess.

Attaching is the second-most dangerous thing in this subsystem, behind writing
values. A quote is what a reviewer reads instead of the chapter, so a wrong one
does not merely fail — it manufactures agreement, because the number and the
sentence will be checked against each other and nothing else.

Every test here is therefore a refusal or a proof of aim: what it points at,
and what it leaves unpointed rather than point somewhere plausible.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from flats.encode.attach import apply, main, plan, unquoted
from flats.encode.corroborate import Finding, Verdict
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

DOC = "or/multnomah/portland/33.110.txt"
LAYER = "or/multnomah/portland"

CITE = {
    "cite": "PCC 33.110.220, Table 110-4",
    "url": "https://www.portland.gov/code/33/100s/110",
    "retrieved": "2026-08-12",
}

TEXT = """33.110.220 Setbacks
Table 110-4
Standard                      RF          R5          R2.5
- Front building              20 ft.      10 ft.      12 ft.
 setback
- Rear building               10 ft.      5 ft.       5 ft.
 setback
Maximum Height                30 ft.      30 ft. [3]  35 ft.
[3] Additional height may be allowed. See 33.110.265.F.
"""

#: R5 carries four values: two the document states plainly, one it states with a
#: footnote, one it states differently than the file does.
FILE = {
    "label": "Portland",
    "kind": "city",
    "eligible": True,
    "zones": {
        "R5": {
            "cite_default": CITE,
            "setback_front_ft": 10,
            "setback_rear_ft": {"value": 5},
            "max_height_ft": 30,
            "min_lot_sqft": 3000,
        },
        "R2.5": {"cite_default": CITE, "setback_front_ft": 10},
    },
}


@pytest.fixture()
def rules(tmp_path: Path) -> Path:
    root = tmp_path / "jurisdictions" / "or" / "multnomah"
    root.mkdir(parents=True)
    (root.parent / "_state.yaml").write_text(
        yaml.safe_dump({"label": "Oregon", "kind": "state", "zones": {}}), encoding="utf-8"
    )
    (root / "portland.yaml").write_text(yaml.safe_dump(FILE), encoding="utf-8")
    return tmp_path / "jurisdictions"


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    ProvenanceStore(root).save(DOC, url=CITE["url"], text=TEXT, retrieved=date(2026, 8, 12))
    return root


def run(rules: Path, store: Path, *extra: str) -> int:
    return main(["--doc", DOC, "--rules", str(rules), "--docs", str(store), LAYER, *extra])


def loaded(rules: Path) -> dict:
    return yaml.safe_load((rules / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8"))


def has_quote(node) -> bool:
    """A refused value stays in whatever form it was written in — often a bare
    scalar, which is exactly the shape that has nowhere to hide a quote."""
    return isinstance(node, dict) and bool(node.get("quote"))


def layer(rules: Path):
    return load_rules(rules, strict=False)[LAYER]


def finding(zone: str, field: str, verdict: Verdict, encoded, *found, notes=()) -> Finding:
    return Finding(
        layer=LAYER,
        zone=zone,
        field=field,
        verdict=verdict,
        encoded=encoded,
        found=tuple(found),
        quote=f"{DOC}#L4",
        notes=notes,
    )


# --- what it points at -------------------------------------------------


def test_a_value_the_document_states_gets_the_line_it_states_it_on(rules: Path, store: Path) -> None:
    run(rules, store, "--apply")

    assert loaded(rules)["zones"]["R5"]["setback_front_ft"]["quote"] == f"{DOC}#L4"


def test_the_shorthand_form_expands_and_keeps_its_number(rules: Path, store: Path) -> None:
    # `setback_front_ft: 10` has nowhere to put a quote. Expanding it must not
    # be a chance to change what it says.
    run(rules, store, "--apply")
    written = loaded(rules)["zones"]["R5"]["setback_front_ft"]

    assert written["value"] == 10


def test_the_mapping_form_keeps_everything_else_it_carried(rules: Path, store: Path) -> None:
    run(rules, store, "--apply")
    written = loaded(rules)["zones"]["R5"]["setback_rear_ft"]

    assert written == {"value": 5, "quote": f"{DOC}#L6"}


def test_attaching_does_not_promote(rules: Path, store: Path) -> None:
    # A quote is where to look, not proof somebody looked. The value stays a
    # draft and stays on the queue — that is the whole boundary.
    run(rules, store, "--apply")
    written = loaded(rules)["zones"]["R5"]["setback_front_ft"]

    assert "status" not in written
    assert "reviewer" not in written


def test_the_rest_of_the_file_survives(rules: Path, store: Path) -> None:
    run(rules, store, "--apply")
    after = loaded(rules)

    assert after["label"] == "Portland"
    assert after["zones"]["R5"]["cite_default"]["cite"] == CITE["cite"]
    assert after["zones"]["R2.5"]["setback_front_ft"] == 10


# --- what it refuses ---------------------------------------------------


def test_a_value_the_document_contradicts_is_left_alone(rules: Path, store: Path) -> None:
    # The file says R2.5 front setback is 10; its own column says 12. Quoting
    # that column would put a reviewer in front of text that disagrees with the
    # number and call it a citation.
    run(rules, store, "--apply")

    assert not has_quote(loaded(rules)["zones"]["R2.5"]["setback_front_ft"])


def test_a_contradiction_is_reported_rather_than_dropped(rules: Path, store: Path) -> None:
    _, skipped = plan(
        [finding("R2.5", "setback_front_ft", Verdict.differs, 10, 12.0)], layer(rules)
    )

    assert [(s.zone, s.field) for s in skipped] == [("R2.5", "setback_front_ft")]
    assert "resolve first" in skipped[0].reason


def test_a_footnoted_number_is_not_quoted_even_when_it_agrees(rules: Path, store: Path) -> None:
    # "30 ft. [3]" with "[3] Additional height may be allowed" is a base case
    # with an exit. The number matches; the rule does not.
    run(rules, store, "--apply")

    assert not has_quote(loaded(rules)["zones"]["R5"]["max_height_ft"])


def test_two_numbers_for_one_field_are_not_resolved_by_quoting_one(rules: Path) -> None:
    attachments, skipped = plan(
        [finding("R5", "setback_front_ft", Verdict.agrees, 10, 10.0, 15.0)], layer(rules)
    )

    assert attachments == []
    assert "more than one value" in skipped[0].reason


def test_a_value_the_document_never_states_stays_unquoted(rules: Path, store: Path) -> None:
    # min_lot_sqft is in the file and nowhere in this chapter. Silence is not
    # disagreement, so it is not reported as one — it simply stays unreviewable
    # until somebody finds the section that states it.
    run(rules, store, "--apply")

    assert not has_quote(loaded(rules)["zones"]["R5"]["min_lot_sqft"])


def test_an_existing_quote_is_never_repointed(rules: Path) -> None:
    raw = {"zones": {"R5": {"setback_front_ft": {"value": 10, "quote": f"{DOC}#L99"}}}}
    from flats.encode.attach import Attachment

    updated, refused = apply(raw, [Attachment("R5", "setback_front_ft", 10, f"{DOC}#L4")])

    assert updated["zones"]["R5"]["setback_front_ft"]["quote"] == f"{DOC}#L99"
    assert [s.reason for s in refused] == ["already quoted"]


def test_a_field_the_file_does_not_carry_is_refused_not_created(rules: Path) -> None:
    from flats.encode.attach import Attachment

    updated, refused = apply({"zones": {"R5": {}}}, [Attachment("R5", "max_far", 1.0, DOC)])

    assert updated["zones"]["R5"] == {}
    assert [s.reason for s in refused] == ["not in the file"]


# --- what counts as unquoted -------------------------------------------


def test_already_quoted_values_are_not_in_the_work_list(rules: Path, store: Path) -> None:
    run(rules, store, "--apply")

    assert ("R5", "setback_front_ft") not in unquoted(layer(rules))


def test_a_variant_is_not_something_this_tool_points(tmp_path: Path) -> None:
    # An exception cites the clause granting it, which is rarely the line the
    # base number sits on. Pointing it at that line would be a wrong citation
    # on the value most likely to be misread.
    root = tmp_path / "jurisdictions" / "or" / "multnomah"
    root.mkdir(parents=True)
    (root.parent / "_state.yaml").write_text(
        yaml.safe_dump({"label": "Oregon", "kind": "state", "zones": {}}), encoding="utf-8"
    )
    (root / "portland.yaml").write_text(
        "label: Portland\n"
        "kind: city\n"
        "zones:\n"
        "  R5:\n"
        "    cite_default:\n"
        f'      cite: "{CITE["cite"]}"\n'
        f'      url: "{CITE["url"]}"\n'
        "      retrieved: 2026-08-12\n"
        "    setback_front_ft:\n"
        "      value: 10\n"
        f'      quote: "{DOC}#L4"\n'
        "      variants:\n"
        "        - value: 5\n"
        "          when: [affordable]\n",
        encoding="utf-8",
    )

    assert unquoted(load_rules(tmp_path / "jurisdictions", strict=False)[LAYER]) == set()


# --- the report --------------------------------------------------------


def test_a_dry_run_writes_nothing(rules: Path, store: Path) -> None:
    before = (rules / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8")

    assert run(rules, store) == 0
    assert (rules / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8") == before


def test_the_report_says_how_many_stay_unquoted(rules: Path, store: Path, capsys) -> None:
    # The count that matters is what is left, not what was done — the ladder
    # only moves off `unquoted` when it reaches zero.
    run(rules, store)
    out = capsys.readouterr().out

    assert "value(s) still unquoted after this" in out


def test_an_unknown_layer_is_an_error_not_an_empty_report(rules: Path, store: Path) -> None:
    code = main(["--doc", DOC, "--rules", str(rules), "--docs", str(store), "or/nowhere"])

    assert code == 2


# --- the file survives the edit ----------------------------------------


COMMENTED = """label: Portland
kind: city
code:
  # This URL is the artifact; the HTML route is navigation furniture.
  - id: "33.110"
    url: https://www.portland.gov/code/33.110.pdf
zones:
  R5:
    cite_default:
      cite: PCC 33.110.220
      url: https://www.portland.gov/code/33/100s/110
      retrieved: '2026-08-12'
    # Ported from quadfit; nobody has read this one yet.
    setback_front_ft: 10
    setback_rear_ft:
      value: 5
"""


def test_the_comments_in_the_file_survive() -> None:
    # These record why a URL is the one that serves the ordinance. Nothing else
    # holds that, so a writer that re-dumps parsed YAML destroys knowledge.
    from flats.encode.attach import Attachment, insert_quotes

    written, missed = insert_quotes(
        COMMENTED, [Attachment("R5", "setback_front_ft", 10, f"{DOC}#L4")]
    )

    assert "# This URL is the artifact" in written
    assert "# Ported from quadfit" in written
    assert missed == []


def test_the_edit_parses_to_exactly_the_parsed_transform() -> None:
    from flats.encode.attach import Attachment, insert_quotes

    ats = [
        Attachment("R5", "setback_front_ft", 10, f"{DOC}#L4"),
        Attachment("R5", "setback_rear_ft", 5, f"{DOC}#L6"),
    ]
    written, _ = insert_quotes(COMMENTED, ats)
    expected, _ = apply(yaml.safe_load(COMMENTED), ats)

    assert yaml.safe_load(written) == expected


def test_a_key_outside_the_zones_block_is_never_touched() -> None:
    # `code:` carries an `id:` and a `url:`, and a zone carries fields. Nothing
    # about the shape of a line says which block it is in.
    from flats.encode.attach import Attachment, insert_quotes

    written, missed = insert_quotes(COMMENTED, [Attachment("R5", "url", 0, DOC)])

    assert "quote" not in written
    assert [s.field for s in missed] == ["url"]


def test_a_field_in_a_different_zone_is_not_the_one_edited() -> None:
    from flats.encode.attach import Attachment, insert_quotes

    two = COMMENTED + "  R2.5:\n    setback_front_ft: 10\n"
    written, _ = insert_quotes(two, [Attachment("R2.5", "setback_front_ft", 10, f"{DOC}#L9")])
    loaded_two = yaml.safe_load(written)

    assert loaded_two["zones"]["R2.5"]["setback_front_ft"]["quote"] == f"{DOC}#L9"
    assert loaded_two["zones"]["R5"]["setback_front_ft"] == 10
