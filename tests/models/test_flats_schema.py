"""The `flats` schema — namespace and keying contracts.

These tests guard the decisions that are expensive to reverse: that FLATS is a
separate namespace rather than a prefix, that results are keyed by lot *and*
design *and* run, and that a human review decision survives the pipeline
rebuilding the lot it was about.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base
from app.models.flats import (
    SCHEMA,
    SRID_WGS84,
    SRID_WORKING,
    FlatsDesign,
    FlatsLot,
    FlatsLotResult,
    FlatsReviewDecision,
    FlatsRun,
)


async def make_run(session: AsyncSession, **kw) -> FlatsRun:
    run = FlatsRun(status="complete", counties=["multnomah"], **kw)
    session.add(run)
    await session.flush()
    return run


async def make_design(session: AsyncSession, key: str = "pod56x36@1", **kw) -> FlatsDesign:
    design_id, _, version = key.partition("@")
    design = FlatsDesign(
        key=key,
        design_id=design_id,
        version=int(version),
        label=kw.pop("label", "Pod 56 x 36"),
        typology="townhome_rear_court",
        width_ft=56,
        depth_ft=36,
        units=4,
        stories=2,
        height_ft=26,
        **kw,
    )
    session.add(design)
    await session.flush()
    return design


async def make_lot(session: AsyncSession, tlid: str = "1S2E05DA 01900", **kw) -> FlatsLot:
    lot = FlatsLot(
        tlid=tlid,
        county=kw.pop("county", "multnomah"),
        jurisdiction=kw.pop("jurisdiction", "or/multnomah/portland"),
        zone=kw.pop("zone", "R5"),
        **kw,
    )
    session.add(lot)
    await session.flush()
    return lot


# --- the namespace ---------------------------------------------------


def test_flats_tables_are_in_their_own_schema() -> None:
    # A dedicated schema, not a `flats_` prefix: the product boundary is
    # structural, and `public` can never reach screening data by accident.
    flats_tables = {t.name for t in Base.metadata.sorted_tables if t.schema == SCHEMA}

    # Pinned as an exact set on purpose: a table arriving in this schema is a
    # product decision, and the list is short enough that naming each one costs
    # less than the surprise of not. The two review inboxes below joined it in
    # 0126 and 0128 and this assertion did not learn about them for a fortnight,
    # because CI's first gate step was crashing and every test under it was
    # being SKIPPED -- see tests/test_config_env_example.py.
    assert flats_tables == {
        "runs",
        "designs",
        "lots",
        "lot_results",
        "rules",
        "clauses",
        "review_decisions",
        # Inboxes. Rules load from the repository; these hold a reviewer's
        # verdict until a drain writes it into the YAML or the signature log
        # and stamps exported_at.
        "rule_signatures",
        "crossref_rulings",
        "reading_rulings",
    }


def test_nothing_named_parcels_came_back() -> None:
    # Migration 0113 dropped `parcels` deliberately. FLATS replaces it; it does
    # not revive it, and a table by that name would restart an argument that
    # already cost two crumb-sweep passes to settle.
    names = {t.name for t in Base.metadata.sorted_tables}

    assert "parcels" not in names
    assert "lots" not in {t.name for t in Base.metadata.sorted_tables if t.schema is None}


async def test_geometry_columns_registered_with_the_right_srids(session: AsyncSession) -> None:
    # Working CRS is Oregon North in FEET, because the zoning code is written in
    # feet. Storing it in degrees and converting per query is a bug generator.
    rows = (
        await session.execute(
            text(
                "SELECT f_table_name, f_geometry_column, srid FROM geometry_columns "
                "WHERE f_table_schema = :s ORDER BY 1, 2"
            ),
            {"s": SCHEMA},
        )
    ).all()

    assert rows == [
        ("lot_results", "site_plan", SRID_WORKING),
        ("lots", "centroid", SRID_WGS84),
        ("lots", "geom", SRID_WORKING),
    ]


# --- keying ----------------------------------------------------------


async def test_a_lot_carries_one_result_per_design(session: AsyncSession) -> None:
    # The whole point of the catalog: one lot, several buildings, separate
    # verdicts. This is the row shape a schema migration would otherwise cost.
    run = await make_run(session)
    lot = await make_lot(session)
    await make_design(session, "pod56x36@1")
    await make_design(session, "pod80x25@1", label="Pod 80 x 25")

    session.add_all(
        [
            FlatsLotResult(lot_id=lot.id, design_key="pod56x36@1", run_id=run.id, tier="green"),
            FlatsLotResult(lot_id=lot.id, design_key="pod80x25@1", run_id=run.id, tier="red"),
        ]
    )
    await session.flush()

    tiers = (
        await session.execute(
            select(FlatsLotResult.design_key, FlatsLotResult.tier)
            .where(FlatsLotResult.lot_id == lot.id)
            .order_by(FlatsLotResult.design_key)
        )
    ).all()
    assert tiers == [("pod56x36@1", "green"), ("pod80x25@1", "red")]


async def test_the_same_lot_and_design_can_differ_across_runs(session: AsyncSession) -> None:
    # Run history is the feature: what changed tier, and why. Two runs must be
    # able to disagree about the same lot without one overwriting the other.
    first, second = await make_run(session), await make_run(session)
    lot = await make_lot(session)
    await make_design(session)

    session.add_all(
        [
            FlatsLotResult(lot_id=lot.id, design_key="pod56x36@1", run_id=first.id, tier="review"),
            FlatsLotResult(lot_id=lot.id, design_key="pod56x36@1", run_id=second.id, tier="green"),
        ]
    )
    await session.flush()

    count = len((await session.execute(select(FlatsLotResult))).all())
    assert count == 2


async def test_a_lot_is_unique_per_county_and_taxlot(session: AsyncSession) -> None:
    await make_lot(session, "1S2E05DA 01900")

    await make_lot(session, "1S2E05DA 01900", county="clackamas")  # same tlid, other county: fine
    with pytest.raises(IntegrityError):
        await make_lot(session, "1S2E05DA 01900")
        await session.flush()


async def test_a_design_version_is_claimed_once(session: AsyncSession) -> None:
    # Immutability is enforced here, not just by convention: a dimensional
    # change has to bump the version, because results already name the old key.
    await make_design(session, "pod56x36@1")

    with pytest.raises(IntegrityError):
        session.add(
            FlatsDesign(
                key="pod56x36@1-again",
                design_id="pod56x36",
                version=1,
                label="Sneakily different",
                typology="townhome_rear_court",
                width_ft=60,
                depth_ft=36,
                units=4,
                stories=2,
                height_ft=26,
            )
        )
        await session.flush()


# --- durable review decisions ----------------------------------------


async def test_a_decision_outlives_the_lot_row_it_was_about(session: AsyncSession) -> None:
    # The pipeline rebuilds flats.lots on every run. A decision keyed on a lot
    # id would evaporate with it and the review queue would reset every run.
    lot = await make_lot(session, "1S2E05DA 01900")
    session.add(
        FlatsReviewDecision(
            county="multnomah",
            tlid="1S2E05DA 01900",
            check_code="lot",
            verdict="green",
            reason="Alley access confirmed on site visit.",
        )
    )
    await session.flush()

    await session.delete(lot)
    await session.flush()

    survivor = (await session.execute(select(FlatsReviewDecision))).scalar_one()
    assert survivor.verdict == "green"
    assert survivor.tlid == "1S2E05DA 01900"


async def test_only_one_live_decision_per_lot_design_and_check(session: AsyncSession) -> None:
    def decision(**kw):
        return FlatsReviewDecision(
            county="multnomah",
            tlid="1S2E05DA 01900",
            check_code="parking",
            verdict="red",
            reason="No feasible curb cut.",
            **kw,
        )

    session.add(decision())
    await session.flush()

    with pytest.raises(IntegrityError):
        session.add(decision())
        await session.flush()


async def test_a_superseded_decision_makes_room_for_the_next(session: AsyncSession) -> None:
    # Supersede rather than update, so the reversal history survives: who said
    # what, when, and why, including the verdicts later overturned.
    from datetime import UTC, datetime

    session.add(
        FlatsReviewDecision(
            county="multnomah",
            tlid="1S2E05DA 01900",
            check_code="parking",
            verdict="red",
            reason="No feasible curb cut.",
            superseded_at=datetime.now(UTC),
        )
    )
    await session.flush()

    session.add(
        FlatsReviewDecision(
            county="multnomah",
            tlid="1S2E05DA 01900",
            check_code="parking",
            verdict="green",
            reason="Frontage re-measured; 34% rule satisfied.",
        )
    )
    await session.flush()

    live = (
        await session.execute(
            select(FlatsReviewDecision).where(FlatsReviewDecision.superseded_at.is_(None))
        )
    ).scalars().all()
    assert [d.verdict for d in live] == ["green"]
    assert len((await session.execute(select(FlatsReviewDecision))).all()) == 2


async def test_a_decision_survives_its_reviewer_leaving(session: AsyncSession) -> None:
    # SET NULL, not CASCADE: deleting a user must not delete the record of what
    # they decided about a lot.
    from app.models.org import Organization, User

    org = Organization(id=uuid.uuid4(), name="East County Housing", slug="ech")
    user = User(
        id=uuid.uuid4(), name="Reviewer", email="r@example.com", hashed_password="x", org_id=org.id
    )
    session.add_all([org, user])
    await session.flush()

    session.add(
        FlatsReviewDecision(
            county="multnomah",
            tlid="1S2E05DA 01900",
            check_code="lot",
            verdict="green",
            reason="Confirmed.",
            org_id=org.id,
            reviewer_user_id=user.id,
        )
    )
    await session.flush()

    await session.delete(user)
    await session.flush()

    survivor = (await session.execute(select(FlatsReviewDecision))).scalar_one()
    assert survivor.reviewer_user_id is None
    assert survivor.verdict == "green"
