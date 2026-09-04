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
UNSCREENED: dict[str, str] = {}
#: Emptied 2026-09-03. Gladstone and Tualatin were the last two names on it and
#: both were wired the same day. Keep the dict rather than deleting it: it is
#: the place a NEW jurisdiction lands the moment it is added to rules.yaml, and
#: the test below fails until somebody either wires the overlay or writes the
#: reason and the date here. An empty exemption list is the goal state, not a
#: dead structure.


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


def test_a_map_means_what_its_own_code_says_it_means() -> None:
    """The finding worth more than either city on its own.

    Oregon City and Happy Valley both publish a natural-resource overlay map.
    OCMC 17.49.030(1) calls its map "a regulatory boundary" and 17.49.070(A)
    prohibits structures inside it -> carve. HV LDC 16.34.060 says its map "is
    designed to be specific enough to determine whether further environmental
    review of a development proposal is necessary" -> flag. Same kind of layer,
    opposite legal weight, and nothing but the code distinguishes them.

    So an overlay's action may never be inferred from what the layer depicts.
    If this test is ever "fixed" by making the two agree, read both chapters
    first -- one of them will have changed, not both.
    """
    by_key = {s.key: s for s in _overlays().overlays}
    assert by_key["oregon_city_nrod"].action == "carve"
    assert by_key["happy_valley_nroz"].action == "flag"
    assert "17.49.030" in by_key["oregon_city_nrod"].citation
    assert "16.34.060" in by_key["happy_valley_nroz"].citation


def test_a_published_buffer_ring_is_filled_before_it_screens_anything() -> None:
    """Wilsonville's layer is a doughnut and the hole is the resource.

    SROZ_ImpactArea publishes 22 polygons, each an outer boundary with exactly
    one interior ring, and the interior ring is the Significant Resource
    Overlay Zone. Screened as fetched it flags lots BESIDE a wetland and clears
    the lot sitting IN one -- an overlay that reports the opposite of the truth
    on the lots that matter most.

    `fill_holes` is what makes it right, and it is the only overlay in the
    corpus that needs it, so this pins both halves: the flag is set here, and
    it is set nowhere else by accident.
    """
    specs = {s.key: s for s in _overlays().overlays}
    sroz = specs["wilsonville_sroz"]
    assert sroz.fill_holes is True
    assert sroz.action == "flag", (
        "WDC 4.139.03(.04) prohibits structures in the SROZ only 'if they will "
        "negatively impact significant natural resources' and 4.139.02 makes "
        "the map a test for whether a report is required -- conditional, so a "
        "review trigger, not a carve"
    )
    assert sroz.applies_to("wilsonville")
    filled = sorted(k for k, v in specs.items() if v.fill_holes)
    assert filled == ["wilsonville_sroz"], (
        f"fill_holes discards interior rings, which makes a genuine doughnut "
        f"(a lake with an island) bigger and wrong. Set it only where the hole "
        f"is known to be the resource: {filled}"
    )


def test_west_linn_carves_a_width_the_code_states_and_flags_one_it_does_not() -> None:
    """The city that publishes features and makes the code supply the geometry.

    WLCDC 32.120(A) adopts a map of water FEATURES and says in terms that it
    "is not intended to delineate the exact WRA boundaries" -- so the protected
    area is a Table 32-2 width around a centreline, not a polygon anyone drew.
    Three stream types, three different answers, and the third is the point:
    Table 32-2 has no row for a channel that is still piped, so that layer is
    flagged rather than carved at a width nobody wrote down.
    """
    specs = {s.key: s for s in _overlays().overlays}

    stream = specs["west_linn_wra_stream"]
    assert (stream.action, stream.buffer_ft) == ("carve", 65)
    assert "32-2" in stream.citation and "65" in stream.citation

    ephemeral = specs["west_linn_wra_ephemeral"]
    assert (ephemeral.action, ephemeral.buffer_ft) == ("carve", 15)
    assert ephemeral.buffer_ft < stream.buffer_ft, (
        "row F is the one width in Table 32-2 narrower than row A -- folding it "
        "into the 65 ft buffer would over-carve every ephemeral stream by 50 ft"
    )

    piped = specs["west_linn_wra_piped"]
    assert piped.action == "flag" and piped.buffer_ft == 0
    assert "row E" in piped.citation or "REOPENED" in piped.citation

    # Flood is a permit, not a prohibition: CDC 27.040 bans only what the base
    # zone already bans, plus uncontained hazardous materials.
    assert specs["west_linn_flood"].action == "flag"

    for key in ("west_linn_wra_stream", "west_linn_wra_ephemeral",
                "west_linn_wra_piped", "west_linn_rci",
                "west_linn_wetlands", "west_linn_flood"):
        assert specs[key].applies_to("west_linn"), key
        assert not specs[key].applies_to("oregon_city"), key


def test_a_borrowed_layer_keeps_its_own_jurisdiction_s_answer() -> None:
    """One regional map, two legal weights, and `source` is how both are held.

    Metro's Title 13 habitat inventory is a carve in Wood Village, which adopts
    it by reference in WVDC 430, and a flag in unincorporated Clackamas, whose
    ZDO 706.05 lists the uses prohibited in an HCA in full -- invasive planting
    and outside storage -- and a dwelling is neither. The county requires a
    development permit, not abstention. Reading the same geometry twice under
    two actions is the correct outcome; downloading it twice was not.
    """
    specs = {s.key: s for s in _overlays().overlays}

    hca = specs["clackamas_hca"]
    assert hca.source == "metro_title13" and hca.layer == "metro_title13"
    assert hca.action == "flag" and "706.05" in hca.citation
    assert hca.applies_to("clackamas_unincorporated")
    assert not hca.applies_to("wood_village")

    borrowed = specs["metro_title13"]
    assert borrowed.action == "carve" and borrowed.layer == "metro_title13"
    assert borrowed.applies_to("wood_village")
    assert not borrowed.applies_to("clackamas_unincorporated"), (
        "adding the county here would make the county's HCA a CARVE, which "
        "ZDO 706.05 does not support -- that is what `source` exists to avoid"
    )

    wqra = specs["clackamas_wqra"]
    assert wqra.source == "metro_title3" and wqra.action == "flag"
    assert "709.05" in wqra.citation


def test_every_borrowed_source_names_a_layer_something_actually_fetches() -> None:
    """A `source` typo would read as a missing layer, which is silence again."""
    import s0_acquire

    keys = {s.key for s in _overlays().overlays}
    for spec in _overlays().overlays:
        if spec.source is None:
            continue
        assert spec.source in keys, (
            f"{spec.key} borrows {spec.source!r}, which is not an overlay key"
        )
        assert f"overlay_{spec.source}" in s0_acquire.PHASE2_LAYERS, (
            f"{spec.key} borrows {spec.source!r}, which s0 never downloads"
        )


def test_one_chapter_can_hold_a_kill_and_a_flag_at_the_same_time() -> None:
    """Milwaukie's MMC 19.400 gives two answers and both of them are right.

    Every other jurisdiction in this corpus reads as a single legal weight per
    chapter. Milwaukie does not. 19.401.3 makes every land use action and all
    development in the Willamette Greenway a CONDITIONAL USE under 19.905, and
    19.401.5.B's thirteen exemptions from Greenway review are interior work,
    maintenance, driveways and 200 sq ft accessory structures -- a dwelling is
    on none of them. Discretionary approval is out of reach for a by-right
    screen, so the greenway KILLS: it is the only city overlay outside
    Portland's e-zones that does.

    Four sections later, 19.402.5.A prohibits "new structures, development, or
    landscaping activity other than those allowed by Section 19.402" inside a
    WQR or HCA -- which reads exactly like Oregon City's carve until Table
    19.402.3.K routes HCA work meeting the 19.402.11.D nondiscretionary
    standards, and limited WQR disturbance FOR NEW DWELLING UNITS under
    19.402.6.B, to Type I review. Type I is ministerial. What the chapter
    imposes is a disturbance budget with mitigation planting, which this screen
    cannot size, so the resource layers FLAG.

    A prohibition followed by "other than those allowed by this section" is not
    a prohibition until you have read what the section allows. That is the
    lesson worth keeping when the next chapter opens with the same sentence.
    """
    specs = {s.key: s for s in _overlays().overlays}

    greenway = specs["milwaukie_greenway"]
    assert greenway.action == "kill"
    assert "19.401.3" in greenway.citation and "19.905" in greenway.citation
    assert greenway.applies_to("milwaukie")

    for key in ("milwaukie_hca", "milwaukie_wqr", "milwaukie_wetlands"):
        spec = specs[key]
        assert spec.action == "flag", (
            f"{key} is a flag because Table 19.402.3.K reaches Type I review "
            f"for new dwellings; carving it would claim the chapter forbids "
            f"what it actually meters"
        )
        assert spec.applies_to("milwaukie")

    assert "19.402" in specs["milwaukie_hca"].citation
    assert "19.402.6.B" in specs["milwaukie_wqr"].citation


def test_the_applicability_band_is_not_the_restriction() -> None:
    """Milwaukie publishes its own 100 ft trigger band and we do not screen it.

    NR_100ft_Compliance is a single polygon of every property within 100 ft of
    a WQR or HCA -- 19.402.3.A's applicability reach, drawn by the city. It is
    tempting precisely because the flags here fire on touch only and therefore
    under-flag by up to 100 ft.

    It is still the wrong layer. Table 19.402.3 gives a nonexempt activity that
    sits outside the resource but inside the band a construction management
    plan and nothing else -- "Comply with Remainder of Section 19.402: No".
    Screening it would hold lots out of green for paperwork, which is the
    opposite error from the one this file was written to catch and no less
    wrong. Being subject to a chapter is not being restrained by it.
    """
    import s0_acquire

    fetched = set(s0_acquire.PHASE2_LAYERS)
    assert "overlay_milwaukie_hca" in fetched
    assert "overlay_milwaukie_nr_100ft" not in fetched
    assert not any(
        "NR_100ft" in spec.get("url", "") for spec in s0_acquire.PHASE2_LAYERS.values()
    ), (
        "the 100 ft band is applicability, not restriction -- if a future "
        "reader wants it, it belongs in a column that says 'needs a "
        "construction management plan', not in the flag that costs a green"
    )
