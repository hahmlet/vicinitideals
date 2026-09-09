"""A ruling that says it became a rule, checked against the rule.

The register has always carried ``encoded_as`` and has always described it as
"checkable against the encoding rather than taken on trust". Nothing checked
it. These are the assertions that make it true, and the load-bearing one is
``test_every_encoded_footnote_still_finds_its_rule`` -- it goes red the day
somebody deletes a variant a closed footnote was standing on, which is the
failure the whole footnote subsystem exists to prevent and the only one it
could not see.

The rest are about the number check, because the first run of this module
reported eleven broken claims and every single one was a false alarm: a zone
code read as a figure, a band bound the reader never looked at, a table number.
A check that cries wolf eleven times out of eleven trains people to close the
tab.
"""

from __future__ import annotations

import pytest

from flats.encode.applied import (
    Applied,
    Claim,
    _mask,
    _numbers_of,
    applied,
)
from datetime import date

from flats.rules.model import Band, Provenance, Value, Variant

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def rows() -> list[Applied]:
    return applied()


# --- the ledger -------------------------------------------------------------


def test_every_encoded_footnote_still_finds_its_rule(rows) -> None:
    """The check the register promised and never performed.

    ``broken`` means a ruling names a field, condition or figure the layer no
    longer has. A closed decision resting on a deleted variant reads exactly
    like a closed decision resting on a live one, and this is the only thing
    that tells them apart.
    """
    broken = [r for r in rows if r.state == "broken"]
    assert not broken, "\n".join(
        f"{r.note.layer} {r.mark}: {r.note.encoded_as!r} -> "
        + ", ".join(f"{c.kind} {c.token!r}" for c in r.failures)
        for r in broken
    )


def test_the_register_and_the_ledger_agree_on_how_many_are_encoded(rows) -> None:
    """46 as of 2026-09-08. A number that moves means a footnote was ruled or
    un-ruled, which is a thing to notice rather than a thing to absorb.

    45 -> 46 on 2026-09-08: Clackamas ZDO Table 316-1 note 8, the sentence the
    five rural refusals rest on. "Each lot of record may be developed with only
    one of the following", and the following is five things ending at a duplex.
    It reaches FF10, FU10, RA1, RA2 and RRFF5 and confirms in all five, which
    is what an `encoded` ruling is supposed to look like: a footnote that did
    not qualify a number so much as become one.
    """
    assert len(rows) == 46


def test_no_ruling_is_pure_prose(rows) -> None:
    """A sentence naming no field, condition or figure cannot be checked at
    all, and a register full of them would grade itself clean."""
    assert [r.mark for r in rows if r.state == "unreadable"] == []


def test_a_ruling_found_outside_its_own_region_is_reported_not_hidden(rows) -> None:
    """Happy Valley's 16.42.030 note is encoded on every zone in the layer
    while its own block sits under one table. That is not a defect and it is
    not confirmation either, so it gets its own word."""
    elsewhere = [r for r in rows if r.state == "elsewhere"]
    assert len(elsewhere) == 1
    assert elsewhere[0].note.layer == "or/clackamas/happy-valley"


# --- reading a figure out of prose ------------------------------------------


@pytest.mark.parametrize(
    "text, zones, gone",
    [
        ("MDR-24 min_lot_width_ft variants", ("MDR-24",), "24"),
        ("R-7.5 max_density_du_per_acre exempt", ("R-7.5",), "7.5"),
        ("LR 7.5 and LR 12, the unit_lots band", ("LR 7.5", "LR 12"), "12"),
        ("none of it appears in Table 210-3 itself", (), "210"),
        ("Pursuant to Section 16.42.030", (), "16.42.030"),
    ],
)
def test_a_name_is_never_read_as_a_figure(text, zones, gone) -> None:
    """Every false alarm in this module's first run was one of these.

    "MDR-24" is not a claim that something equals 24, and a check that cannot
    say so has no business reporting a ruling broken.
    """
    assert gone not in _mask(text, zones)


def test_masking_leaves_the_figures_alone() -> None:
    masked = _mask("MDR-24 min_lot_width_ft variants, when [unit_lots] 42 ft", ("MDR-24",))
    assert "42" in masked


PROV = Provenance(
    cite="X 1.00",
    url="https://example.invalid/x",
    retrieved=date(2026, 9, 7),
    quote="or/x/1.txt#L1",
)


def test_a_band_bound_is_a_figure_a_ruling_may_quote() -> None:
    """"exempt below 11,000 sq ft" is a claim about 11,000, and 11,000 lives
    on the band rather than on the value. Reading `value` alone reported three
    Gresham rulings broken over exactly this."""
    variant = Variant(
        exempt=True, band=Band(measure="lot_sqft", less_than=11000), prov=PROV
    )
    assert 11000.0 in set(_numbers_of(variant))


def test_the_figure_a_sentence_states_counts_as_much_as_the_one_it_means() -> None:
    """`per_dwelling` carries what the page says where `value` carries what
    the field means, and a ruling quotes the page."""
    value = Value(name="min_lot_sqft", value=6000, per_dwelling=1500, prov=PROV)
    assert {6000.0, 1500.0} <= set(_numbers_of(value))


def test_a_flag_is_not_a_figure() -> None:
    """`exempt: true` must not read as the number 1."""
    assert list(_numbers_of(Variant(exempt=True, prov=PROV))) == []


# --- how a claim is graded --------------------------------------------------


def _applied(*claims: Claim) -> Applied:
    from flats.encode.dispositions import Note

    note = Note(layer="or/x", doc="or/x/1.txt", line=1, mark="1", text="t", state="encoded")
    return Applied(note=note, zones_named=(), claims=claims)


@pytest.mark.parametrize(
    "claims, state",
    [
        ((Claim("field", "a", "R.a", True),), "confirmed"),
        ((Claim("field", "a", "R.a", False),), "elsewhere"),
        ((Claim("field", "a", "", False),), "broken"),
        # One broken claim outranks any number of confirmed ones: a ruling is
        # only as good as the part of it that no longer resolves.
        (
            (Claim("field", "a", "R.a", True), Claim("number", "9", "", False)),
            "broken",
        ),
        ((Claim("field", "a", "R.a", True), Claim("number", "9", "S.a", False)), "elsewhere"),
        ((), "unreadable"),
    ],
)
def test_the_state_is_the_worst_thing_that_happened_to_any_claim(claims, state) -> None:
    assert _applied(*claims).state == state
