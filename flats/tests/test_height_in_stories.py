"""A height stated in stories, where the code says how tall a story may be.

Hillsboro's residential tables print "2 1/2 stories or 35 feet, whichever is
less", and 12.50.140 B.6 says "a residential 'story' is considered to be not
more than 10 feet". Steph ruled 2026-09-29 that the math holds: 25 feet. The
file states the two printed numbers, each against its own citation, and the
loader carries the product, which is printed nowhere -- the same bargain as
`per_height_ft`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.readiness import quotes_the_number
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Provenance, Value

pytestmark = pytest.mark.unit

PROV = Provenance(
    cite="Hillsboro CDC Table 12.21.250-1",
    url="https://example.invalid/12.21",
    retrieved="2026-09-29",
    quote="or/washington/hillsboro/cdc.12.21.middle-housing-zones.txt#L1",
)


def _somewhere(root: Path, body: str) -> Path:
    d = root / "or" / "washington"
    d.mkdir(parents=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/washington/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  R-6:\n"
        "    cite_default:\n"
        "      cite: CDC 12.21\n"
        "      url: https://example.invalid/12.21\n"
        "      retrieved: '2026-09-29'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


STORY = (
    "      story_ft:\n"
    "        ft: 10\n"
    "        cite: CDC 12.50.140 B.6\n"
    "        quote: 'or/washington/somewhere/b6.txt#L1'\n"
)


def test_the_loader_multiplies_the_count_by_the_story(tmp_path: Path) -> None:
    layer = load_rules(
        _somewhere(
            tmp_path,
            "    max_height_ft:\n"
            "      stories: 2.5\n" + STORY +
            "      quote: 'or/washington/somewhere/12.21.txt#L1'\n",
        ),
        strict=False,
    )["or/washington/somewhere"]
    held = layer.zones["R-6"].values["max_height_ft"]
    assert held.value == 25
    assert (held.stories, held.story_ft) == (2.5, 10)
    assert held.story_ft_quote == "or/washington/somewhere/b6.txt#L1"


def test_a_count_of_stories_without_the_story_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="'story_ft' block"):
        load_rules(
            _somewhere(
                tmp_path,
                "    max_height_ft:\n"
                "      stories: 2.5\n"
                "      quote: 'or/washington/somewhere/12.21.txt#L1'\n",
            ),
            strict=True,
        )


def test_feet_and_stories_are_not_both_stated(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="feet or a count of stories"):
        load_rules(
            _somewhere(
                tmp_path,
                "    max_height_ft:\n"
                "      stories: 2.5\n"
                "      value: 25\n" + STORY +
                "      quote: 'or/washington/somewhere/12.21.txt#L1'\n",
            ),
            strict=True,
        )


def test_only_a_height_is_counted_in_stories() -> None:
    with pytest.raises(ValueError, match="applies to max_height_ft"):
        Value(
            name="setback_side_ft", value=25, stories=2.5, story_ft=10,
            story_ft_cite="B.6", story_ft_quote="x#L1", prov=PROV,
        )


def test_the_feet_a_story_may_be_must_be_cited() -> None:
    with pytest.raises(ValueError, match="cite and quote it"):
        Value(name="max_height_ft", value=25, stories=2.5, story_ft=10, prov=PROV)


def test_readiness_looks_for_the_count_the_table_prints() -> None:
    # The table prints "2 1/2 stories"; the 25 is printed nowhere.
    assert quotes_the_number("2 ½ stories or 35 feet, whichever is less", 2.5)
    assert not quotes_the_number("2 ½ stories or 35 feet, whichever is less", 25)
