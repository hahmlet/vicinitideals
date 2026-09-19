"""The failure-state warning: every rule fires once, and a fresh copy is quiet.

The banner is computed from rows already in the database, never from a live
request; these tests hand it literals and read the notices back.
"""

from __future__ import annotations

import datetime as dt

from flats.ingest.status import (
    CANDIDATE_WAIT_DAYS,
    PROBE_GAP_DAYS,
    STALE_DAYS,
    Notice,
    Probe,
    Snapshot,
    assess,
    footer,
    holes,
)

TODAY = dt.date(2026, 10, 1)


def snap(
    id: int = 1,
    date: dt.date = dt.date(2026, 9, 18),
    status: str = "current",
    registered: dt.date | None = None,
    manifest: dict | None = None,
    release: str | None = "2026_08",
) -> Snapshot:
    return Snapshot(
        id=id,
        snapshot_date=date,
        status=status,
        registered_at=registered or date,
        rlis_release=release,
        manifest=manifest if manifest is not None else {"datasets": {"rlis_taxlots": {"status": "acquired"}}},
    )


def probe(date: dt.date = dt.date(2026, 9, 20), *findings: tuple[str, str]) -> Probe:
    return Probe(
        ran_at=date,
        status="warn" if findings else "ok",
        findings=tuple({"key": k, "finding": f, "detail": ""} for k, f in findings),
    )


def codes(notices: list[Notice]) -> list[tuple[str, str]]:
    return [(n.level, n.code) for n in notices]


def test_a_fresh_checked_copy_raises_nothing() -> None:
    current = snap()
    out = assess(current=current, latest=current, candidates=[], probes=[probe()], today=TODAY)
    assert out == []
    assert footer(current, [probe()]) == "County map copy: RLIS 2026_08 + ArcGIS layers, taken 2026-09-18; sources checked 2026-09-20."


def test_no_copy_at_all_is_red_and_the_footer_says_so() -> None:
    out = assess(current=None, latest=None, candidates=[], probes=[], today=TODAY)
    assert codes(out) == [("red", "none"), ("amber", "unchecked")]
    assert footer(None, []) == "County map copy: none recorded."


def test_a_copy_older_than_a_missed_quarter_is_red() -> None:
    old = snap(date=TODAY - dt.timedelta(days=STALE_DAYS + 1))
    out = assess(current=old, latest=old, candidates=[], probes=[probe(TODAY)], today=TODAY)
    assert codes(out) == [("red", "stale")]
    assert f"{STALE_DAYS + 1} days old" in out[0].text and "2026-06-02" in out[0].text

    fine = snap(date=TODAY - dt.timedelta(days=STALE_DAYS))
    assert assess(current=fine, latest=fine, candidates=[], probes=[probe(TODAY)], today=TODAY) == []


def test_a_download_with_a_hole_is_red_and_names_the_hole() -> None:
    manifest = {
        "datasets": {
            "rlis_taxlots": {"status": "acquired"},
            "zoning_gladstone": {"status": "refused", "error": "ZONE missing"},
            "util_sewer_wood_village": {"status": "failed", "error": "Invalid URL"},
            "overlay_fema_flood": {"status": "acquired", "unfetched_ids": [1, 2, 3]},
            "dem_3dep": {"status": "deferred"},
            "rlis_ugb": {"status": "retired"},
        }
    }
    assert holes(manifest) == [
        "overlay_fema_flood (3 features unfetched)",
        "util_sewer_wood_village (failed)",
        "zoning_gladstone (refused)",
    ]
    current = snap(id=1, date=dt.date(2026, 9, 18))
    latest = snap(id=2, date=dt.date(2026, 9, 28), status="candidate", manifest=manifest)
    out = assess(current=current, latest=latest, candidates=[latest], probes=[probe(TODAY)], today=TODAY)
    assert codes(out) == [("red", "incomplete")]
    assert "zoning_gladstone (refused)" in out[0].text
    assert "The copy in use is from 2026-09-18" in out[0].text


def test_the_copy_in_use_with_a_hole_says_it_is_the_copy_in_use() -> None:
    manifest = {"datasets": {"rlis_taxlots": {"status": "failed", "error": "range refused"}}}
    current = snap(manifest=manifest)
    out = assess(current=current, latest=current, candidates=[], probes=[probe(TODAY)], today=TODAY)
    assert codes(out) == [("red", "incomplete")]
    assert out[0].text.startswith("The copy in use (2026-09-18) did not complete")


def test_a_failed_attempt_is_red_and_the_copy_in_use_is_named() -> None:
    current = snap(id=1)
    failed = snap(id=2, date=dt.date(2026, 9, 30), status="failed", manifest={})
    out = assess(current=current, latest=failed, candidates=[], probes=[probe(TODAY)], today=TODAY)
    assert codes(out) == [("red", "failed")]
    assert "2026-09-30" in out[0].text and "in use is from 2026-09-18" in out[0].text


def test_a_source_that_changed_on_its_own_side_is_red() -> None:
    current = snap()
    seen = probe(dt.date(2026, 9, 25), ("util_sewer_wood_village", "moved"), ("zoning_gladstone", "count_drift"))
    out = assess(current=current, latest=current, candidates=[], probes=[seen], today=TODAY)
    assert codes(out) == [("red", "source_changed")]
    assert "util_sewer_wood_village" in out[0].text and "zoning_gladstone" in out[0].text
    assert "copy in use is unaffected" in out[0].text


def test_a_registry_edited_after_the_copy_is_red_and_says_it_was_us() -> None:
    current = snap()
    seen = probe(dt.date(2026, 9, 25), ("overlay_hv_nroz", "registry_changed"), ("overlay_hv_slope", "registry_changed"))
    out = assess(current=current, latest=current, candidates=[], probes=[seen], today=TODAY)
    assert codes(out) == [("red", "registry_changed")]
    assert "overlay_hv_nroz" in out[0].text and "changed after the copy was taken" in out[0].text
    assert "on its own side" not in out[0].text

    both = probe(dt.date(2026, 9, 25), ("overlay_hv_nroz", "registry_changed"), ("zoning_gladstone", "moved"))
    out = assess(current=current, latest=current, candidates=[], probes=[both], today=TODAY)
    assert codes(out) == [("red", "source_changed"), ("red", "registry_changed")]


def test_a_layer_that_did_not_answer_is_amber_once_and_red_twice() -> None:
    current = snap()
    once = probe(dt.date(2026, 9, 25), ("zoning_portland", "unreachable"))
    out = assess(current=current, latest=current, candidates=[], probes=[once], today=TODAY)
    assert codes(out) == [("amber", "unreachable")]

    before = probe(dt.date(2026, 8, 25), ("zoning_portland", "unreachable"))
    out = assess(current=current, latest=current, candidates=[], probes=[once, before], today=TODAY)
    assert codes(out) == [("red", "unreachable")]
    assert "last two monthly checks" in out[0].text

    # A different layer down last month is not the same layer down twice.
    other = probe(dt.date(2026, 8, 25), ("zoning_gresham", "unreachable"))
    out = assess(current=current, latest=current, candidates=[], probes=[once, other], today=TODAY)
    assert codes(out) == [("amber", "unreachable")]


def test_a_new_release_is_amber_until_a_snapshot_follows_it() -> None:
    current = snap()
    seen = probe(dt.date(2026, 11, 5), ("https://portal/items/x/data", "new_release"))
    out = assess(current=current, latest=current, candidates=[], probes=[seen], today=dt.date(2026, 11, 6))
    assert codes(out) == [("amber", "new_release")]

    taken = snap(id=2, date=dt.date(2026, 11, 10), status="candidate")
    out = assess(current=current, latest=taken, candidates=[taken], probes=[seen], today=dt.date(2026, 11, 11))
    assert codes(out) == []


def test_a_candidate_waiting_too_long_is_amber() -> None:
    current = snap(id=1)
    cand = snap(id=2, date=dt.date(2026, 9, 28), status="candidate", registered=TODAY - dt.timedelta(days=CANDIDATE_WAIT_DAYS + 1))
    out = assess(current=current, latest=cand, candidates=[cand], probes=[probe(TODAY)], today=TODAY)
    assert codes(out) == [("amber", "waiting")]
    assert f"{CANDIDATE_WAIT_DAYS + 1} days" in out[0].text

    fresh = snap(id=2, date=dt.date(2026, 9, 28), status="candidate", registered=TODAY)
    assert assess(current=current, latest=fresh, candidates=[fresh], probes=[probe(TODAY)], today=TODAY) == []


def test_a_check_that_has_not_run_lately_is_amber() -> None:
    current = snap()
    stale = probe(TODAY - dt.timedelta(days=PROBE_GAP_DAYS + 1))
    out = assess(current=current, latest=current, candidates=[], probes=[stale], today=TODAY)
    assert codes(out) == [("amber", "unchecked")]
    out = assess(current=current, latest=current, candidates=[], probes=[], today=TODAY)
    assert codes(out) == [("amber", "unchecked")]
    assert "not run yet" in out[0].text


def test_a_check_that_did_not_complete_is_said_and_does_not_count_as_a_check() -> None:
    current = snap()
    broken = Probe(
        ran_at=dt.date(2026, 9, 30),
        status="failed",
        findings=({"key": "-", "finding": "failed", "detail": "ConnectError: no route to host"},),
    )
    out = assess(current=current, latest=current, candidates=[], probes=[broken], today=TODAY)
    assert codes(out) == [("amber", "check_failed"), ("amber", "unchecked")]
    assert "2026-09-30" in out[0].text and "no route to host" in out[0].text
    # The footer names the last check that completed, not the one that broke.
    assert footer(current, [broken]) == "County map copy: RLIS 2026_08 + ArcGIS layers, taken 2026-09-18."
    assert footer(current, [broken, probe(dt.date(2026, 8, 30))]).endswith("sources checked 2026-08-30.")

    # The month before completed: the clock runs from that one.
    out = assess(current=current, latest=current, candidates=[], probes=[broken, probe(dt.date(2026, 9, 1))], today=TODAY)
    assert codes(out) == [("amber", "check_failed")]


def test_red_comes_before_amber_whatever_the_order_found() -> None:
    old = snap(date=TODAY - dt.timedelta(days=STALE_DAYS + 30))
    cand = snap(id=2, date=dt.date(2026, 9, 1), status="candidate", registered=dt.date(2026, 9, 1))
    out = assess(current=old, latest=cand, candidates=[cand], probes=[], today=TODAY)
    assert [n.level for n in out] == ["red", "amber", "amber"]
    assert codes(out)[0] == ("red", "stale")
