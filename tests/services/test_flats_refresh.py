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
    gate,
    promote,
    prune,
    refresh_notices,
    register_snapshot,
    rollback,
    run_probe,
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


async def _world(session: AsyncSession, tmp_path, *, same_rules: bool = True) -> dict:
    """A copy in use (July, run 2) and a candidate (September, run 4) with the
    delta between them, one decision on each lot, and a clean gate."""
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

    def lot(snap: FlatsSnapshot, tlid: str, zone: str, county: str = "multnomah") -> FlatsLot:
        return FlatsLot(
            tlid=tlid, county=county, jurisdiction=f"or/{county}/x", zone_raw=zone, zone=zone,
            area_sqft=5000, condo_verdict="land", facts={}, snapshot_id=snap.id,
        )

    lots = {
        ("july", KEPT): lot(july, KEPT, "R5"),
        ("july", REZONED): lot(july, REZONED, "R5"),
        ("july", SPLIT): lot(july, SPLIT, "R-7", "clackamas"),
        ("july", ONLY_OLD): lot(july, ONLY_OLD, "R5"),
        ("sept", KEPT): lot(sept, KEPT, "R5"),
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

    sept.checks = {**sept.checks, "new_zones": {"tripped": True, "detail": "or/clackamas: XYZ (1)"}}
    sept.report = {"drift": {"unexplained": 2, "moved": 5, "compared": 100, "by_cause": {"data": 3, "rules": 0, "code": 0, "unexplained": 2}}}
    assert blocks(sept) == ["new_zones", "no_delta", "verdict_drift"]
    sept.report = {"delta": {"rows": 1}, "drift": {"unexplained": 0, "moved": 5, "compared": 100, "by_cause": {"data": 5, "rules": 0, "code": 0, "unexplained": 0}}}
    assert blocks(sept) == ["new_zones"]


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
    assert doc["by_cause"] == {"data": 2, "rules": 0, "code": 1, "unexplained": 0}
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

    assert doc["by_cause"] == {"data": 2, "rules": 0, "code": 0, "unexplained": 1}
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
    assert doc["by_cause"] == {"data": 2, "rules": 1, "code": 0, "unexplained": 0}
    with pytest.raises(PromotionError, match="same copy"):
        await drift(session, from_run=2, to_run=2)
    with pytest.raises(PromotionError, match="no run 99"):
        await drift(session, from_run=2, to_run=99)


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
