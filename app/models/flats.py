"""FLATS screening schema — ``flats.*``, not ``public.*``.

FLATS and the underwriting platform share a database and an auth system. They do
not share a namespace. Every table here lives in a dedicated Postgres schema so
the product boundary is structural rather than a naming convention, and so a
query against ``public`` can never accidentally reach screening data.

**This is not the decommissioned parcel subsystem.** Migration 0113 dropped
``public.parcels`` (446K rows) along with the county-GIS scrapers and the map,
because that pipeline was lookup-only and tagged jurisdictions wrongly. FLATS is
batch-fed and validated, and it shares none of that schema. Never ``parcels``,
never ``public.lots``.

Three ideas shape the keying, and all three are expensive to retrofit:

**Results are keyed ``(lot, design, run)`` from the start.** A screen that can
only answer for one building has a one-building shelf life. Design-independent
facts — envelope, fit frontier, slope, sewer, acquisition economics — live once
on :class:`FlatsLot`; only what genuinely varies per building lands in
:class:`FlatsLotResult`.

**Runs are immutable and comparable.** Every result names the run that produced
it, and every run records the code and rule versions behind it, so "which lots
changed tier, and which rule change caused it" is a join rather than an
archaeology project.

**Human decisions outlive the run that prompted them.** :class:`FlatsReviewDecision`
is keyed on the durable taxlot id rather than a row id, so a re-run replays past
verdicts instead of resetting the queue. Without that nobody works the queue
twice.

Where the eventual shape of a check or a fact is still open, it is JSONB rather
than a guessed column. The keying is what has to be right now; the payload can
grow without a migration.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

#: Postgres schema every FLATS table lives in.
SCHEMA = "flats"

#: Working CRS: NAD83(HARN) / Oregon North, **feet**. Every length in this schema
#: is feet, and every area square feet, because the zoning code is written in
#: them and converting at the boundary is one fewer place to be wrong.
SRID_WORKING = 2913

#: WGS84, for map display and anything leaving the system.
SRID_WGS84 = 4326


class FlatsRun(Base):
    """One execution of the screening pipeline.

    Records the inputs a result depends on — code version, rule-config version,
    which designs and counties were in scope — so two runs can be diffed and a
    tier change can be attributed to the change that caused it.
    """

    __tablename__ = "runs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: running | complete | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")

    #: Git SHA of the tree that produced this run.
    code_version: Mapped[str | None] = mapped_column(String(64))
    #: Content hash of flats/config/jurisdictions. A rule edit changes results
    #: even when no code changed, so it needs its own version.
    rules_version: Mapped[str | None] = mapped_column(String(64))

    #: Design keys (``id@version``) evaluated. Empty means design-independent
    #: stages only.
    design_keys: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    counties: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    #: Slack/tolerance settings and any other knobs, verbatim.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


class FlatsDesign(Base):
    """A snapshot of one catalog entry, as it was when a run used it.

    The YAML catalog in ``flats/config/pods/`` is the source of truth, but a run
    from six months ago has to stay interpretable after the file changes. Rows
    here are written once per ``id@version`` and never updated; a dimensional
    change bumps the version and creates a new row.
    """

    __tablename__ = "designs"
    __table_args__ = (
        UniqueConstraint("design_id", "version", name="uq_flats_designs_id_version"),
        {"schema": SCHEMA},
    )

    #: ``id@version`` — the identity results carry.
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    design_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    typology: Mapped[str] = mapped_column(String(48), nullable=False)

    width_ft: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    depth_ft: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    stories: Mapped[int] = mapped_column(Integer, nullable=False)
    height_ft: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    #: active | archived. Archived designs stay queryable — old results name them.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    #: The full YAML as loaded, including parking, delivery and assumptions.
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    results: Mapped[list["FlatsLotResult"]] = relationship(back_populates="design")


class FlatsLot(Base):
    """One taxlot and everything true of it regardless of what gets built.

    Deliberately design-independent. Envelope, fit frontier, slope, sewer,
    frontage class and acquisition economics are computed once and shared across
    every design in the catalog — that asymmetry is what makes a ten-design
    catalog affordable instead of ten times the work.

    Keyed internally by a bigint because a 300k-lot corpus times a ten-design
    catalog is three million result rows, and the foreign key is carried on all
    of them. ``(county, tlid)`` is the natural key and the one humans and
    external systems use.
    """

    __tablename__ = "lots"
    __table_args__ = (
        UniqueConstraint("county", "tlid", name="uq_flats_lots_county_tlid"),
        Index("ix_flats_lots_jurisdiction_zone", "jurisdiction", "zone"),
        Index("ix_flats_lots_geom", "geom", postgresql_using="gist"),
        Index("ix_flats_lots_centroid", "centroid", postgresql_using="gist"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    #: Metro RLIS taxlot id. Durable across pipeline re-runs, which is why review
    #: decisions key on it rather than on ``id``.
    tlid: Mapped[str] = mapped_column(String(40), nullable=False)
    county: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Rule-layer id, e.g. ``or/multnomah/portland``. Joins to the encoded rules.
    jurisdiction: Mapped[str] = mapped_column(String(80), nullable=False)
    #: Zone code as the GIS layer spelled it, before normalization.
    zone_raw: Mapped[str | None] = mapped_column(String(40))
    #: Normalized zone code, matching a key in the jurisdiction's rule file.
    zone: Mapped[str | None] = mapped_column(String(40))

    site_address: Mapped[str | None] = mapped_column(String(255))
    area_sqft: Mapped[float | None] = mapped_column(Numeric(14, 2))

    geom: Mapped[Any | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=SRID_WORKING, spatial_index=False)
    )
    #: WGS84 centroid, for map display and address-free identification.
    centroid: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=SRID_WGS84, spatial_index=False)
    )

    #: land | excluded | suspect, from the condo / air-parcel detector. Excluded
    #: rows are retained rather than deleted so an over-eager exclusion stays
    #: visible and reversible.
    condo_verdict: Mapped[str | None] = mapped_column(String(16))
    condo_reason: Mapped[str | None] = mapped_column(String(48))

    #: Design-independent computed facts: buildable envelope, the
    #: max-depth-per-width fit frontier, slope, sewer availability, frontage
    #: class, owner propensity, acquisition economics. JSONB because these stages
    #: are still being built and their column set would churn.
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")

    first_seen_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.runs.id", ondelete="SET NULL")
    )
    updated_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.runs.id", ondelete="SET NULL")
    )

    results: Mapped[list["FlatsLotResult"]] = relationship(
        back_populates="lot", cascade="all, delete-orphan"
    )


class FlatsLotResult(Base):
    """The screening verdict for one lot, one design, one run.

    Only what genuinely varies per building lives here: the site plan, the
    parking layout, the set-access check, and the tier those produce.

    ``slack_ft`` is the margin on the tightest binding check — how much room the
    lot has left before it fails. It is what makes the answer actionable: a lot
    missing by four inches is a different conversation than one missing by
    twenty feet.
    """

    __tablename__ = "lot_results"
    __table_args__ = (
        Index("ix_flats_lot_results_run_tier", "run_id", "tier"),
        Index("ix_flats_lot_results_design_tier", "design_key", "tier"),
        {"schema": SCHEMA},
    )

    lot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.lots.id", ondelete="CASCADE"), primary_key=True
    )
    design_key: Mapped[str] = mapped_column(
        String(80), ForeignKey(f"{SCHEMA}.designs.key", ondelete="RESTRICT"), primary_key=True
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.runs.id", ondelete="CASCADE"), primary_key=True
    )

    #: green | review | red. REVIEW is not a failure state — it is the honest
    #: answer whenever the rules behind a lot are not verified.
    tier: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Margin on the tightest binding check, in feet. Negative means it fails.
    slack_ft: Mapped[float | None] = mapped_column(Numeric(10, 3))
    #: Reason codes for what binds, tightest first. Drives the histogram that
    #: says which rule is costing the most lots.
    binding: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    #: Every check: observed value, threshold, the citation behind the threshold,
    #: pass/fail, slack.
    checks: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")

    #: Generated plan — building, driveway, stalls, open space — in working feet.
    site_plan: Mapped[Any | None] = mapped_column(
        Geometry("GEOMETRYCOLLECTION", srid=SRID_WORKING, spatial_index=False)
    )

    lot: Mapped["FlatsLot"] = relationship(back_populates="results")
    design: Mapped["FlatsDesign"] = relationship(back_populates="results")


class FlatsRule(Base):
    """A resolved rule value as one run saw it.

    The YAML tree is the source of truth; this is the per-run snapshot, so a
    result stays explainable after the rules change. It carries the resolved
    value *and* the layer and citation it came from, which is what lets lot
    detail show "front setback 10 ft — PCC 33.110 Table 110-4" beside "parking
    1/unit — OAR 660-046-0220 (state, preempts city 2/unit)".
    """

    __tablename__ = "rules"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "jurisdiction", "zone", "field", name="uq_flats_rules_run_zone_field"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.runs.id", ondelete="CASCADE"), nullable=False
    )

    jurisdiction: Mapped[str] = mapped_column(String(80), nullable=False)
    zone: Mapped[str] = mapped_column(String(40), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    #: draft | encoded | verified | stale. Only `verified` may produce GREEN or RED.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    #: Layer that supplied the value, e.g. ``or`` for a state preemption.
    layer: Mapped[str | None] = mapped_column(String(80))
    #: True when this value overrode a more specific one under `preempts`.
    preempted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    cite: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text)
    retrieved: Mapped[date | None] = mapped_column(Date)
    reviewer: Mapped[str | None] = mapped_column(String(80))
    reviewed: Mapped[date | None] = mapped_column(Date)


class FlatsClause(Base):
    """One RASE-tagged sentence of code text.

    The coverage ledger catches a zone nobody encoded. It would never catch a
    missed exception clause inside a zone believed finished — that is what this
    is for. A clause with no tag is a sentence nobody has decided about, and it
    blocks its zone from `verified`.

    ``source_hash`` is the drift watch: when a nightly re-fetch of ``url``
    produces different text, everything encoded from it flips to `stale`.
    """

    __tablename__ = "clauses"
    __table_args__ = (
        Index("ix_flats_clauses_jurisdiction_section", "jurisdiction", "section"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    jurisdiction: Mapped[str] = mapped_column(String(80), nullable=False)
    section: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    #: Pointer into flats/provenance/ with a line range.
    quote: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    #: A | S | R | E | N. NULL means untagged, which is itself a gap.
    tag: Mapped[str | None] = mapped_column(String(1))
    #: Rule field this clause produces a value for, when it is a requirement.
    field: Mapped[str | None] = mapped_column(String(64))
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    source_hash: Mapped[str | None] = mapped_column(String(64))
    reviewer: Mapped[str | None] = mapped_column(String(80))
    reviewed: Mapped[date | None] = mapped_column(Date)


class FlatsReviewDecision(Base):
    """A human verdict that outlives the run that prompted it.

    Keyed on ``(county, tlid, design_key, check_code)`` rather than a lot row id,
    because the pipeline rebuilds ``flats.lots`` on every run and a decision keyed
    on a row id would evaporate with it. Decisions are replayed into each
    subsequent run. Without this the review queue resets every run and nobody
    works it twice.

    Superseding rather than updating keeps the history: who decided what, when,
    and why, including the verdicts that were later reversed.
    """

    __tablename__ = "review_decisions"
    __table_args__ = (
        Index(
            "uq_flats_review_active",
            "county",
            "tlid",
            "design_key",
            "check_code",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    county: Mapped[str] = mapped_column(String(40), nullable=False)
    tlid: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Empty string when the decision applies to the lot regardless of design.
    #: Not NULL — a nullable column would silently drop rows from the partial
    #: unique index and let duplicate active decisions accumulate.
    design_key: Mapped[str] = mapped_column(String(80), nullable=False, server_default="")
    #: Which check the human is overriding, or ``lot`` for the whole verdict.
    check_code: Mapped[str] = mapped_column(String(64), nullable=False)

    #: green | red. A human answer to a machine REVIEW.
    verdict: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL")
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlatsRuleSignature(Base):
    """A reviewer's verdict on one encoded standard, captured in the browser.

    Verification is a signature over a value, and the signature lives in the
    repository (``flats/config/verifications.jsonl``) hashed over the number and
    its citation, so editing either silently withdraws it. That property is the
    reason the log cannot be replaced by a table: a database row survives an
    edit to the YAML it was about, and a stale row certifying a number nobody
    read is the worst failure this system has.

    So this table is an inbox, not a source of truth. A reviewer comparing a
    value to its quoted line records the verdict here; a later drain writes the
    verified ones into the log for commit and stamps ``exported_at``. Rules load
    from the repository either way — an undrained signature has simply not taken
    effect yet, which is visible rather than silent.
    """

    __tablename__ = "rule_signatures"
    __table_args__ = (
        Index(
            "ix_flats_rule_signatures_pending",
            "decided_at",
            postgresql_where=text("exported_at IS NULL"),
        ),
        Index(
            "ix_flats_rule_signatures_unbundled",
            "decided_at",
            postgresql_where=text("bundled_at IS NULL"),
        ),
        Index("ix_flats_rule_signatures_fingerprint", "fingerprint"),
        Index("ix_flats_rule_signatures_value", "layer", "zone", "field", "when_key"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    #: Layer id, e.g. ``or/clackamas/wilsonville``.
    layer: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Zone code, or ``(layer defaults)`` for a layer-wide value.
    zone: Mapped[str] = mapped_column(String(40), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Sorted condition and band tokens joined by ``+``, empty for the base
    #: value. The same address the signing log uses, so a drain is a copy.
    when_key: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")

    #: The number as it stood when the reviewer looked at it.
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    cite: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    quote: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    #: verified | rejected | unclear. The third is not indecision — it is
    #: the reviewer saying the page does not answer the question, which is a
    #: finding about the encoding and not about the number.
    verdict: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    reviewer: Mapped[str] = mapped_column(String(80), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: When a drain wrote this into the repository log. NULL is the queue.
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: The code text that was on screen, verbatim, and the citation it was
    #: shown under. Kept so a note can be read months later by someone who
    #: was not there — and so a bundle handed to an encoder carries its own
    #: evidence rather than a reference to a page that has since changed.
    shown: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    shown_ref: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    #: Hash over the address, the value, its citation and its quote — the
    #: same one the verification log signs with. It is what makes iteration
    #: legible: change the encoding in response to a note and the
    #: fingerprint stops matching, so the item resurfaces as changed rather
    #: than sitting in a list nobody can tell is stale.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")

    #: When a reviewer handed this on to whoever will fix it. Separate from
    #: ``exported_at``: that is the drain writing a confirmation into the
    #: repository, this is a problem leaving the reviewer's desk. A row can
    #: be one, the other, both or neither.
    bundled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlatsCrossrefRuling(Base):
    """A reviewer's decision about a chapter the store cannot open.

    Fetch triage asks one question — can this chapter change a number we screen
    on? — and the answer is a tagged outcome plus the reasoning behind it. The
    outcome is what a ledger can count; the note is what the next reader needs,
    and neither is worth much alone.

    An inbox, not a source of truth, for the same reason
    :class:`FlatsRuleSignature` is one. Rules load from the jurisdiction YAML in
    the repository, and the container rebuilds that YAML from git on every
    deploy — so a decision recorded only here has not taken effect yet, and a
    decision spliced only into a running container's YAML is gone at the next
    release. The drain closes the gap in the safe direction: rows land here
    immediately, and ``scripts/flats_drain_crossref_rulings.py`` writes them
    into the rule files for commit and stamps ``exported_at``.

    Append-only. A reviewer who changes their mind writes a second row rather
    than editing the first, and the latest ``decided_at`` for a
    ``(layer, ref)`` is the one that counts — the record of who believed what,
    and when, survives being wrong.
    """

    __tablename__ = "crossref_rulings"
    __table_args__ = (
        Index(
            "ix_flats_crossref_rulings_pending",
            "decided_at",
            postgresql_where=text("exported_at IS NULL"),
        ),
        Index("ix_flats_crossref_rulings_ref", "layer", "ref", "decided_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    #: Layer id, e.g. ``or/multnomah/gresham``.
    layer: Mapped[str] = mapped_column(String(120), nullable=False)
    #: The section number as the ledger prints it, e.g. ``7.0221``.
    ref: Mapped[str] = mapped_column(String(40), nullable=False)

    #: One of ``flats.rules.model.CROSSREF_OUTCOMES``. Stored as text rather
    #: than a database enum: the vocabulary was derived from rulings already
    #: written and grew by one the first day it was used, so it will grow
    #: again, and a migration per word is a reason not to add the word.
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Why. Required — a row closed with a word nobody can check is worse than
    #: an open row, because the open row still shows the sentence.
    note: Mapped[str] = mapped_column(Text, nullable=False)

    #: What the queue showed when the decision was made, so a ruling can be
    #: re-read against what it was actually about. The card is rebuilt from
    #: documents that may since have been re-fetched.
    lots: Mapped[int | None] = mapped_column(Integer)
    fields_touched: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )

    decided_by: Mapped[str] = mapped_column(String(200), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: When the drain wrote this into the repository. NULL means pending, and
    #: pending is visible in the queue rather than silent.
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlatsReadingRuling(Base):
    """A reviewer's decision about one section of code nobody had read.

    The reading queues regroup :mod:`flats.encode.uncited` -- every measured
    statement in a document we hold that no encoded value quotes -- into
    section cards, and a card asks one of four questions. This is where the
    answer lands.

    Same inbox bargain as ``FlatsCrossrefRuling`` (0128) and for the same
    reason: rules load from the repository, the container rebuilds those files
    from git on every deploy, and a decision spliced into a running container's
    YAML is gone at the next release. ``scripts/flats_drain_reading_rulings.py``
    writes these into the rule files for commit and stamps ``exported_at``.

    Append-only. A reviewer who changes their mind writes a second row, and the
    latest ``decided_at`` for a section is the one that counts.
    """

    __tablename__ = "reading_rulings"
    __table_args__ = (
        Index(
            "ix_flats_reading_rulings_pending",
            "decided_at",
            postgresql_where=text("exported_at IS NULL"),
        ),
        Index("ix_flats_reading_rulings_card", "layer", "path", "section", "decided_at"),
        Index("ix_flats_reading_rulings_fingerprint", "fingerprint"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    #: Layer id, e.g. ``or/multnomah/gresham``.
    layer: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Store path of the document, e.g. ``or/multnomah/gresham/4.1100.txt``.
    path: Mapped[str] = mapped_column(String(300), nullable=False)
    #: The section heading the lines sit under, as the document prints it.
    #: Empty where the document prints no headings -- a real state, not a gap.
    section: Mapped[str] = mapped_column(String(60), nullable=False, server_default="")

    #: Which of the four queues asked. Stored because the same section can be
    #: re-routed when the encoding changes, and a ruling read back without
    #: knowing which question it answered is a word without a sentence.
    queue: Mapped[str] = mapped_column(String(16), nullable=False)
    #: One of ``flats.rules.model.READING_ALL``. Text rather than an enum, for
    #: the reason the crossref vocabulary is: it grew the first day it was used
    #: and a migration per word is a reason not to add the word.
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    #: The section as it read when the decision was made. When a document is
    #: re-fetched and the section moves, this stops matching and the card
    #: reopens -- flagged, with the old text and the new shown together --
    #: rather than staying silently closed against words nobody has seen. The
    #: same bargain ``rule_signatures`` strikes over a number and its citation.
    fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)

    #: What the card showed, so a ruling can be re-read against its subject.
    lots: Mapped[int | None] = mapped_column(Integer)
    lines: Mapped[int | None] = mapped_column(Integer)
    fields_touched: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )

    decided_by: Mapped[str] = mapped_column(String(200), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: When the drain wrote this into the repository. NULL means pending, and
    #: pending is visible in the queue rather than silent.
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlatsWordRuling(Base):
    """A reviewer's decision about what one word means in one jurisdiction.

    The ledger under the other two. ``crossref_rulings`` records a chapter we
    cannot open and ``reading_rulings`` a chapter we opened and decided about;
    this records what the *words* those chapters are written in mean here. A
    number read correctly out of a sentence is still wrong if the sentence
    measures it in a word this city defines its own way, which is why this
    queue is worked before signing rather than after it.

    Keyed by ``(layer, term)`` where the term is ours -- the key
    :data:`flats.encode.words.GOVERNS` uses -- not the city's spelling. One
    code files the entry "Lot, Width" and another writes "lot width"; they are
    answering the same question, and keying on their spelling would make the
    ledger uncountable.

    Same inbox bargain as 0128 and 0129, for the same reason: rules load from
    the repository, the container rebuilds those files from git on every
    deploy, and a decision spliced into a running container's YAML is gone at
    the next release. ``scripts/flats_drain_word_rulings.py`` writes these into
    the rule files for commit and stamps ``exported_at``.

    Append-only. A reviewer who changes their mind writes a second row, and the
    latest ``decided_at`` for a word is the one that counts.
    """

    __tablename__ = "word_rulings"
    __table_args__ = (
        Index(
            "ix_flats_word_rulings_pending",
            "decided_at",
            postgresql_where=text("exported_at IS NULL"),
        ),
        Index("ix_flats_word_rulings_card", "layer", "term", "decided_at"),
        Index("ix_flats_word_rulings_fingerprint", "fingerprint"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    #: Layer id, e.g. ``or/multnomah/gresham``.
    layer: Mapped[str] = mapped_column(String(120), nullable=False)
    #: The word, in our vocabulary — a key of ``flats.encode.words.GOVERNS``.
    term: Mapped[str] = mapped_column(String(60), nullable=False)

    #: What was known about the word when the question was put: ``defined``,
    #: ``silent`` or ``unread``. Stored because those are three different
    #: questions sharing no answer, and a ruling read back without knowing
    #: which was asked is a word without a sentence.
    standing: Mapped[str] = mapped_column(String(16), nullable=False)
    #: One of ``flats.rules.model.WORD_ALL``. Text rather than an enum, for the
    #: reason the other two vocabularies are: they grow on first real use and a
    #: migration per word is a reason not to add the word.
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    #: The definitions this card showed, as they read. A glossary is
    #: re-extracted whenever a document is re-fetched — and this corpus has
    #: already had entries appear, split and triple on a re-read — so a ruling
    #: whose fingerprint no longer matches reopens rather than staying closed
    #: against wording nobody has seen.
    fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)

    #: What the card showed, so a ruling can be re-read against its subject.
    lots: Mapped[int | None] = mapped_column(Integer)
    #: Encoded values resting on this word here — the cost of being wrong, in
    #: numbers that would have to be read again.
    values_touched: Mapped[int | None] = mapped_column(Integer)
    fields_touched: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )

    decided_by: Mapped[str] = mapped_column(String(200), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: When the drain wrote this into the repository. NULL means pending, and
    #: pending is visible in the queue rather than silent.
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
