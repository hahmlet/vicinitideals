"""Every screened jurisdiction is either environmentally screened or says why not.

The Clackamas build shipped in July 2026 with no environmental overlay in any
of its eleven jurisdictions, and that fact survived five weeks of work, three
new cities and a dozen audits without once raising its hand. On 2026-09-01 it
was measured: **70,196 Clackamas lots carried one overlay touch between them,
and 2,820 green verdicts -- 28% of every green in the corpus -- were graded
with no environmental check at all.**

The reason nothing noticed is the same reason the FEMA county gap survived (see
`test_overlay_coverage.py`): an absent overlay is indistinguishable from clear
land. `ovl_<key>` is False either way, s7 reads them identically, and the
aggregate looks like a county with no wetlands. Silence is the failure mode, so
the guard has to be a test that treats silence as failure.

So: a jurisdiction the screen grades must either have an environmental overlay
pointed at it, or appear in `UNSCREENED` with a written reason and a date. A
city earns the exemption by having somebody say why, never by being left off a
list -- the same rule the frontage work settled on for `frontage_is_lot_width`.
Adding a jurisdiction to `rules.yaml` now fails this test until one or the
other is true, which is the whole point: the cost of the gap is that nobody
had to decide anything.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


#: Environmental overlay keys, as opposed to the FEMA flood pair which applies
#: everywhere by declaration and so can never evidence that a *jurisdiction*
#: was looked at. A city whose only overlay is the nationwide flood layer has
#: not been screened for wetlands, habitat or steep slope, and counting it as
#: screened is precisely the mistake this file exists to prevent.
FLOOD_EVERYWHERE = frozenset({"fema_floodway", "fema_sfha"})


#: Jurisdictions knowingly running without an environmental overlay, each with
#: the reason and the date it was written. These are debts, not decisions --
#: every line here is a city whose layers were found and whose chapter has not
#: been read. Deleting a line without wiring the overlay is how the original
#: bug comes back.
UNSCREENED: dict[str, str] = {
    "milwaukie": (
        "2026-09-01: publishes Habitat_Conservation_Areas/7, Wetlands/5, "
        "Vegetated_Corridors/6, Floodplain/9 and Willamette_Greenway/8, all "
        "verified live. MMC's natural resource chapter not yet read, so no "
        "action (carve/flag) can be assigned. 845 greens exposed."
    ),
    "west_linn": (
        "2026-09-01: publishes RiparianCI/1 + /2, WetlandInventory/1, "
        "FloodManagement/1 and SteepSlope2014/0, all verified live. CDC "
        "chapter not yet read. 355 greens exposed."
    ),
    "clackamas_unincorporated": (
        "2026-09-01: county GeoHazard FeatureServer found; the resource "
        "overlay layer has not been located and ZDO has not been read. "
        "598 greens exposed."
    ),
    "wilsonville": (
        "2026-09-01: LandUseDataset/Map___NaturalResources service confirmed, "
        "layer ids not yet enumerated. WDC chapter not read. 140 greens."
    ),
    "happy_valley": (
        "2026-09-01: publishes NaturalResourceOZ and SteepSlopesOZ. Zero "
        "greens today (all 731 lots held at review on sewer), so nothing is "
        "mis-graded yet -- but the layers exist and the chapter is unread."
    ),
    "tualatin": (
        "2026-09-01: Public/EnvironmentalExplorer confirmed, layers not "
        "enumerated. Zero greens today (20 lots at review on sewer)."
    ),
    "gladstone": (
        "2026-09-01: not audited. Zero greens today -- all 145 lots wait on "
        "signing, so no verdict rides on this. Audit when signing lands."
    ),
}


def _overlays():
    from common import load_overlays

    return load_overlays()


def _eligible_jurisdictions() -> list[str]:
    """Jurisdictions the screen actually grades: eligible, with zones."""
    import yaml

    from common import CONFIG_DIR

    doc = yaml.safe_load((CONFIG_DIR / "rules.yaml").read_text(encoding="utf-8"))
    juris = doc.get("jurisdictions", doc)
    return sorted(
        name
        for name, spec in juris.items()
        if isinstance(spec, dict)
        and spec.get("eligible", True)
        and (spec.get("zones") or [])
    )


def _environmentally_screened(name: str) -> bool:
    return any(
        spec.applies_to(name)
        for spec in _overlays().overlays
        if spec.key not in FLOOD_EVERYWHERE
    )


def test_every_graded_jurisdiction_is_screened_or_declared() -> None:
    """The assertion whose absence cost 2,820 greens their environmental check.

    A new jurisdiction fails here until somebody either wires its overlay or
    writes down why it has none. Do not satisfy this by adding a bare name to
    UNSCREENED -- the value is the reason, and a reason nobody wrote is the
    condition this test exists to detect.
    """
    silent = [
        j for j in _eligible_jurisdictions()
        if not _environmentally_screened(j) and j not in UNSCREENED
    ]
    assert not silent, (
        f"graded with no environmental overlay and no stated reason: {silent}. "
        f"Wire an overlay in overlays.yaml, or add the jurisdiction to "
        f"UNSCREENED with a dated reason and the greens at stake."
    )


def test_no_city_is_excused_without_a_reason() -> None:
    """The exemption list cannot decay into a bare list of names."""
    for name, why in UNSCREENED.items():
        assert why.strip(), name
        assert "2026-" in why, f"{name}: no date in the reason -- {why!r}"
        assert len(why) > 60, f"{name}: reason too thin to act on -- {why!r}"


def test_the_exemption_list_names_only_jurisdictions_that_still_need_it() -> None:
    """A city that gets its overlay must leave this list in the same commit.

    Otherwise the list becomes archaeology: a name sitting here long after the
    work is done reads as an outstanding gap and sends somebody to redo it.
    """
    stale = sorted(j for j in UNSCREENED if _environmentally_screened(j))
    assert not stale, (
        f"these have an overlay now and should come off UNSCREENED: {stale}"
    )


def test_oregon_city_is_the_one_clackamas_city_that_is_screened() -> None:
    """Pins today's state so the next city wired in is a deliberate change.

    Oregon City went first because it has the most greens at stake (882) and
    because its chapter answers cleanly: OCMC 17.49.030(1) makes the published
    NROD map a regulatory boundary, and 17.49.070(A) prohibits new structures
    inside it. Map plus prohibition is what a carve needs; a layer without both
    is not one.
    """
    spec = next(s for s in _overlays().overlays if s.key == "oregon_city_nrod")
    assert spec.action == "carve"
    assert spec.buffer_ft == 0
    assert "17.49.070" in spec.citation and "17.49.030" in spec.citation
    assert spec.applies_to("oregon_city")
    assert not spec.applies_to("milwaukie")
