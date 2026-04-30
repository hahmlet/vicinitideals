"""Cross-source broker deduplication.

Merges Broker rows that represent the same person across sources (LoopNet vs
Crexi) using `(license_number, license_state)` as the primary identity key.
Falls back to exact `(first_name, last_name)` match for license-less rows.

A row is considered a "winner" when it has the most listings, then Oregon
enrichment, then a `crexi_broker_id` (oldest historical track). Loser fields
are copied into the winner only when the winner's slot is NULL — never
overwriting populated values. License-locked rows are never replaced.

Designed to run idempotently:
  - One-shot via scripts/merge_duplicate_brokers.py
  - Wired into oregon_elicense_sweep so each enrichment pass also reconciles
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker, BrokerDisciplinaryAction
from app.models.project import ScrapedListing

# Suffixes/credentials that get appended to last_name and shouldn't break match
_NAME_SUFFIX_RE = re.compile(
    r"\s*[,]?\s*\b(?:CCIM|MBA|SIOR|PC|JR|SR|II|III|IV|ESQ|MAI|CRE|CPM)\b\.?",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    s = _NAME_SUFFIX_RE.sub("", str(name))
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip().lower()
    return s


def _names_compatible(a_first: str | None, a_last: str | None,
                      b_first: str | None, b_last: str | None) -> bool:
    """Loose name match: first 3 chars of first_name + normalized last match."""
    af, al = _normalize_name(a_first), _normalize_name(a_last)
    bf, bl = _normalize_name(b_first), _normalize_name(b_last)
    if not al or not bl or al != bl:
        return False
    if not af or not bf:
        return False
    # Allow nickname expansion: "ben"/"benjamin" share first 3 chars
    return af[:3] == bf[:3]


@dataclass
class MergeReport:
    license_groups: int = 0
    license_groups_merged: int = 0
    license_groups_skipped_name_mismatch: int = 0
    name_groups: int = 0
    name_groups_merged: int = 0
    listings_reassigned: int = 0
    disciplinary_actions_reassigned: int = 0
    brokers_deleted: int = 0
    skipped_locked: int = 0
    skipped_groups: list[dict[str, Any]] = field(default_factory=list)


def _pick_winner(brokers: list[Broker]) -> Broker:
    """Score by listings → oregon → crexi_broker_id presence → oldest."""
    return max(
        brokers,
        key=lambda b: (
            len(b.scraped_listings) if b.scraped_listings is not None else 0,
            1 if b.oregon_lookup_status == "success" else 0,
            1 if b.crexi_broker_id is not None else 0,
            1 if b.license_number_locked else 0,
            -((b.id.int) if isinstance(b.id, uuid.UUID) else 0),  # tiebreak
        ),
    )


def _copy_missing_fields(winner: Broker, loser: Broker) -> None:
    """Copy non-null loser fields into winner where winner is null. Don't
    touch license_number when winner is locked."""
    fields_to_copy = (
        "crexi_broker_id", "crexi_global_id", "loopnet_broker_id",
        "first_name", "last_name", "thumbnail_url",
        "is_platinum", "number_of_assets", "brokerage_id",
        "email", "phone",
        "license_personal_street", "license_personal_street2",
        "license_personal_city", "license_personal_state",
        "license_personal_zip",
        "license_type", "license_status",
        "oregon_last_pulled_at", "oregon_lookup_status",
        "oregon_failure_count", "oregon_detail_url",
    )
    for f in fields_to_copy:
        w_val = getattr(winner, f, None)
        l_val = getattr(loser, f, None)
        if w_val in (None, "", False) and l_val not in (None, ""):
            setattr(winner, f, l_val)
    # License: only fill if winner has no license AND not locked
    if not winner.license_number_locked and not winner.license_number and loser.license_number:
        winner.license_number = loser.license_number
        winner.license_state = loser.license_state


async def _merge_group(
    session: AsyncSession, brokers: list[Broker], report: MergeReport,
) -> None:
    """Merge a group of duplicate Broker rows into one winner."""
    if len(brokers) < 2:
        return
    winner = _pick_winner(brokers)
    losers = [b for b in brokers if b.id != winner.id]

    for loser in losers:
        # Skip if loser is license-locked and winner doesn't have its license —
        # that's a manual alignment we shouldn't undo.
        if loser.license_number_locked and not winner.license_number_locked:
            report.skipped_locked += 1
            continue

        _copy_missing_fields(winner, loser)

        # Reassign listings
        result = await session.execute(
            update(ScrapedListing)
            .where(ScrapedListing.broker_id == loser.id)
            .values(broker_id=winner.id)
            .returning(ScrapedListing.id)
        )
        report.listings_reassigned += len(result.fetchall())

        # Reassign disciplinary actions
        result = await session.execute(
            update(BrokerDisciplinaryAction)
            .where(BrokerDisciplinaryAction.broker_id == loser.id)
            .values(broker_id=winner.id)
            .returning(BrokerDisciplinaryAction.id)
        )
        report.disciplinary_actions_reassigned += len(result.fetchall())

        await session.delete(loser)
        report.brokers_deleted += 1


async def merge_duplicate_brokers(session: AsyncSession) -> MergeReport:
    """Find and merge duplicate Broker rows. Idempotent."""
    report = MergeReport()

    # Phase 1: license-based dedup
    stmt = (
        select(Broker.license_number, Broker.license_state)
        .where(Broker.license_number.isnot(None), Broker.license_number != "")
        .group_by(Broker.license_number, Broker.license_state)
        .having(func.count(Broker.id) > 1)
    )
    license_groups = (await session.execute(stmt)).all()
    report.license_groups = len(license_groups)

    for lic_num, lic_state in license_groups:
        rows = list((await session.execute(
            select(Broker).where(
                Broker.license_number == lic_num,
                Broker.license_state == lic_state,
            )
        )).scalars())
        # Eagerly load listings count for winner-picking
        for b in rows:
            count_q = select(func.count(ScrapedListing.id)).where(
                ScrapedListing.broker_id == b.id
            )
            b.scraped_listings = [None] * int(
                (await session.execute(count_q)).scalar_one()
            )

        # Verify names compatible across all rows
        first = rows[0]
        all_compatible = all(
            _names_compatible(first.first_name, first.last_name, r.first_name, r.last_name)
            for r in rows[1:]
        )
        if not all_compatible:
            report.license_groups_skipped_name_mismatch += 1
            report.skipped_groups.append({
                "reason": "name_mismatch",
                "license_number": lic_num,
                "license_state": lic_state,
                "names": [f"{r.first_name} {r.last_name}" for r in rows],
                "broker_ids": [str(r.id) for r in rows],
            })
            continue

        await _merge_group(session, rows, report)
        report.license_groups_merged += 1

    # Phase 2: name-only dedup (no license, exact name match)
    # After phase 1 commits, re-query for residual name dupes among license-less rows.
    await session.flush()
    stmt = (
        select(Broker.first_name, Broker.last_name)
        .where(
            Broker.first_name.isnot(None),
            Broker.last_name.isnot(None),
            (Broker.license_number.is_(None) | (Broker.license_number == "")),
        )
        .group_by(Broker.first_name, Broker.last_name)
        .having(func.count(Broker.id) > 1)
    )
    name_groups = (await session.execute(stmt)).all()
    report.name_groups = len(name_groups)

    for first_name, last_name in name_groups:
        rows = list((await session.execute(
            select(Broker).where(
                Broker.first_name == first_name,
                Broker.last_name == last_name,
                (Broker.license_number.is_(None) | (Broker.license_number == "")),
            )
        )).scalars())
        for b in rows:
            count_q = select(func.count(ScrapedListing.id)).where(
                ScrapedListing.broker_id == b.id
            )
            b.scraped_listings = [None] * int(
                (await session.execute(count_q)).scalar_one()
            )
        await _merge_group(session, rows, report)
        report.name_groups_merged += 1

    await session.flush()
    return report
