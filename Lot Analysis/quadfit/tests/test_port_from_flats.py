"""The Washington County rows are the corpus's, and only the corpus's.

`port_from_flats.py` writes them; these tests hold rules.yaml to what it would
write today, so a corpus edit that nobody re-ported fails here rather than
screening Washington lots against yesterday's reading, and pin the two rules
that keep the port on the safe side: the largest limb of every yard and
minimum, and a placeholder for a yard nobody has read, named in the row.
"""

from __future__ import annotations

from types import SimpleNamespace

import port_from_flats as pf
import pytest

from flats.rules.loader import load_rules


@pytest.fixture(scope="module")
def layers():
    return load_rules()


def test_rules_yaml_holds_exactly_what_the_corpus_ports_to(layers) -> None:
    text = pf.RULES.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert pf.BEGIN in text and pf.END in text
    assert pf.splice(text, pf.render(layers)) == text, (
        "the corpus moved since the Washington rows were written: "
        'run python "Lot Analysis/quadfit/port_from_flats.py" --write'
    )


def _value(value, *variants, exempt=False):
    return SimpleNamespace(value=value, exempt=exempt, variants=tuple(variants))


def test_every_limb_counts_and_an_exempt_one_does_not() -> None:
    v = _value(10, _value(20), _value(None), _value(99, exempt=True))
    assert pf._limbs(v) == [10.0, 20.0]
    assert pf._limbs(_value(0, exempt=True)) == []
    assert pf._limbs(None) == []


def test_a_variant_that_allows_the_pod_opens_the_zone_to_measurement() -> None:
    assert pf._allowed(_value(True))
    assert pf._allowed(_value(False, _value(True)))
    assert not pf._allowed(_value(False, _value(False)))
    assert not pf._allowed(None)


def test_each_row_takes_the_strict_limb_and_names_its_placeholders(layers) -> None:
    checked = placeholders = 0
    for t in pf.TARGETS:
        layer = layers[t.layer_id]
        yards = pf.largest_yards(layer)
        for name in layer.zones:
            row = pf.zone_row(layer, name, t.layer_id, yards)
            assert row["confidence"] == "needs_verification"
            if not row["quadplex_allowed"]:
                continue
            get = pf._getter(layer, name)
            for mine, theirs in pf.MIRRORED.items():
                limbs = pf._limbs(get(theirs))
                if not limbs:
                    continue
                want = min(limbs) if mine in pf.SMALLER_BINDS else max(limbs)
                assert row[mine] == want, (t.slug, name, mine)
                checked += 1
            for yard in pf.YARDS:
                assert yard in row, (t.slug, name, yard)
                if not pf._limbs(get(yard)) and row[yard] != 0:
                    assert "PLACEHOLDER" in row["notes"] and yard in row["notes"], (t.slug, name, yard)
                    assert row[yard] == yards[yard]
                    placeholders += 1
    assert checked > 100, checked
    # 16 -> 25 on 2026-10-19: the rows the ORS 197A.400 lane admits (FOLLOWUPS 85)
    # carry their unread yards as placeholders the same way.
    # 25 -> 23 on 2026-11-08 (FOLLOWUPS 147, f4ac56b0): Washington County TO:R24-40
    # and TO:R40-80 read their front yard, Table B(2)'s printed "None" frontage
    # minimum (375-10.txt#L342), so it is exempt (0) rather than a placeholder.
    assert placeholders == 23, "the six Washington rows and the clear-objective rows with an unread yard"


#: Rows placed by hand outside the ported region that mirror an adopted
#: amendment rather than the codified block (rules.yaml ``corpus_amendment``).
#: Portland CI1 since RICAP 11 (2026-11-01, FOLLOWUPS 155): a home there is
#: built to RM1's standards.
#: Gladstone R7.2, R10 and C1 on Ord. 1545 (in force 2026-08-13, FOLLOWUPS
#: 156): R7.2's own amended table, R10 copying it, C1 through its like: R7.2.
AMENDED_ROWS = {
    ("portland", "CI1"): ("or/multnomah/portland", "ricap11"),
    ("gladstone", "R7.2"): ("or/clackamas/gladstone", "ord1545"),
    ("gladstone", "R10"): ("or/clackamas/gladstone", "ord1545"),
    ("gladstone", "C1"): ("or/clackamas/gladstone", "ord1545"),
}


def test_a_row_mirroring_an_amendment_is_what_the_port_makes_of_it(layers) -> None:
    """The CI1 row is the port's rule run on RICAP 11's block, number for number.

    The codified CI1 block still refuses the home and prints 15 ft setbacks;
    a row read off it would measure the wrong envelope or none. The amended
    block adopts RM1 whole, so the row must come out as RM1's.
    """
    import yaml

    top = yaml.safe_load(pf.RULES.read_text(encoding="utf-8"))["jurisdictions"]
    named = {
        (j, z["zone"]): z["corpus_amendment"]
        for j, spec in top.items() if isinstance(spec, dict)
        for z in spec.get("zones") or [] if z.get("corpus_amendment")
    }
    assert named == {k: v[1] for k, v in AMENDED_ROWS.items()}
    for (slug, zone), (layer_id, amendment) in AMENDED_ROWS.items():
        shipped = next(z for z in top[slug]["zones"] if z["zone"] == zone)
        want = pf.amended_zone_row(layers[layer_id], zone, layer_id, amendment)
        for key in ("quadplex_allowed", "corpus_amendment", *pf.MIRRORED):
            assert shipped.get(key) == want.get(key), (slug, zone, key)
    ci1 = pf.amended_zone_row(layers["or/multnomah/portland"], "CI1", "or/multnomah/portland", "ricap11")
    rm1 = pf.zone_row(layers["or/multnomah/portland"], "RM1", "or/multnomah/portland",
                      pf.largest_yards(layers["or/multnomah/portland"]))
    assert {k: ci1.get(k) for k in pf.MIRRORED} == {k: rm1.get(k) for k in pf.MIRRORED}
    assert ci1["quadplex_allowed"] is True
    # The codified block is still the codified block: refused, 15 ft yards.
    codified = pf.zone_row(layers["or/multnomah/portland"], "CI1", "or/multnomah/portland",
                           pf.largest_yards(layers["or/multnomah/portland"]))
    assert codified["quadplex_allowed"] is False


def test_an_amendment_the_corpus_does_not_carry_is_an_error(layers) -> None:
    with pytest.raises(LookupError):
        pf.amended_zone_row(layers["or/multnomah/portland"], "CI1", "or/multnomah/portland", "ricap99")
