"""A yard printed for one story and grown for each story above it.

Cornelius 18.35.050 (D)(2), the A-2 rear yard: "No rear yard shall be less
than 10 feet in depth for a single-story structure, plus five feet per
additional story as measured from the foundation of the structure." The pod
is two stories, so it owes 15 feet, and 15 is printed nowhere. Writing 15 into
the rule file would be the invented figure the readiness ladder exists to
catch; writing 10 would state the single-story yard as if it were the pod's,
five feet looser along the whole rear line.

So the file states the 10 and the five the sentence prints, the loader adds
the stories, and the citation is checked against the 10. The same bargain
`per_height_ft` strikes, counted in stories because that is what the code
counts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from flats.designs.model import load_catalog
from flats.encode.readiness import _quoted_parts
from flats.rules.fields import DESIGN_STORIES
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Provenance, Value

pytestmark = pytest.mark.unit

A2 = "or/washington/cornelius/cmc.18.35.a-2.txt"
PROV = Provenance(
    cite="CMC 18.35.050 (D)(2)",
    url="https://example.invalid/18.35",
    retrieved="2026-10-01",
    quote=f"{A2}#L204",
)


def _somewhere(root: Path, body: str) -> Path:
    d = root / "or" / "washington"
    d.mkdir(parents=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/washington/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  A-2:\n"
        "    cite_default:\n"
        "      cite: CMC 18.35\n"
        "      url: https://example.invalid/18.35\n"
        "      retrieved: '2026-10-01'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def _rear(extra: str = "", field: str = "setback_rear_ft", plus: str = "5") -> str:
    return (
        f"    {field}:\n"
        "      value: 10\n"
        f"      plus_per_story_ft: {plus}\n"
        f'      quote: "{A2}#L204"\n' + extra
    )


def test_the_design_stories_constant_is_the_tallest_design_in_the_catalog() -> None:
    """Two places name how many stories the pod has. If they part company the
    yard this form grows is grown for a building nobody is building."""
    assert max(d.stories for d in load_catalog()) == DESIGN_STORIES


def test_a_two_story_building_owes_the_single_story_yard_and_one_more_step(
    tmp_path: Path,
) -> None:
    layer = load_rules(_somewhere(tmp_path, _rear()))["or/washington/somewhere"]
    rear = layer.zones["A-2"].values["setback_rear_ft"]

    assert rear.before_story == 10
    assert rear.plus_per_story_ft == 5
    assert rear.value == 10 + 5 * (DESIGN_STORIES - 1)
    assert rear.value == 15


def test_the_ladder_looks_for_the_printed_ten_not_the_fifteen(tmp_path: Path) -> None:
    layer = load_rules(_somewhere(tmp_path, _rear()))["or/washington/somewhere"]
    rows = {name: number for _zone, name, _q, number, _d in _quoted_parts(layer)}

    assert rows["setback_rear_ft"] == 10


def test_a_yard_per_story_will_not_grow_a_variant(tmp_path: Path) -> None:
    extra = (
        "      variants:\n"
        "      - when: [attached_wall]\n"
        "        value: 0\n"
        f'        quote: "{A2}#L208"\n'
    )
    with pytest.raises(RuleLoadError, match="adds to the base and no variant"):
        load_rules(_somewhere(tmp_path, _rear(extra)))


def test_a_yard_per_story_needs_a_positive_step(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="expects a positive distance"):
        load_rules(_somewhere(tmp_path, _rear(plus="0")))


def test_only_a_yard_grows_with_the_building(tmp_path: Path) -> None:
    """A lot area per story is not a rule any code writes."""
    with pytest.raises(RuleLoadError, match="grows a yard with the building"):
        load_rules(_somewhere(tmp_path, _rear(field="min_lot_sqft")))


def test_a_step_without_the_single_story_figure_is_refused() -> None:
    with pytest.raises(ValidationError, match="needs both the single-story figure"):
        Value(name="setback_rear_ft", value=15, prov=PROV, plus_per_story_ft=5)
