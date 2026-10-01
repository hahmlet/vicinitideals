"""A passage read and set aside on purpose is located, not just described.

The page check tints what we encoded, and a reviewer must tell an untinted
clause nobody weighed (a blind miss) from one that was read and declined (a
conscious refusal). The prose refusals in refusals.py carry no line numbers,
so a layer's ``set_aside:`` list names the lines; the loader holds each entry
to a quote it can place on the page.
"""

from __future__ import annotations

from flats.rules import loader
from flats.rules.loader import load_rules

ZONES = {"R-2": object()}


def _parse(raw):
    problems: list[str] = []
    out = loader._parse_set_aside(raw, ZONES, where="x", problems=problems)
    return out, problems


def test_an_entry_is_a_quote_a_reason_and_optionally_its_zones():
    out, problems = _parse(
        [{"quote": "code.pdf.txt#L10-L12,L20", "why": "applies to garages", "zones": ["R-2"]}]
    )

    assert problems == []
    assert out[0].quote == "code.pdf.txt#L10-L12,L20"
    assert out[0].zones == ("R-2",)


def test_an_entry_that_could_not_be_placed_on_the_page_is_refused():
    out, problems = _parse(
        [
            {"quote": "section 16.12", "why": "no line numbers"},
            {"quote": "code.pdf.txt#L1", "zones": ["R-99"]},
            {"quote": "code.pdf.txt#L1", "reason": "a key the loader does not know"},
        ]
    )

    assert out == ()
    assert len(problems) == 3


def test_oregon_city_locates_what_it_read_and_declined():
    layer = load_rules()["or/clackamas/oregon-city"]

    assert len(layer.set_aside) >= 12
    assert all(s.why for s in layer.set_aside), "a set-aside without a reason is a guess"
