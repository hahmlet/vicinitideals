"""The county copy's ledger: registering a snapshot, writing the monthly check.

``app.services.flats_refresh`` is what the scripts, the Celery task and the
Lots pages share, so what is held here is the row-level contract: a manifest
becomes one row with its counts lifted out; the copy in use cannot be
demoted by re-registering; a check that cannot complete is still a row.
The banner rules themselves are tested without a database in
``flats/tests/test_status.py``; the probe's findings in ``test_probe.py``.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsProbe, FlatsSnapshot
from app.services import flats_refresh
from app.services.flats_refresh import (
    RegisterError,
    attach_report,
    refresh_notices,
    register_snapshot,
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
