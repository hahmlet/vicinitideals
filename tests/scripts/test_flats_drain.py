"""Moving a browser verdict into the repository without losing it.

The drain crosses a boundary that nothing else in FLATS crosses: it reads a
production database and writes a file. Those two live in different places and
survive different events — the database is a named volume that outlives every
deploy, the container's filesystem is rebuilt by the next one. Stamp the rows
and lose the file and a reviewer's afternoon is gone with no error raised
anywhere, because a stamped row is never offered again.

So what these tests hold to is the order: nothing is stamped until the lines
are on disk and have been read back.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsRuleSignature
from flats.rules.loader import load_rules
from scripts.flats_drain_signatures import drain

pytestmark = pytest.mark.asyncio


def _a_real_encoded_value() -> tuple[str, str, str, object, str, str]:
    """One base value out of the corpus, addressed the way the browser does.

    Taken from the real rules rather than a fixture because the drain's whole
    job is to compare what the reviewer saw against what the files say now; a
    value that exists only in the test could never fail that comparison.
    """
    for layer_id, layer in sorted(load_rules(strict=False).items()):
        for code in sorted(layer.zones):
            for name in sorted(layer.zones[code].values):
                value = layer.zones[code].values[name]
                if not value.variants and value.prov.quote:
                    return (
                        layer_id,
                        code,
                        name,
                        value.value,
                        value.prov.cite or "",
                        value.prov.quote,
                    )
    raise AssertionError("the corpus has no quoted base value to drain")


def _row(**kw) -> FlatsRuleSignature:
    layer, zone, field, value, cite, quote = _a_real_encoded_value()
    return FlatsRuleSignature(
        layer=kw.pop("layer", layer),
        zone=zone,
        field=field,
        when_key="",
        value=kw.pop("value", value),
        cite=cite,
        quote=quote,
        verdict=kw.pop("verdict", "verified"),
        note=kw.pop("note", ""),
        reviewer="reviewer@example.com",
        **kw,
    )


async def test_a_confirmation_becomes_a_line_in_the_log(
    session: AsyncSession, tmp_path
):
    log = tmp_path / "verifications.jsonl"
    session.add(_row())
    await session.commit()

    await drain(session, write=True, log_path=log, rejections_path=tmp_path / "r.jsonl")

    written = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(written) == 1
    assert written[0]["reviewer"] == "reviewer@example.com"
    assert written[0]["fingerprint"]


async def test_a_drained_row_is_stamped_and_not_offered_twice(
    session: AsyncSession, tmp_path
):
    log = tmp_path / "verifications.jsonl"
    session.add(_row())
    await session.commit()

    await drain(session, write=True, log_path=log, rejections_path=tmp_path / "r.jsonl")
    await drain(session, write=True, log_path=log, rejections_path=tmp_path / "r.jsonl")

    assert len(log.read_text().splitlines()) == 1
    row = (await session.execute(select(FlatsRuleSignature))).scalars().one()
    assert row.exported_at is not None


async def test_a_dry_run_writes_nothing_and_stamps_nothing(
    session: AsyncSession, tmp_path
):
    log = tmp_path / "verifications.jsonl"
    session.add(_row())
    await session.commit()

    await drain(session, write=False, log_path=log, rejections_path=tmp_path / "r.jsonl")

    assert not log.exists()
    row = (await session.execute(select(FlatsRuleSignature))).scalars().one()
    assert row.exported_at is None


async def test_a_verdict_on_a_number_that_has_since_changed_stays_in_the_queue(
    session: AsyncSession, tmp_path
):
    """The reviewer confirmed something the files no longer say.

    Signing it would certify text nobody read, so the row is left where it is —
    the right answer to a moved value is another look, not a signature.
    """
    log = tmp_path / "verifications.jsonl"
    session.add(_row(value=999999))
    await session.commit()

    await drain(session, write=True, log_path=log, rejections_path=tmp_path / "r.jsonl")

    assert not log.exists()
    row = (await session.execute(select(FlatsRuleSignature))).scalars().one()
    assert row.exported_at is None


async def test_a_rejection_goes_to_its_own_file_not_the_verification_log(
    session: AsyncSession, tmp_path
):
    """Nothing was verified, and an entry in the log would have to say it was."""
    log = tmp_path / "verifications.jsonl"
    rejections = tmp_path / "rejections.jsonl"
    session.add(_row(verdict="rejected", note="the table says 15, not 10"))
    await session.commit()

    await drain(session, write=True, log_path=log, rejections_path=rejections)

    assert not log.exists()
    assert "the table says 15, not 10" in rejections.read_text()


async def test_a_drained_rejection_actually_stops_the_screen_trusting_it(
    session: AsyncSession, tmp_path
):
    """The half of a review that used to go nowhere.

    Rejections landed in a file of their own shape that nothing read, so a
    reviewer could refuse a number and the screen would go on using it -- the
    verdict was recorded and inert. A drained rejection is a dispute now: same
    fingerprint a signature uses, read by the same load pipeline, and it
    demotes the value it is about.
    """
    from flats.encode.dispute import DisputeLog, apply_disputes
    from flats.rules.model import Status

    log = tmp_path / "verifications.jsonl"
    disputes = tmp_path / "disputes.jsonl"
    layer, zone, field, _, _, _ = _a_real_encoded_value()
    session.add(_row(verdict="rejected", note="the table row is the corner-lot column"))
    await session.commit()

    await drain(session, write=True, log_path=log, rejections_path=disputes)

    layers = load_rules(strict=False)
    assert layers[layer].zones[zone].values[field].status is not Status.disputed

    out, answered = apply_disputes(layers, DisputeLog.load(disputes))

    assert not answered, "the value has not changed, so nothing is answered yet"
    assert out[layer].zones[zone].values[field].status is Status.disputed
    assert not out[layer].zones[zone].values[field].status.trusted


async def test_nothing_is_stamped_when_the_lines_do_not_land(
    session: AsyncSession, tmp_path
):
    """The failure this whole ordering exists for.

    A path that cannot be written is a stand-in for the real case: a drain run
    inside a container whose filesystem the next deploy discards. If stamping
    happened anyway the row would never be offered again, and the reviewer's
    verdict would be gone with nothing raised.
    """
    unwritable = tmp_path / "wall"
    unwritable.write_text("not a directory")
    session.add(_row())
    await session.commit()

    with pytest.raises((OSError, RuntimeError)):
        await drain(
            session,
            write=True,
            log_path=unwritable / "verifications.jsonl",
            rejections_path=tmp_path / "r.jsonl",
        )

    await session.rollback()
    row = (await session.execute(select(FlatsRuleSignature))).scalars().one()
    assert row.exported_at is None
