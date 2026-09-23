"""The county copy's ledger: registering a snapshot, writing the monthly check.

``app.services.flats_refresh`` is what the scripts, the Celery task and the
Lots pages share, so what is held here is the row-level contract: a manifest
becomes one row with its counts lifted out; the copy in use cannot be
demoted by re-registering; a check that cannot complete is still a row.
The banner rules themselves are tested without a database in
``flats/tests/test_status.py``; the probe's findings in ``test_probe.py``.

The promotion half (plan phase 4) is held the same way: the gate reads the
row, a standing gate refuses without a written override, the flip touches
exactly the three rows it names, a decision about ground that moved is
marked, a rollback puts the previous copy back, drift puts every move to a
cause, and prune never touches the copy in use or a candidate.

A re-screen of the copy in use (the rules or the screen changed, the ground
did not) is a candidate RUN on the current copy: its gate is its own drift
against the run in use, two runs of one copy put a move to the rules or the
screen and never to the ground, promoting it makes it the default while the
run it replaces stays complete, and rolling it back puts that run back.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import (
    FlatsDesign,
    FlatsLot,
    FlatsLotChange,
    FlatsLotResult,
    FlatsProbe,
    FlatsReviewDecision,
    FlatsRun,
    FlatsSnapshot,
)
from app.services import flats_refresh
from app.services.flats_refresh import (
    PromotionBlocked,
    PromotionError,
    RegisterError,
    attach_report,
    blocks,
    drift,
    drift_markdown,
    facts_moved,
    gate,
    promote,
    promote_run,
    prune,
    refresh_notices,
    register_snapshot,
    rollback,
    rollback_run,
    run_in_use,
    run_probe,
    warns,
)
from flats.ingest.acquire import _spec_sha
from flats.ingest.sources import load_pipeline

pytestmark = pytest.mark.asyncio

ZONING = "https://example.gov/arcgis/rest/services/Zoning/MapServer/0"
RLIS = "https://example.gov/sharing/rest/content/items/abc/data"
REGISTRY = f"""
working_srid: 2913
display_srid: 4326
jurisdictions:
  or/multnomah/portland: true
datasets:
  rlis_taxlots:
    kind: rlis_zip
    label: Metro RLIS taxlots
    provides: lots
    url: {RLIS}
    member: TAXLOTS/taxlots_public.shp
    fields: [TLID, COUNTY]
    serves: [or/multnomah, or/clackamas]
  zoning_portland:
    kind: arcgis
    label: Portland zoning
    provides: zoning
    url: {ZONING}
    fields: [ZONE]
    zone_field: ZONE
    serves: [or/multnomah/portland]
"""


def _pipeline(tmp_path):
    path = tmp_path / "pipeline.yaml"
    path.write_text(REGISTRY, encoding="utf-8")
    return load_pipeline(path)


def _manifest(pipe, snapshot: str = "2026-09-18") -> dict:
    ds = pipe.datasets
    return {
        "snapshot": snapshot,
        "working_srid": 2913,
        "archives": {RLIS: {"release": "2026_08", "modified": "2026-08-26", "size": 1_067_276_384, "members": 426}},
        "datasets": {
            "rlis_taxlots": {
                "status": "acquired", "features": 453_782, "retrieved_at": "2026-09-18T20:01:00Z",
                "spec_sha256": _spec_sha(ds["rlis_taxlots"]),
            },
            "zoning_portland": {
                "status": "acquired", "features": 15_700, "retrieved_at": "2026-09-18T19:40:00Z",
                "spec_sha256": _spec_sha(ds["zoning_portland"]), "unfetched_ids": [4, 5],
            },
            "zoning_gladstone": {"status": "refused", "error": "ZONE missing", "retrieved_at": "2026-09-18T19:41:00Z"},
        },
    }


def _county() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?", 1)[0]
        if url.endswith("/query"):
            return httpx.Response(200, json={"count": 15_702})
        if url.endswith("/items/abc"):
            return httpx.Response(200, json={"name": "rlis_free_quarter.zip", "modified": 1787768567000, "size": 1_067_276_384})
        return httpx.Response(200, json={"name": "layer", "fields": [{"name": "OBJECTID"}, {"name": "ZONE"}]})

    return httpx.Client(transport=httpx.MockTransport(handler))


# --- registering ------------------------------------------------------------


async def test_a_manifest_becomes_one_row_with_its_counts_lifted_out(session: AsyncSession, tmp_path) -> None:
    pipe = _pipeline(tmp_path)

    row = await register_snapshot(session, _manifest(pipe), host="137", status="candidate", notes="first")
    await session.commit()

    assert (row.snapshot_date, row.host, row.status, row.rlis_release) == (dt.date(2026, 9, 18), "137", "candidate", "2026_08")
    assert row.acquired_at == dt.datetime(2026, 9, 18, 20, 1, tzinfo=dt.UTC)
    assert row.counts["features"] == 453_782 + 15_700
    assert row.counts["by_status"] == {"acquired": 2, "refused": 1}
    assert row.counts["datasets"]["zoning_portland"] == {"status": "acquired", "features": 15_700, "unfetched": 2}
    assert row.manifest["datasets"]["zoning_gladstone"]["error"] == "ZONE missing"
    assert row.notes == "first"


async def test_re_registering_the_same_copy_updates_it_rather_than_doubling_it(session: AsyncSession, tmp_path) -> None:
    pipe = _pipeline(tmp_path)
    first = await register_snapshot(session, _manifest(pipe), host="137", status="candidate")
    await session.commit()
    doc = _manifest(pipe)
    doc["datasets"]["zoning_gladstone"] = {"status": "acquired", "features": 1_200, "retrieved_at": "2026-09-19T08:00:00Z"}

    again = await register_snapshot(session, doc, host="137", status="candidate")
    await session.commit()

    assert again.id == first.id
    assert again.counts["by_status"] == {"acquired": 3}
    assert again.acquired_at == dt.datetime(2026, 9, 19, 8, 0, tzinfo=dt.UTC)
    assert len((await session.execute(select(FlatsSnapshot))).scalars().all()) == 1


async def test_the_copy_in_use_is_neither_demoted_nor_doubled_by_registering(session: AsyncSession, tmp_path) -> None:
    pipe = _pipeline(tmp_path)
    in_use = await register_snapshot(session, _manifest(pipe, "2026-07-28"), host="137", status="current")
    await session.commit()

    with pytest.raises(RegisterError, match="copy in use"):
        await register_snapshot(session, _manifest(pipe, "2026-07-28"), host="137", status="candidate")
    with pytest.raises(RegisterError, match="already the copy in use"):
        await register_snapshot(session, _manifest(pipe, "2026-09-18"), host="137", status="current")
    with pytest.raises(RegisterError, match="status must be"):
        await register_snapshot(session, _manifest(pipe, "2026-09-18"), host="137", status="retired")

    # Re-registering the copy in use as current is fine: its manifest is updated.
    same = await register_snapshot(session, _manifest(pipe, "2026-07-28"), host="137", status="current")
    assert same.id == in_use.id and same.status == "current"


async def test_a_manifest_without_a_date_is_refused(session: AsyncSession) -> None:
    with pytest.raises(RegisterError, match="snapshot date"):
        await register_snapshot(session, {"datasets": {}}, host="137", status="candidate")


async def test_a_report_section_is_stored_on_the_row_and_replaced_whole(session: AsyncSession, tmp_path) -> None:
    pipe = _pipeline(tmp_path)
    row = await register_snapshot(session, _manifest(pipe), host="137", status="candidate")
    await session.commit()

    await attach_report(session, row.id, "delta", {"rows": 17, "by_kind": {"split": 5}})
    await attach_report(session, row.id, "drift", {"moves": 3})
    await attach_report(session, row.id, "delta", {"rows": 18, "by_kind": {"split": 6}})
    await session.commit()
    session.expunge_all()

    stored = await session.get(FlatsSnapshot, row.id)
    assert stored is not None
    assert stored.report == {"delta": {"rows": 18, "by_kind": {"split": 6}}, "drift": {"moves": 3}}
    with pytest.raises(RegisterError, match="no snapshot 999"):
        await attach_report(session, 999, "delta", {})


# --- the monthly check -------------------------------------------------------


async def test_the_check_writes_one_row_against_the_copy_in_use(session: AsyncSession, tmp_path) -> None:
    pipe = _pipeline(tmp_path)
    current = await register_snapshot(session, _manifest(pipe), host="137", status="current")
    await session.commit()

    row = await run_probe(session, client=_county(), pipeline=pipe)
    await session.commit()

    assert row.snapshot_id == current.id
    assert row.status == "ok"
    assert sorted(f["key"] for f in row.findings) == sorted([RLIS, "zoning_portland"])
    assert all(f["finding"] == "ok" for f in row.findings)
    assert row.seconds is not None
    assert len((await session.execute(select(FlatsProbe))).scalars().all()) == 1


async def test_a_check_with_no_copy_in_use_is_a_failed_row_not_an_error(session: AsyncSession, tmp_path) -> None:
    pipe = _pipeline(tmp_path)
    await register_snapshot(session, _manifest(pipe), host="137", status="candidate")
    await session.commit()

    row = await run_probe(session, client=_county(), pipeline=pipe)
    await session.commit()

    assert row.status == "failed" and row.snapshot_id is None
    assert "no county map copy is in use" in row.findings[0]["detail"]


async def test_a_copy_in_use_without_a_manifest_is_checked_through_the_newest_copy_that_has_one(
    session: AsyncSession, tmp_path
) -> None:
    pipe = _pipeline(tmp_path)
    # Run 2's copy, as migration 0132 registers it: current, no manifest.
    bare = FlatsSnapshot(snapshot_date=dt.date(2026, 7, 28), host="137", status="current", manifest={}, counts={})
    session.add(bare)
    await session.flush()
    with_manifest = await register_snapshot(session, _manifest(pipe), host="137", status="candidate")
    await session.commit()

    row = await run_probe(session, client=_county(), pipeline=pipe)

    assert row.status == "ok" and row.snapshot_id == with_manifest.id
    assert row.findings[0]["finding"] == "ok"
    assert "compared against snapshot" in row.findings[0]["detail"] and "recorded no manifest" in row.findings[0]["detail"]
    assert {f["key"] for f in row.findings[1:]} == {RLIS, "zoning_portland"}

    # With no copy holding a manifest at all, the check says so and fails.
    await session.delete(with_manifest)
    await session.commit()
    row = await run_probe(session, client=_county(), pipeline=pipe)
    assert row.status == "failed" and "no other copy has one" in row.findings[0]["detail"]


async def test_a_check_that_breaks_is_a_failed_row_with_the_reason(session: AsyncSession, tmp_path, monkeypatch) -> None:
    pipe = _pipeline(tmp_path)
    current = await register_snapshot(session, _manifest(pipe), host="137", status="current")
    await session.commit()

    def broken():
        raise FileNotFoundError("pipeline.yaml")

    monkeypatch.setattr(flats_refresh, "load_pipeline", broken)
    row = await run_probe(session, client=_county())

    assert row.status == "failed" and row.snapshot_id == current.id
    assert row.findings == [{"key": "-", "finding": "failed", "detail": "FileNotFoundError: pipeline.yaml"}]


# --- the banner, from rows -------------------------------------------------


async def test_the_banner_reads_the_rows_it_was_given(session: AsyncSession, tmp_path) -> None:
    pipe = _pipeline(tmp_path)
    current = await register_snapshot(session, _manifest(pipe, "2026-07-28"), host="137", status="current")
    waiting = await register_snapshot(session, _manifest(pipe, "2026-09-18"), host="137", status="candidate")
    await session.commit()
    checked = await run_probe(session, client=_county(), pipeline=pipe)
    await session.commit()

    found = await refresh_notices(session, today=dt.date(2026, 10, 1))

    assert found.current is not None and found.current.id == current.id
    # The candidate's refused layer is red; the current copy is 65 days old, fine.
    assert [(n.level, n.code) for n in found.notices] == [("red", "incomplete")]
    assert "zoning_gladstone (refused)" in found.notices[0].text
    assert "zoning_portland (2 features unfetched)" in found.notices[0].text
    assert found.footer == f"County map copy: RLIS 2026_08 + ArcGIS layers, taken 2026-07-28; sources checked {checked.ran_at.date().isoformat()}."
    assert found.level == "red"
    assert waiting.status == "candidate"



# --- promotion: fixtures ------------------------------------------------------

DESIGNS = ("pod56x36@2", "pod80x25@2")
KEPT = "1S2E08BA  -09500"  # same ground, same zone, both runs
REZONED = "1N1E29DD  -05600"  # zone moved between the copies
SPLIT = "11E25AB  -00300"  # the delta shows it split
ONLY_NEW = "1S2E08BA  -09600"  # a lot only the new copy screens (unmeasured)
ONLY_OLD = "1S2E08BA  -09700"  # a lot the county deleted


def _clean_checks() -> dict:
    return {
        code: {"tripped": False, "detail": "quiet"}
        for code in ("layers_incomplete", "count_drift", "new_zones", "lots_drift", "zone_changes", "rlis_agreement")
    }


def _result(lot: FlatsLot, run: FlatsRun, design: str, tier: str, colour: str, *, screened: bool = True) -> FlatsLotResult:
    return FlatsLotResult(
        lot_id=lot.id, design_key=design, run_id=run.id, tier=tier, slack_ft=None, binding=[],
        checks={"verdict": tier, "if_signed": colour, "screened": screened, "rule_verdict": "draft" if screened else None},
    )


#: What the July measurement saw, and the same ground re-read from the
#: September copy: the last digits differ the way a re-projected copy differs.
FACTS_JULY = {
    "frontage_ft": 50.0, "lot_width_ft": 50.0, "lot_depth_ft": 100.0, "zone_frac": 1.0,
    "front_bearings_deg": [90.0], "fronts_cul_de_sac": False,
    "observed": {"corner_lot": False, "abuts_alley": False, "in_floodplain": False},
    "sewer": {"in_district": True, "main_dist_ft": 100.0},
    "source": "quadfit", "quadfit": {"triage": "green", "stalls_provided": 6},
}
FACTS_SEPT = {
    "frontage_ft": 50.02, "lot_width_ft": 50.0, "lot_depth_ft": 100.3, "zone_frac": 0.9999999999999999,
    "front_bearings_deg": [90.4], "fronts_cul_de_sac": False,
    "observed": {"corner_lot": False, "abuts_alley": False, "in_floodplain": False},
    "sewer": {"in_district": True, "main_dist_ft": 100.00000001},
    "source": "snapshot", "quadfit": {"triage": "yellow", "stalls_provided": 4},
    "assessor": {"TOTALVAL": 2}, "snapshot_zone": "R5",
}


async def _world(session: AsyncSession, tmp_path, *, same_rules: bool = True, kept: str = "same") -> dict:
    """A copy in use (July, run 2) and a candidate (September, run 4) with the
    delta between them, one decision on each lot, and a clean gate. The lots
    the ground explains were re-read within float noise; the KEPT lot's
    September reading is ``same`` to the digit, ``nudged`` within float
    noise, or ``corner`` -- the street layer now makes it a corner."""
    pipe = _pipeline(tmp_path)
    july = await register_snapshot(session, _manifest(pipe, "2026-07-28"), host="137", status="current")
    sept = await register_snapshot(session, _manifest(pipe, "2026-09-18"), host="137", status="candidate")
    sept.checks = _clean_checks()
    await attach_report(session, sept.id, "delta", {"from": "2026-07-28", "to": "2026-09-18", "rows": 3, "rereview": 1})
    for key in DESIGNS:
        design_id, version = key.split("@")
        session.add(
            FlatsDesign(
                key=key, design_id=design_id, version=int(version), label=design_id,
                typology="pod", width_ft=56, depth_ft=36, units=4, stories=2, height_ft=28,
            )
        )
    old = FlatsRun(
        id=2, status="complete", snapshot_id=july.id, code_version="aaaa", rules_version="r1",
        design_keys=list(DESIGNS), counties=["multnomah", "clackamas"], finished_at=dt.datetime(2026, 9, 18, tzinfo=dt.UTC),
    )
    new = FlatsRun(
        id=4, status="candidate", snapshot_id=sept.id, code_version="bbbb", rules_version="r1" if same_rules else "r2",
        design_keys=list(DESIGNS), counties=["multnomah", "clackamas"], finished_at=dt.datetime(2026, 9, 19, tzinfo=dt.UTC),
    )
    session.add_all([old, new])
    await session.flush()

    def lot(snap: FlatsSnapshot, tlid: str, zone: str, county: str = "multnomah", facts: dict | None = None) -> FlatsLot:
        return FlatsLot(
            tlid=tlid, county=county, jurisdiction=f"or/{county}/x", zone_raw=zone, zone=zone,
            area_sqft=5000, condo_verdict="land", snapshot_id=snap.id,
            facts=facts if facts is not None else (FACTS_JULY if snap is july else FACTS_SEPT),
        )

    kept_sept = {
        "same": {**FACTS_JULY, "source": "snapshot"},
        "nudged": FACTS_SEPT,
        "corner": {**FACTS_SEPT, "observed": {**FACTS_SEPT["observed"], "corner_lot": True}},
    }[kept]
    lots = {
        ("july", KEPT): lot(july, KEPT, "R5"),
        ("july", REZONED): lot(july, REZONED, "R5"),
        ("july", SPLIT): lot(july, SPLIT, "R-7", "clackamas"),
        ("july", ONLY_OLD): lot(july, ONLY_OLD, "R5"),
        ("sept", KEPT): lot(sept, KEPT, "R5", facts=kept_sept),
        ("sept", REZONED): lot(sept, REZONED, "R2.5"),
        ("sept", SPLIT): lot(sept, SPLIT, "R-7", "clackamas"),
        ("sept", ONLY_NEW): lot(sept, ONLY_NEW, "R5"),
    }
    session.add_all(lots.values())
    await session.flush()
    results = [
        # KEPT: one design unchanged, the other moves with no cause -- the bug the gate is for.
        _result(lots["july", KEPT], old, DESIGNS[0], "unknown", "green"),
        _result(lots["sept", KEPT], new, DESIGNS[0], "unknown", "green"),
        _result(lots["july", KEPT], old, DESIGNS[1], "unknown", "yellow"),
        _result(lots["sept", KEPT], new, DESIGNS[1], "unknown", "red"),
        # REZONED: both designs move; the zone explains it.
        _result(lots["july", REZONED], old, DESIGNS[0], "unknown", "green"),
        _result(lots["sept", REZONED], new, DESIGNS[0], "unknown", "red"),
        _result(lots["july", REZONED], old, DESIGNS[1], "unknown", "green"),
        _result(lots["sept", REZONED], new, DESIGNS[1], "unknown", "green"),
        # SPLIT: the tier moves; the delta row explains it.
        _result(lots["july", SPLIT], old, DESIGNS[0], "unknown", "yellow"),
        _result(lots["sept", SPLIT], new, DESIGNS[0], "red", "red"),
        _result(lots["july", SPLIT], old, DESIGNS[1], "unknown", "yellow"),
        _result(lots["sept", SPLIT], new, DESIGNS[1], "unknown", "yellow"),
        # ONLY_NEW: the county map holds it, nobody measured it.
        _result(lots["sept", ONLY_NEW], new, DESIGNS[0], "unknown", "unknown", screened=False),
        _result(lots["sept", ONLY_NEW], new, DESIGNS[1], "unknown", "unknown", screened=False),
        # ONLY_OLD: gone from the county map.
        _result(lots["july", ONLY_OLD], old, DESIGNS[0], "unknown", "green"),
        _result(lots["july", ONLY_OLD], old, DESIGNS[1], "unknown", "green"),
    ]
    session.add_all(results)
    session.add_all(
        [
            FlatsLotChange(snapshot_from=july.id, snapshot_to=sept.id, county="clackamas", tlid=SPLIT, kind="split", role="parent", related_tlids=["11E25AB  -00301"]),
            FlatsLotChange(snapshot_from=july.id, snapshot_to=sept.id, county="multnomah", tlid=ONLY_OLD, kind="deleted"),
            FlatsLotChange(snapshot_from=july.id, snapshot_to=sept.id, county="multnomah", tlid=KEPT, kind="attr_change", attr_diff={"TOTALVAL": [1, 2]}),
        ]
    )
    for county, tlid in (("multnomah", KEPT), ("multnomah", REZONED), ("clackamas", SPLIT), ("multnomah", ONLY_OLD)):
        session.add(FlatsReviewDecision(county=county, tlid=tlid, design_key="", check_code="lot", verdict="green", reason="seen it"))
    # A superseded decision on the split lot is history and is left alone.
    session.add(
        FlatsReviewDecision(
            county="clackamas", tlid=SPLIT, design_key="", check_code="lot", verdict="red", reason="old",
            superseded_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
        )
    )
    await session.commit()
    return {"july": july, "sept": sept, "old": old, "new": new}


async def _rescreen(
    session: AsyncSession,
    snap: FlatsSnapshot,
    base_run_id: int,
    run_id: int,
    *,
    code: str = "cccc",
    rules: str = "r1",
    screen: str | None = None,
    moves: dict[tuple[str, str], tuple[str, str]] | None = None,
) -> FlatsRun:
    """A re-screen of ``snap``'s lots as candidate run ``run_id``: every
    answer copied from ``base_run_id`` except ``moves`` {(tlid, design):
    (tier, colour)} -- by default the KEPT lot's second design turns red."""
    run = FlatsRun(
        id=run_id, status="candidate", snapshot_id=snap.id, code_version=code, rules_version=rules,
        screen_version=screen, design_keys=list(DESIGNS), counties=["multnomah", "clackamas"],
        finished_at=dt.datetime(2026, 9, 21, tzinfo=dt.UTC),
    )
    session.add(run)
    await session.flush()
    moves = {(KEPT, DESIGNS[1]): ("unknown", "red")} if moves is None else moves
    rows = (
        await session.execute(
            select(FlatsLotResult, FlatsLot)
            .join(FlatsLot, FlatsLot.id == FlatsLotResult.lot_id)
            .where(FlatsLotResult.run_id == base_run_id, FlatsLot.snapshot_id == snap.id)
        )
    ).all()
    for res, lot in rows:
        tier, colour = moves.get((lot.tlid, res.design_key), (res.tier, res.checks.get("if_signed")))
        session.add(_result(lot, run, res.design_key, tier, colour, screened=res.checks.get("screened", True)))
    await session.commit()
    return run


async def _decisions(session: AsyncSession) -> dict[str, tuple[int | None, str | None]]:
    rows = (
        await session.execute(select(FlatsReviewDecision).where(FlatsReviewDecision.superseded_at.is_(None)))
    ).scalars().all()
    return {r.tlid: (r.needs_rereview_snapshot_id, r.needs_rereview_reason) for r in rows}


# --- the gate ------------------------------------------------------------------


async def test_the_gate_reads_the_six_checks_and_the_two_reports(session: AsyncSession, tmp_path) -> None:
    w = await _world(session, tmp_path)
    sept = w["sept"]

    # Clean checks, a delta, no drift report yet: only the drift report is owed.
    assert blocks(sept) == ["no_drift"]
    codes = [g["code"] for g in gate(sept)]
    assert codes == list(flats_refresh.GATE_CODES)
    assert [g["code"] for g in gate(sept) if g["tripped"]] == ["no_drift"]
    assert "3 lot changes 2026-07-28 -> 2026-09-18" in next(g["detail"] for g in gate(sept) if g["code"] == "no_delta")

    sept.checks = {**sept.checks, "lots_drift": {"tripped": True, "detail": "289,845 -> 280,000 measured lots (-3.4%)"}}
    sept.report = {"drift": {"unexplained": 2, "moved": 5, "compared": 100, "by_cause": {"data": 3, "rules": 0, "code": 0, "unexplained": 2}}}
    assert blocks(sept) == ["lots_drift", "no_delta", "verdict_drift"]
    sept.report = {"delta": {"rows": 1}, "drift": {"unexplained": 0, "moved": 5, "compared": 100, "by_cause": {"data": 5, "rules": 0, "code": 0, "unexplained": 0}}}
    assert blocks(sept) == ["lots_drift"]


async def test_a_zone_code_nobody_ruled_on_is_shown_warned_and_let_through(session: AsyncSession, tmp_path) -> None:
    """Steph 2026-09-22 (HUMAN_TODO 22): "when a city invents a zone code, only
    those lots sit while the rest go live." The gate row is still there and
    still tripped -- the page shows it and the banner names the code -- but it
    is not what the promotion reads, so the agent promotes on the standing
    word and the county gets its fresh copy on time."""
    w = await _world(session, tmp_path)
    sept = w["sept"]
    await drift(session, from_run=2, to_run=4)
    await session.commit()
    sept = await session.get(FlatsSnapshot, sept.id)
    sept.checks = {**sept.checks, "new_zones": {"tripped": True, "detail": "or/multnomah/gresham: CX (312)"}}
    session.add(sept)
    await session.flush()

    assert blocks(sept) == [], "the rest of the county is not held back"
    assert warns(sept) == ["new_zones"]
    row = next(g for g in gate(sept) if g["code"] == "new_zones")
    assert (row["tripped"], row["blocking"], row["warn_only"]) == (True, False, True)
    assert row["detail"] == "or/multnomah/gresham: CX (312)", "the page still names the code and its lots"

    done = await promote(session, sept.id, by="agent, standing word 2026-09-19")
    await session.commit()
    assert done.blocks == [] and done.snapshot.status == "current"
    assert "over" not in (done.snapshot.notes or ""), "no override was needed"

    # Anything else standing beside it still waits for Steph.
    session.expunge_all()
    july = await session.get(FlatsSnapshot, w["july"].id)
    july.status = "candidate"
    july.checks = {
        **_clean_checks(),
        "new_zones": {"tripped": True, "detail": "or/multnomah/gresham: CX (312)"},
        "layers_incomplete": {"tripped": True, "detail": "zoning_gresham: failed"},
    }
    session.add(july)
    await session.flush()
    assert blocks(july) == ["layers_incomplete", "no_delta", "no_drift"]


async def test_a_re_screen_of_the_copy_in_use_is_gated_on_its_own_drift(session: AsyncSession, tmp_path) -> None:
    """The delta is the copy's and is not owed twice; the drift report must
    be about THIS run, not one left on the row from the copy's promotion."""
    w = await _world(session, tmp_path)
    july = w["july"]
    july.checks = _clean_checks()
    session.add(july)
    await session.flush()
    rerun = await _rescreen(session, july, 2, 5)

    assert blocks(july, rerun) == ["no_drift"]
    rows = gate(july, rerun)
    assert [g["code"] for g in rows] == [*flats_refresh.CHECK_CODES, "no_drift", "verdict_drift"], "no delta row for a re-screen"
    assert next(g["detail"] for g in rows if g["code"] == "no_drift") == "no drift report for run 5; run drift from the run in use to it"

    # A drift report about another run does not count for this one.
    await attach_report(session, july.id, "drift", {"from_run": 1, "to_run": 2, "unexplained": 0, "moved": 0, "compared": 4, "by_cause": {}})
    assert blocks(july, rerun) == ["no_drift"]
    assert blocks(july) == ["no_delta"], "the copy's own gate reads the same row and is owed its delta"

    doc = await drift(session, from_run=2, to_run=5)
    await session.commit()
    assert doc["same_copy"] is True and doc["to_run"] == 5
    assert blocks(july, rerun) == []
    assert [g["code"] for g in gate(july, rerun) if g["tripped"]] == []
    # The report the copy carried before is kept, not overwritten.
    session.expunge_all()
    july = await session.get(FlatsSnapshot, w["july"].id)
    assert july.report["drift"]["to_run"] == 5
    assert [d["to_run"] for d in july.report["drift_earlier"]] == [2]


async def test_two_runs_of_one_copy_put_a_move_to_the_rules_or_the_screen_never_the_ground(
    session: AsyncSession, tmp_path
) -> None:
    """The ground cannot have moved between two runs of one copy; a
    lot_changes row on that copy is the previous quarter's. What is left is
    the rules version, the screen's own version (``screen_version``, the
    hash of the screen's files) when both runs carry one, else the repo
    HEAD -- and a move with none of those is unexplained."""
    w = await _world(session, tmp_path)
    july, old = w["july"], w["old"]
    july.checks = _clean_checks()
    session.add(july)
    # The previous quarter's delta named the KEPT lot as split INTO this copy: not this run's doing.
    april = await register_snapshot(session, _manifest(_pipeline(tmp_path), "2026-04-01"), host="137", status="candidate")
    april.status = "retired"
    session.add(april)
    await session.flush()
    session.add(FlatsLotChange(snapshot_from=april.id, snapshot_to=july.id, county="multnomah", tlid=KEPT, kind="split", role="parent"))
    await session.commit()

    by_code = await _rescreen(session, july, 2, 5, code="cccc")
    doc = await drift(session, from_run=2, to_run=5)
    assert (doc["compared"], doc["moved"], doc["unscreened_side"], doc["only_in_new"], doc["only_in_old"]) == (8, 1, 0, 0, 0)
    assert doc["by_cause"] == {"data": 0, "surroundings": 0, "remeasured": 0, "rules": 0, "code": 1, "unexplained": 0}
    assert doc["colour_moves"] == {"yellow->red": 1} and doc["same_copy"] is True
    assert "Both runs read the same copy" in drift_markdown(doc)
    assert blocks(july, by_code) == [], "a move the screen explains does not block"
    assert blocks(july) == ["no_delta"], "the copy's own gate still wants the delta it was promoted on"

    by_rules = await _rescreen(session, july, 2, 6, code="aaaa", rules="r2")
    doc = await drift(session, from_run=2, to_run=6)
    assert doc["by_cause"]["rules"] == 1 and doc["unexplained"] == 0

    # Both carry a screen version and it is the same: the HEAD moved, the screen did not -- a bug, and it blocks.
    old.screen_version = "s1"
    session.add(old)
    await session.flush()
    same_screen = await _rescreen(session, july, 2, 7, code="dddd", screen="s1")
    doc = await drift(session, from_run=2, to_run=7)
    await session.commit()
    assert doc["screen_version"] == ["s1", "s1"] and doc["by_cause"]["code"] == 0 and doc["unexplained"] == 1
    assert "screen s1 -> s1" in drift_markdown(doc)
    assert blocks(july, same_screen) == ["verdict_drift"]
    with pytest.raises(PromotionBlocked) as caught:
        await promote_run(session, 7, by="agent, standing word 2026-09-19")
    assert caught.value.codes == ["verdict_drift"]

    # The screen changed and the HEAD did not (a re-export from the same commit with a fixed quadfit): the screen.
    other_screen = await _rescreen(session, july, 2, 8, code="aaaa", screen="s2")
    doc = await drift(session, from_run=2, to_run=8)
    assert doc["by_cause"]["code"] == 1 and doc["unexplained"] == 0
    assert blocks(july, other_screen) == []
    assert by_rules.status == "candidate"


async def test_a_re_screen_is_promoted_through_the_gate_and_the_run_it_replaces_stays(
    session: AsyncSession, tmp_path
) -> None:
    w = await _world(session, tmp_path)
    july = w["july"]
    july.checks = _clean_checks()
    session.add(july)
    await session.flush()
    rerun = await _rescreen(session, july, 2, 5)

    with pytest.raises(PromotionBlocked) as caught:
        await promote_run(session, 5, by="agent, standing word 2026-09-19")
    assert caught.value.codes == ["no_drift"]
    with pytest.raises(PromotionError, match="promoted whole"):
        await promote_run(session, 4, by="Steph")  # run 4 is the September candidate's run: promote the copy
    with pytest.raises(PromotionError, match="only a candidate run"):
        await promote_run(session, 2, by="Steph")
    with pytest.raises(PromotionError, match="no run 999"):
        await promote_run(session, 999, by="Steph")
    with pytest.raises(PromotionError, match="say who"):
        await promote_run(session, 5, by="")

    await drift(session, from_run=2, to_run=5)
    done = await promote_run(session, 5, by="agent, standing word 2026-09-19", now=dt.datetime(2026, 9, 21, 9, 0, tzinfo=dt.UTC))
    await session.commit()
    session.expunge_all()

    assert (done.run.id, done.previous.id, done.snapshot.id, done.blocks) == (5, 2, july.id, [])
    new = await session.get(FlatsRun, 5)
    old = await session.get(FlatsRun, 2)
    july = await session.get(FlatsSnapshot, w["july"].id)
    assert new.status == "complete" and old.status == "complete", "the run it replaces stays reachable by ?run="
    assert july.status == "current" and july.promoted_at is None, "the copy did not change hands"
    assert "promoted 2026-09-21 by agent, standing word 2026-09-19 (replaces run 2, still reachable by ?run=)" in new.notes
    assert "re-screen: run 5 promoted 2026-09-21 by agent, standing word 2026-09-19; run 2 replaced" in july.notes
    assert (await run_in_use(session, july.id)).id == 5
    assert (await run_in_use(session)).id == 5, "the Lots pages' default is the newest complete run"
    assert (await _decisions(session))[KEPT] == (None, None), "nothing on the ground moved; no decision is doubted"
    with pytest.raises(PromotionError, match="only a candidate run"):
        await promote_run(session, 5, by="Steph")

    # Undo: the run goes back to waiting, the earlier run is the default again.
    with pytest.raises(PromotionError, match="say why"):
        await rollback_run(session, 5, by="Steph", reason=" ")
    with pytest.raises(PromotionError, match="not the run in use"):
        await rollback_run(session, 2, by="Steph", reason="the old one")
    with pytest.raises(PromotionError, match="not on the copy in use"):
        await rollback_run(session, 4, by="Steph", reason="the candidate's run")
    undone = await rollback_run(session, 5, by="Steph", reason="the new numbers look wrong", now=dt.datetime(2026, 9, 22, tzinfo=dt.UTC))
    await session.commit()
    session.expunge_all()
    assert (undone.restored.id, undone.demoted.id) == (2, 5)
    new = await session.get(FlatsRun, 5)
    assert new.status == "candidate" and "rolled back 2026-09-22 by Steph: the new numbers look wrong (run 2 is the default again)" in new.notes
    assert (await run_in_use(session)).id == 2
    assert "re-screen: run 5 rolled back 2026-09-22 by Steph; run 2 in use again" in (await session.get(FlatsSnapshot, w["july"].id)).notes
    with pytest.raises(PromotionError, match="only complete run"):
        await rollback_run(session, 2, by="Steph", reason="further back")

    # Over a warning, with the reason kept on the run.
    (await session.get(FlatsSnapshot, w["july"].id)).report = {"drift": {"from_run": 2, "to_run": 5, "unexplained": 3, "moved": 3, "compared": 8, "by_cause": {"unexplained": 3}}}
    await session.flush()
    with pytest.raises(PromotionBlocked):
        await promote_run(session, 5, by="agent, standing word 2026-09-19")
    done = await promote_run(session, 5, by="Steph", override="read the three lots myself")
    await session.commit()
    session.expunge_all()
    assert done.blocks == ["verdict_drift"]
    assert "over verdict_drift: read the three lots myself" in (await session.get(FlatsRun, 5)).notes
    assert rerun.id == 5


async def test_a_copy_rollback_demotes_every_complete_run_on_it(session: AsyncSession, tmp_path) -> None:
    """After a copy promotion and a re-screen promotion on top of it, the
    copy carries two complete runs; rolling the copy back demotes both, or
    the newest complete run overall would sit on a candidate copy."""
    w = await _world(session, tmp_path)
    await drift(session, from_run=2, to_run=4)
    await promote(session, w["sept"].id, by="Steph")
    await session.commit()
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    rerun = await _rescreen(session, sept, 4, 6, code="dddd")
    await drift(session, from_run=4, to_run=6)
    await promote_run(session, 6, by="agent, standing word 2026-09-19")
    await session.commit()
    session.expunge_all()
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    assert sept.report["drift"]["to_run"] == 6 and [d["to_run"] for d in sept.report["drift_earlier"]] == [4]
    assert (await run_in_use(session)).id == 6

    done = await rollback(session, by="Steph", reason="the September copy as a whole looks wrong")
    await session.commit()
    session.expunge_all()

    assert done.demoted_run.id == 6
    assert [(await session.get(FlatsRun, r)).status for r in (2, 4, 6)] == ["complete", "candidate", "candidate"]
    assert (await session.get(FlatsSnapshot, w["july"].id)).status == "current"
    assert (await run_in_use(session)).id == 2
    assert rerun.id == 6


# --- drift ----------------------------------------------------------------------


async def test_drift_puts_every_move_to_a_cause_and_stores_the_report(session: AsyncSession, tmp_path) -> None:
    w = await _world(session, tmp_path)

    doc = await drift(session, from_run=2, to_run=4)
    await session.commit()

    assert (doc["from_run"], doc["to_run"], doc["from_snapshot"], doc["to_snapshot"]) == (2, 4, w["july"].id, w["sept"].id)
    # Six answers on lots both copies hold and both runs screened; three unchanged.
    assert doc["compared"] == 6 and doc["unchanged"] == 3 and doc["moved"] == 3
    # Code changed between the runs (aaaa -> bbbb), so nothing is unexplained yet;
    # the KEPT lot's move is put to the code, not to the ground.
    assert doc["by_cause"] == {"data": 2, "surroundings": 0, "remeasured": 0, "rules": 0, "code": 1, "unexplained": 0}
    assert doc["surroundings_facts"] == {} and doc["remeasured_facts"] == {}
    assert doc["unexplained"] == 0 and doc["examples"] == []
    assert doc["unscreened_side"] == 0
    assert doc["only_in_new"] == 2 and doc["only_in_old"] == 2
    assert doc["tier_moves"] == {"unknown->red": 1}
    assert doc["colour_moves"] == {"yellow->red": 2, "green->red": 1}
    session.expunge_all()
    stored = await session.get(FlatsSnapshot, w["sept"].id)
    assert stored is not None and stored.report["drift"]["moved"] == 3
    assert "**unexplained 0**" in drift_markdown(doc)


async def test_a_move_with_no_cause_is_unexplained_and_blocks(session: AsyncSession, tmp_path) -> None:
    w = await _world(session, tmp_path)
    w["new"].code_version = "aaaa"  # same code, same rules: the KEPT lot's move has no cause
    await session.commit()

    doc = await drift(session, from_run=2, to_run=4)
    await session.commit()

    assert doc["by_cause"] == {"data": 2, "surroundings": 0, "remeasured": 0, "rules": 0, "code": 0, "unexplained": 1}
    assert doc["examples"] == [
        {"county": "multnomah", "tlid": KEPT, "design": DESIGNS[1], "tier": ["unknown", "unknown"], "colour": ["yellow", "red"]}
    ]
    session.expunge_all()
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    assert blocks(sept) == ["verdict_drift"]
    assert "Unexplained moves" in drift_markdown(doc) and KEPT in drift_markdown(doc)
    with pytest.raises(PromotionBlocked, match="verdict_drift"):
        await promote(session, sept.id, by="agent, standing word 2026-09-19")


async def test_a_rules_change_explains_what_the_ground_does_not(session: AsyncSession, tmp_path) -> None:
    w = await _world(session, tmp_path, same_rules=False)
    w["new"].code_version = "aaaa"
    await session.commit()
    doc = await drift(session, from_run=2, to_run=4)
    assert doc["by_cause"] == {"data": 2, "surroundings": 0, "remeasured": 0, "rules": 1, "code": 0, "unexplained": 0}
    with pytest.raises(PromotionError, match="against itself"):
        await drift(session, from_run=2, to_run=2)
    with pytest.raises(PromotionError, match="no run 99"):
        await drift(session, from_run=2, to_run=99)


async def test_a_moved_surrounding_explains_a_move_the_ground_does_not(session: AsyncSession, tmp_path) -> None:
    """The lot itself is unchanged on the county map, but the street layer
    re-read around it now makes it a corner: the move belongs to the
    surroundings and does not block, and the report says which fact moved."""
    w = await _world(session, tmp_path, kept="corner")
    w["new"].code_version = "aaaa"
    await session.commit()

    doc = await drift(session, from_run=2, to_run=4)
    await session.commit()

    assert doc["by_cause"] == {"data": 2, "surroundings": 1, "remeasured": 0, "rules": 0, "code": 0, "unexplained": 0}
    assert doc["surroundings_facts"] == {"observed.corner_lot": 1}
    assert doc["examples"] == []
    md = drift_markdown(doc)
    assert "by the surroundings 1" in md and "## What moved around the lots" in md and "observed.corner_lot: 1" in md
    session.expunge_all()
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    assert blocks(sept) == []


async def test_a_re_measurement_within_tolerance_that_flipped_the_answer_is_named_not_blocked(
    session: AsyncSession, tmp_path
) -> None:
    """Nothing around the KEPT lot moved beyond float noise, but its answer
    sat on a line and flipped: the verdict is unstable there, which is worth
    a line in the report and is not a bug in the screen."""
    w = await _world(session, tmp_path, kept="nudged")
    w["new"].code_version = "aaaa"
    await session.commit()

    doc = await drift(session, from_run=2, to_run=4)
    await session.commit()

    assert doc["by_cause"] == {"data": 2, "surroundings": 0, "remeasured": 1, "rules": 0, "code": 0, "unexplained": 0}
    assert doc["surroundings_facts"] == {}
    assert doc["remeasured_facts"] == {"front_bearings_deg": 1, "frontage_ft": 1, "lot_depth_ft": 1, "sewer.main_dist_ft": 1, "zone_frac": 1}
    md = drift_markdown(doc)
    assert "by a re-measurement 1" in md and "re-measured within tolerance" in md and "zone_frac: 1" in md
    session.expunge_all()
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    assert blocks(sept) == []


async def test_two_readings_of_the_same_ground_differ_only_beyond_float_noise() -> None:
    # The fixture's two readings are the same measurement, to a hair.
    assert facts_moved(FACTS_JULY, FACTS_SEPT) == []
    assert facts_moved(FACTS_JULY, FACTS_SEPT, tolerant=False) == [
        "front_bearings_deg",
        "frontage_ft",
        "lot_depth_ft",
        "sewer.main_dist_ft",
        "zone_frac",
    ]
    # A flag, a line, a nested flag: each is a fact that moved, named by its path.
    assert facts_moved({"observed": {"corner_lot": False}}, {"observed": {"corner_lot": True}}) == ["observed.corner_lot"]
    assert facts_moved(
        {"fronts_cul_de_sac": False, "sewer": {"in_district": True}}, {"fronts_cul_de_sac": True, "sewer": {"in_district": False}}
    ) == ["fronts_cul_de_sac", "sewer.in_district"]
    # Within a twentieth of a foot or two per cent is the same number; beyond either is not.
    assert facts_moved({"lot_width_ft": 100.0}, {"lot_width_ft": 101.9}) == []
    assert facts_moved({"lot_width_ft": 100.0}, {"lot_width_ft": 102.5}) == ["lot_width_ft"]
    assert facts_moved({"slope": {"pct": 0.01}}, {"slope": {"pct": 0.05}}) == []
    assert facts_moved({"slope": {"pct": 0.01}}, {"slope": {"pct": 0.10}}) == ["slope.pct"]
    # A street gained or lost is a move; a bearing nudged is not.
    assert facts_moved({"front_bearings_deg": [90.0]}, {"front_bearings_deg": [90.0, 180.0]}) == ["front_bearings_deg"]
    assert facts_moved({"front_bearings_deg": [90.0]}, {"front_bearings_deg": [91.0]}) == []
    # A fact that appears or disappears moved; a missing reading is empty.
    assert facts_moved({}, {"observed": {"corner_lot": True}}) == ["observed.corner_lot"]
    assert facts_moved(None, None) == []
    # What the screen concluded, the roll, and the register's bookkeeping are not surroundings.
    assert facts_moved(
        {"quadfit": {"triage": "green"}, "source": "quadfit"},
        {
            "quadfit": {"triage": "red"}, "source": "snapshot", "assessor": {"TOTALVAL": 9},
            "condo": {"verdict": "unit"}, "snapshot_zone": "R5", "quadfit_jurisdiction": "x",
        },
    ) == []


# --- promote / rollback / prune --------------------------------------------------


async def test_promotion_flips_three_rows_and_marks_the_decisions_on_moved_ground(session: AsyncSession, tmp_path) -> None:
    w = await _world(session, tmp_path)
    await drift(session, from_run=2, to_run=4)
    await session.commit()

    done = await promote(session, w["sept"].id, by="agent, standing word 2026-09-19", now=dt.datetime(2026, 9, 20, 9, 0, tzinfo=dt.UTC))
    await session.commit()
    session.expunge_all()

    sept = await session.get(FlatsSnapshot, w["sept"].id)
    july = await session.get(FlatsSnapshot, w["july"].id)
    new = await session.get(FlatsRun, 4)
    old = await session.get(FlatsRun, 2)
    assert done.blocks == [] and done.flagged == 3
    assert (sept.status, sept.promoted_by, sept.promoted_at) == ("current", "agent, standing word 2026-09-19", dt.datetime(2026, 9, 20, 9, 0, tzinfo=dt.UTC))
    assert july.status == "retired" and "promoted by agent" in july.notes
    assert new.status == "complete" and old.status == "complete", "the old run stays reachable by ?run="
    assert "over" not in (sept.notes or "")
    marked = await _decisions(session)
    assert marked[KEPT] == (None, None), "an attribute change is adopted, not doubted"
    assert marked[REZONED] == (sept.id, "zone R5 -> R2.5")
    assert marked[SPLIT] == (sept.id, "split parent")
    assert marked[ONLY_OLD] == (sept.id, "deleted")
    history = (
        await session.execute(select(FlatsReviewDecision).where(FlatsReviewDecision.superseded_at.is_not(None)))
    ).scalars().one()
    assert history.needs_rereview_snapshot_id is None

    # Promoting again: nothing is a candidate any more.
    with pytest.raises(PromotionError, match="only a candidate"):
        await promote(session, sept.id, by="Steph")


async def test_a_standing_gate_refuses_the_agent_and_records_stephs_override(session: AsyncSession, tmp_path) -> None:
    w = await _world(session, tmp_path)
    # No drift report: the gate stands on no_drift.
    with pytest.raises(PromotionBlocked) as caught:
        await promote(session, w["sept"].id, by="agent, standing word 2026-09-19")
    assert caught.value.codes == ["no_drift"]
    with pytest.raises(PromotionError, match="say who"):
        await promote(session, w["sept"].id, by=" ")
    with pytest.raises(PromotionError, match="no snapshot 999"):
        await promote(session, 999, by="Steph")

    done = await promote(session, w["sept"].id, by="Steph", override="read the delta myself; the drift can wait")
    await session.commit()
    session.expunge_all()
    sept = await session.get(FlatsSnapshot, w["sept"].id)
    assert done.blocks == ["no_drift"]
    assert sept.status == "current" and sept.promoted_by == "Steph"
    assert "promoted 20" in sept.notes and "over no_drift by Steph: read the delta myself" in sept.notes


async def test_a_copy_nothing_was_loaded_from_cannot_be_promoted(session: AsyncSession, tmp_path) -> None:
    pipe = _pipeline(tmp_path)
    bare = await register_snapshot(session, _manifest(pipe, "2026-09-18"), host="137", status="candidate")
    await session.commit()
    with pytest.raises(PromotionError, match="nothing has been loaded"):
        await promote(session, bare.id, by="Steph")


async def test_rollback_puts_the_previous_copy_back_and_the_run_with_it(session: AsyncSession, tmp_path) -> None:
    w = await _world(session, tmp_path)
    with pytest.raises(PromotionError, match="never promoted"):
        await rollback(session, by="Steph", reason="cold feet")
    await drift(session, from_run=2, to_run=4)
    await promote(session, w["sept"].id, by="Steph")
    await session.commit()

    with pytest.raises(PromotionError, match="say why"):
        await rollback(session, by="Steph", reason="")
    done = await rollback(session, by="Steph", reason="the Milwaukie zones look wrong")
    await session.commit()
    session.expunge_all()

    sept = await session.get(FlatsSnapshot, w["sept"].id)
    july = await session.get(FlatsSnapshot, w["july"].id)
    assert done.restored.id == july.id and done.demoted.id == sept.id
    assert (july.status, sept.status) == ("current", "candidate")
    assert (await session.get(FlatsRun, 4)).status == "candidate"
    assert (await session.get(FlatsRun, 2)).status == "complete"
    assert "rolled back" in sept.notes and "Milwaukie" in sept.notes
    assert "restored" in july.notes
    # The marks stay: a person clears them, not a status flip.
    assert (await _decisions(session))[REZONED][0] == sept.id
    # And the same copy can be promoted again once the doubt is settled.
    await promote(session, sept.id, by="Steph")
    await session.commit()
    session.expunge_all()
    assert (await session.get(FlatsSnapshot, w["sept"].id)).status == "current"


async def test_prune_drops_only_copies_older_than_the_previous_one(session: AsyncSession, tmp_path) -> None:
    w = await _world(session, tmp_path)
    pipe = _pipeline(tmp_path)
    # An older retired copy from before July, with a lot row of its own.
    ancient = await register_snapshot(session, _manifest(pipe, "2026-04-01"), host="137", status="candidate")
    ancient.status = "retired"
    ancient.promoted_at = dt.datetime(2026, 4, 2, tzinfo=dt.UTC)
    run0 = FlatsRun(id=1, status="complete", snapshot_id=ancient.id, design_keys=list(DESIGNS), counties=[])
    session.add(run0)
    await session.flush()
    session.add(FlatsLot(tlid="OLD", county="multnomah", jurisdiction="or/multnomah/x", zone="R5", area_sqft=1, facts={}, snapshot_id=ancient.id))
    await drift(session, from_run=2, to_run=4)
    await promote(session, w["sept"].id, by="Steph")
    await session.commit()

    pruned = await prune(session, keep=1)
    await session.commit()
    session.expunge_all()

    assert pruned == [{"snapshot_id": ancient.id, "snapshot_date": "2026-04-01", "lots": 1, "runs": 1}]
    assert (await session.get(FlatsRun, 1)).status == "retired"
    left = dict(
        (await session.execute(select(FlatsLot.snapshot_id, func.count()).group_by(FlatsLot.snapshot_id))).all()
    )
    assert left == {w["july"].id: 4, w["sept"].id: 4}, "the copy in use and the one before it keep every row"
    assert "pruned" in (await session.get(FlatsSnapshot, ancient.id)).notes
    assert await prune(session, keep=1) == []
    with pytest.raises(PromotionError, match="pruned"):
        # July is the previous copy and whole; prune everything retired, then a rollback has nothing to go back to.
        await prune(session, keep=0)
        await session.commit()
        await rollback(session, by="Steph", reason="try")
