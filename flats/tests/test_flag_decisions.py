"""A person's approval, written into flags.yaml and colour.yaml.

The approval page (/flats/flags) stores a decision; the drain writes it through
``decide_type`` / ``decide_rules``. What these hold to: the decided numbers and
``status: approved`` with who and when land in the right block and nowhere
else, the comments a person wrote survive, and a decision the file would not
load back exactly is refused whole rather than half-applied.

Run against the real files: the whole risk is a line-edit that matches the
wrong block or misses one, and only the real layout can show that.
"""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from flats.score import flags as fp

ON = date(2026, 10, 3)
BY = "Stephen Ketch"


@pytest.fixture(scope="module")
def registry_text() -> str:
    return fp.REGISTRY_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def colour_text() -> str:
    return fp.COLOUR_PATH.read_text(encoding="utf-8")


def _two_codes(text: str) -> tuple[str, str]:
    codes = [t.code for t in fp.parse_registry(text)]
    assert len(codes) > 2
    return codes[0], codes[1]


def test_an_approved_type_carries_the_numbers_and_who_approved_it(registry_text) -> None:
    code, _ = _two_codes(registry_text)
    values = {
        "risk": "likely",
        "severity": 7,
        "absorbs": "height",
        "resolution": "measurement",
        "priority": "now",
    }

    out = fp.decide_type(registry_text, code, values, by=BY, on=ON)

    got = fp.parse_registry(out)[code]
    assert got.risk.value == "likely"
    assert got.severity == 7
    assert got.absorbs == "height"
    assert got.resolution.value == "measurement"
    assert got.priority.value == "now"
    assert got.status is fp.TypeStatus.approved
    assert got.approved_by == BY
    assert got.approved_on == ON


def test_only_the_decided_block_moves(registry_text) -> None:
    code, other = _two_codes(registry_text)
    before = fp.parse_registry(registry_text)

    out = fp.decide_type(
        registry_text, code, {"severity": 9, "priority": "now"}, by=BY, on=ON
    )

    after = fp.parse_registry(out)
    for t in before:
        if t.code != code:
            assert after[t.code] == t, t.code
    assert after[other].status is before[other].status


def test_the_comments_survive(registry_text, colour_text) -> None:
    code, _ = _two_codes(registry_text)
    out = fp.decide_type(registry_text, code, {"severity": 6}, by=BY, on=ON)
    comments = [line for line in registry_text.splitlines() if line.lstrip().startswith("#")]
    assert comments
    assert [line for line in out.splitlines() if line.lstrip().startswith("#")] == comments

    out = fp.decide_rules(colour_text, {"yellow_at_severity": 4}, by=BY, on=ON)
    comments = [line for line in colour_text.splitlines() if line.lstrip().startswith("#")]
    assert comments
    assert [line for line in out.splitlines() if line.lstrip().startswith("#")] == comments
    # Line for line: only values change, so a diff reads as the decision.
    assert len(out.splitlines()) == len(colour_text.splitlines())


def test_a_name_with_a_space_is_quoted_and_reads_back(registry_text) -> None:
    code, _ = _two_codes(registry_text)
    out = fp.decide_type(registry_text, code, {"severity": 5}, by="O'Brien: Ketch", on=ON)
    assert fp.parse_registry(out)[code].approved_by == "O'Brien: Ketch"


@pytest.mark.parametrize(
    "values",
    [
        {"severity": 11},
        {"severity": 0},
        {"risk": "sometimes"},
        {"resolution": "guess"},
        {"scope": "per_lot"},  # not set from the page: a scope change is a key change
        {"status": "approved"},  # only the drain says approved, and it says who
    ],
)
def test_a_decision_the_file_would_not_hold_is_refused(registry_text, values) -> None:
    code, _ = _two_codes(registry_text)
    with pytest.raises(ValueError):
        fp.decide_type(registry_text, code, values, by=BY, on=ON)


def test_an_unknown_kind_and_an_unnamed_approver_are_refused(registry_text) -> None:
    code, _ = _two_codes(registry_text)
    with pytest.raises(ValueError):
        fp.decide_type(registry_text, "NO-SUCH-KIND", {"severity": 5}, by=BY, on=ON)
    with pytest.raises(ValueError):
        fp.decide_type(registry_text, code, {"severity": 5}, by="", on=ON)


def test_the_colour_rule_takes_scalars_and_nested_numbers(colour_text) -> None:
    out = fp.decide_rules(
        colour_text,
        {
            "yellow_at_severity": 4,
            "near_miss": {"fit_ft": 0.5},
            "risk_bands": {"possible": 0.35},
        },
        by=BY,
        on=ON,
    )

    got = fp.ColourRules(**yaml.safe_load(out))
    before = fp.ColourRules(**yaml.safe_load(colour_text))
    assert got.yellow_at_severity == 4
    assert got.near_miss["fit_ft"] == 0.5
    bands = {getattr(k, "value", k): v for k, v in got.risk_bands.items()}
    old = {getattr(k, "value", k): v for k, v in before.risk_bands.items()}
    assert bands["possible"] == 0.35
    assert {k: v for k, v in bands.items() if k != "possible"} == {
        k: v for k, v in old.items() if k != "possible"
    }
    assert got.status is fp.TypeStatus.approved
    assert got.approved_by == BY
    assert got.approved_on == ON


@pytest.mark.parametrize(
    "values",
    [
        {"yellow_at_severity": 11},
        {"risk_bands": {"possible": 1.5}},
        {"accept_approvals": ["anything"]},  # variances are not set from the page
    ],
)
def test_a_colour_rule_the_file_would_not_hold_is_refused(colour_text, values) -> None:
    with pytest.raises(ValueError):
        fp.decide_rules(colour_text, values, by=BY, on=ON)
