"""A number nobody has read is not a rule.

A citation names a chapter. A quote proves the chapter says it. Between the two
sits every value in this corpus that somebody typed from a spreadsheet, a PDF
they had open at the time, or a predecessor pipeline — plausible, uncheckable,
and indistinguishable in a zone from a standard three people have confirmed.

So the loader will not put one in a zone. It goes to the layer's queue instead,
where it is work: a lead for whoever goes looking for the passage. Screening
never sees it, printing never quotes it, and a lot it would have decided comes
back as a gap — which is the honest answer, and the one somebody can act on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

PORTLAND = "or/41051-multnomah/4159000-portland"
CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220, Table 110-4"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
)
QUOTED = '  quote: "or/multnomah/portland/33.110.txt#L2"\n'


def portland(root: Path, body: str, cite: str = CITE) -> None:
    p = root / f"{PORTLAND}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("label: Portland\n" + cite + body, encoding="utf-8")


def test_a_value_with_no_quote_never_reaches_the_zone(tmp_path: Path) -> None:
    portland(tmp_path, "zones:\n  R5:\n    setback_front_ft: 10\n")

    layer = load_rules(tmp_path)[PORTLAND]

    assert "setback_front_ft" not in layer.zones["R5"].values
    assert [(w.zone, w.field) for w in layer.wanted] == [("R5", "setback_front_ft")]


def test_the_queue_keeps_the_number_and_the_citation_as_a_lead(tmp_path: Path) -> None:
    """Whoever goes looking should start where the encoder thought it was."""
    portland(tmp_path, "zones:\n  R5:\n    setback_front_ft: 10\n")

    wanted = load_rules(tmp_path)[PORTLAND].wanted[0]

    assert wanted.value.value == 10
    assert wanted.cite.startswith("PCC 33.110.220")
    assert wanted.url.endswith("/110")


def test_a_quoted_value_is_a_rule_and_stays_out_of_the_queue(tmp_path: Path) -> None:
    portland(tmp_path, "zones:\n  R5:\n    setback_front_ft:\n      value: 10\n    " + QUOTED)

    layer = load_rules(tmp_path)[PORTLAND]

    assert layer.zones["R5"].values["setback_front_ft"].value == 10
    assert layer.wanted == ()


def test_a_layer_default_with_no_quote_queues_under_defaults(tmp_path: Path) -> None:
    """Addressed the way every review command names a layer-wide standard."""
    portland(tmp_path, "defaults:\n  max_height_ft: 35\nzones:\n  R5: {}\n")

    layer = load_rules(tmp_path)[PORTLAND]

    assert "max_height_ft" not in layer.defaults
    assert [(w.zone, w.field) for w in layer.wanted] == [("defaults", "max_height_ft")]


def test_quarantining_is_not_an_error_in_the_file(tmp_path: Path) -> None:
    """The file is fine. The encoding is unfinished, which is a different thing.

    Refusing to load the layer would take a jurisdiction's twelve good values
    off the screen along with its one unread one, and nothing would get better
    for it.
    """
    portland(
        tmp_path,
        "zones:\n"
        "  R5:\n"
        "    quadplex_allowed:\n"
        "      value: true\n"
        "    " + QUOTED + "    setback_front_ft: 10\n",
    )

    layer = load_rules(tmp_path)[PORTLAND]

    assert layer.zones["R5"].values["quadplex_allowed"].value is True
    assert len(layer.wanted) == 1


def test_the_queue_is_addressed_the_way_the_encoding_tools_address_a_value(
    tmp_path: Path,
) -> None:
    """``(zone, field) -> Value``, so corroboration and attachment need no
    special case for the half of the corpus they exist to fix."""
    portland(tmp_path, "zones:\n  R5:\n    setback_front_ft: 10\n")

    unread = load_rules(tmp_path)[PORTLAND].unread()

    assert unread[("R5", "setback_front_ft")].value == 10
    assert unread[("R5", "setback_front_ft")].prov.quote is None
