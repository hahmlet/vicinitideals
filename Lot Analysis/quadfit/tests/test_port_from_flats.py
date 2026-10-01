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
    assert placeholders == 16, "the six Washington rows with an unread yard, three or two yards each"
