"""Rule value model — every encoded number carries its own proof.

The unit of encoding is a :class:`Value`, not a bare scalar. A value knows the
code clause it came from, the URL and quoted excerpt backing it, when that text
was retrieved, and whether a human has confirmed it. Provenance survives
resolution (see :mod:`flats.rules.resolver`) so a lot detail page can name the
layer and the code section behind every threshold it displays.

Two authoring forms, both valid:

.. code-block:: yaml

    # full — value carries its own citation
    setback_front_ft:
      value: 10
      cite: "PCC 33.110.220, Table 110-4"
      url: "https://www.portland.gov/code/33/100s/110"
      quote: provenance/or/multnomah/portland/33.110-t110-4.txt#L42-L48
      retrieved: 2026-08-12
      status: verified
      reviewer: sjk
      reviewed: 2026-08-14

    # shorthand — inherits the zone's cite_default, status defaults to draft
    setback_side_ft: 5

Shorthand plus ``cite_default`` is what keeps the format writable; per-value
override is what keeps it auditable. Both are required.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Collection, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from flats.rules.conditions import condition
from flats.rules.fields import FieldDef, field


class Status(str, enum.Enum):
    """Encoding lifecycle. Only ``verified`` is trusted by the screen."""

    #: Extraction output. Loadable, never trusted.
    draft = "draft"
    #: Hand-entered but not yet confirmed against the quoted text.
    encoded = "encoded"
    #: A human confirmed the value against its quote.
    verified = "verified"
    #: Was verified; the source text hash has since changed.
    stale = "stale"

    @property
    def trusted(self) -> bool:
        return self is Status.verified


#: A Census GEOID prefix on a directory name, e.g. '4159000-portland'.
_GEOID = re.compile(r"^\d{5,7}-")

#: Meta keys permitted alongside field names inside a zone block.
ZONE_META = frozenset({"zone", "cite_default", "notes", "clauses", "like", "section"})
#: Meta keys permitted at the top level of a jurisdiction/layer file.
LAYER_META = frozenset(
    {
        "layer",
        "code",
        "kind",
        "label",
        "eligible",
        "cite_default",
        "notes",
        "defaults",
        "zones",
        "ingest",
    }
)


class Provenance(BaseModel):
    """Where a value came from. Never optional on a loaded value."""

    model_config = ConfigDict(frozen=True)

    cite: str = Field(min_length=3, description="Human-readable code citation.")
    url: str = Field(min_length=5, description="Fetchable source URL — the drift-watch target.")
    retrieved: date = Field(description="Date the source text was fetched and hashed.")
    quote: str | None = Field(
        default=None,
        description="Path into flats/provenance/ with a line range, e.g. 'or/.../33.110.txt#L42-L48'.",
    )
    clause: str | None = Field(
        default=None,
        description="Clause-ledger id. Links this value to its RASE-tagged source clause.",
    )


#: Lot measurements a standard may be banded on. Registered for the same
#: reason conditions and fields are: "lot_size" beside "lot_sqft" would be two
#: axes nobody can reconcile, and the units have to be unambiguous — a band
#: read in square feet and applied in acres is off by 43,560.
LOT_MEASURES: tuple[str, ...] = ("lot_sqft", "lot_width_ft", "lot_depth_ft")


class Band(BaseModel):
    """A range of lot sizes one column of a banded table was written for.

    Milwaukie's Table 19.301.4 is one zone, R-MD, in four columns: lots of
    1,500–2,999 sq ft, 3,000–4,999, 5,000–6,999, and 7,000 and up. The street
    side setback is 5 ft in the first and 20 ft in the last. Neither number is
    "the R-MD street side setback", and encoding either one as though it were
    applies a four-times error to most of the city.

    That is not a condition. Nobody elects it, nobody applies for it, and it
    is not observed the way a corner or an alley is — it is arithmetic on the
    lot we are already screening. So it selects a variant the way a condition
    does, and is expressed as what it is: a range on a measurement.

    Bounds are inclusive, because codes write inclusive bands ("3,000–4,999")
    and the next band starts at the next whole foot. An open end is ``None``:
    "7,000 and up" is ``at_least=7000`` with no ceiling. Where a code splits on
    a single figure instead — "over 10,000" against "not exceeding 10,000" —
    the exclusive side is ``more_than``, so the two columns meet exactly and
    neither shares a lot with the other nor leaves a gap between them.
    """

    model_config = ConfigDict(frozen=True)

    measure: str
    at_least: float | None = None
    at_most: float | None = None
    #: An exclusive lower bound, for the codes that write "over 10,000 square
    #: feet" against "not exceeding 10,000". Wilsonville 4.113(.02) is the
    #: pattern, and it is the commonest two-column banding in Oregon. Written
    #: with inclusive bounds it can only be wrong: ``at_least: 10000`` beside
    #: ``at_most: 10000`` hands a 10,000 sq ft lot to whichever variant sorted
    #: first, and ``at_least: 10001`` leaves a 1 sq ft hole a lot falls
    #: silently through to the base value in.
    more_than: float | None = None

    @model_validator(mode="after")
    def _is_a_range_on_a_known_measure(self) -> Band:
        if self.measure not in LOT_MEASURES:
            raise ValueError(
                f"unknown lot measure {self.measure!r} — "
                f"one of {', '.join(LOT_MEASURES)}"
            )
        if self.at_least is not None and self.more_than is not None:
            raise ValueError(
                f"{self.measure}: a band has one lower bound — "
                f"'at_least' includes it, 'more_than' does not"
            )
        if self.at_least is None and self.at_most is None and self.more_than is None:
            # A band with no bounds is every lot, which is the base value
            # written twice under a name that hides it.
            raise ValueError(f"{self.measure}: a band needs at least one bound")
        if self.at_least is not None and self.at_most is not None:
            if self.at_least > self.at_most:
                raise ValueError(
                    f"{self.measure}: band {self.at_least}–{self.at_most} is empty"
                )
        if self.more_than is not None and self.at_most is not None:
            if self.more_than >= self.at_most:
                raise ValueError(
                    f"{self.measure}: band over {self.more_than} to {self.at_most} is empty"
                )
        return self

    @property
    def lower(self) -> tuple[float, bool]:
        """The lower bound and whether a lot sitting exactly on it is in.

        Read by the overlap check, which has to tell "10,000 and up" beside
        "up to 10,000" (they share a lot) from "over 10,000" beside the same
        (they do not).
        """
        if self.more_than is not None:
            return self.more_than, False
        return (self.at_least if self.at_least is not None else float("-inf")), True

    @property
    def upper(self) -> float:
        return self.at_most if self.at_most is not None else float("inf")

    @property
    def token(self) -> str:
        """How a reviewer names this band on the command line.

        A signature is over one sentence, and for a banded table the sentence
        is one column. ``--when lot_sqft:3000-4999`` addresses it the way
        ``--when affordable`` addresses a footnote.
        """
        high = _num(self.at_most) if self.at_most is not None else ""
        if self.more_than is not None:
            low = f">{_num(self.more_than)}"
        elif self.at_least is not None:
            low = _num(self.at_least)
        else:
            # A ceiling with no floor. Written as the comparison rather than as
            # an empty low end, because "lot_sqft:-10000" reads as a range
            # somebody forgot to finish typing.
            return f"{self.measure}:<={high}"
        return f"{self.measure}:{low}-{high}" if high else f"{self.measure}:{low}+"

    def holds(self, lot: Mapping[str, float] | None) -> bool | None:
        """Whether a lot falls in this band — ``None`` when it cannot be told.

        ``None`` rather than ``False``, and the difference decides a lot's
        colour. A lot we have not measured is not outside the band; it is a
        lot we cannot place, and treating that as "outside" would hand it the
        residual column's numbers with no warning.
        """
        if lot is None or self.measure not in lot:
            return None
        got = lot[self.measure]
        if self.at_least is not None and got < self.at_least:
            return False
        if self.more_than is not None and got <= self.more_than:
            return False
        if self.at_most is not None and got > self.at_most:
            return False
        return True


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


class Variant(BaseModel):
    """The same standard, at a different number, under stated conditions.

    "5 ft., or 10 ft. where the development is affordable" is one rule with two
    numbers, not two rules. Encoding only the base silently applies the wrong
    one to every project that took the incentive; encoding only the exception
    does the same in reverse.

    A variant carries its own citation and is signed on its own, because a
    reviewer who confirmed the base has not thereby confirmed the exception —
    they are usually in different sentences and often in different chapters.
    """

    model_config = ConfigDict(frozen=True)

    value: Any
    #: Registered condition names, all of which must hold. Empty is allowed
    #: only alongside a band: a variant with neither is the base value written
    #: twice, and two bases cannot be told apart.
    when: tuple[str, ...] = ()
    #: The lot sizes this number was written for, where the table bands them.
    #: A band narrows the same way a condition does, and both may apply: the
    #: affordable exception to the 3,000–4,999 sq ft column is one sentence.
    band: Band | None = None
    prov: Provenance
    status: Status = Status.draft
    reviewer: str | None = None
    reviewed: date | None = None

    @property
    def trusted(self) -> bool:
        return self.status.trusted

    @property
    def key(self) -> tuple[str, ...]:
        """What addresses this variant — its conditions, plus its band.

        Signing, orphan detection and the review queue all identify a variant
        by the set of things that select it. Before bands that set was the
        conditions alone, and a banded variant carrying none of them would
        have addressed as the base.
        """
        names = self.when + ((self.band.token,) if self.band else ())
        return tuple(sorted(names))

    @model_validator(mode="after")
    def _conditions_are_registered(self) -> Variant:
        # Same refusal as the field registry: an unregistered name is a typo
        # that would become a second lever nobody can satisfy.
        for name in self.when:
            try:
                condition(name)
            except KeyError as exc:
                # Re-raised as a ValueError so pydantic collects it with every
                # other problem in the file instead of aborting the load on the
                # first typo. Porting a jurisdiction should surface all of them.
                raise ValueError(exc.args[0]) from None
        return self

    @model_validator(mode="after")
    def _verified_needs_a_reviewer(self) -> Variant:
        if self.status is Status.verified and not (self.reviewer and self.reviewed):
            raise ValueError("a verified variant requires both 'reviewer' and 'reviewed'")
        return self


@dataclass(frozen=True, slots=True)
class Effective:
    """The number that applies to one lot, and where it came from.

    Separate from :class:`Value` because a value is what the code says and this
    is what the code says *here* — under this configuration, for this lot.
    """

    value: Any
    prov: Provenance
    status: Status
    reviewer: str | None = None
    reviewed: date | None = None
    #: Conditions that selected this number. Empty means the base applied.
    when: tuple[str, ...] = ()
    #: Populated when two variants applied equally well. The number carried is
    #: the base, but nothing may treat it as an answer.
    ambiguous: tuple[str, ...] = ()

    @property
    def trusted(self) -> bool:
        """Verified, and unambiguous. Ambiguity is not a trust question a
        signature can settle — both variants may be correctly transcribed and
        the encoding still not say which one governs."""
        return self.status.trusted and not self.ambiguous

    @property
    def conditional(self) -> bool:
        return bool(self.when)


class Value(BaseModel):
    """One encoded standard plus its proof and review state."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: Any
    prov: Provenance
    status: Status = Status.draft
    reviewer: str | None = None
    reviewed: date | None = None
    #: Exceptions to this standard, each under its own conditions. The base
    #: value applies when none of them do.
    variants: tuple[Variant, ...] = ()
    #: When True this value wins over anything a more specific layer says.
    #: This is how state preemption works: OAR 660-046-0220 caps required
    #: parking at 1 stall/unit, and a city asking for 2 does not get to
    #: override it. The one place the flat rule set needs defeasibility.
    preempts: bool = False

    @property
    def trusted(self) -> bool:
        return self.status.trusted

    @property
    def definition(self) -> FieldDef:
        return field(self.name)

    @model_validator(mode="after")
    def _verified_needs_a_reviewer(self) -> Value:
        # A `verified` value with nobody's name on it is indistinguishable from
        # an unreviewed one, which defeats the whole lifecycle.
        if self.status is Status.verified and not (self.reviewer and self.reviewed):
            raise ValueError(
                f"{self.name}: status 'verified' requires both 'reviewer' and 'reviewed'"
            )
        return self

    @model_validator(mode="after")
    def _value_matches_kind(self) -> Value:
        check_kind(self.name, self.value)
        for variant in self.variants:
            check_kind(self.name, variant.value)
        return self

    @model_validator(mode="after")
    def _variants_are_distinguishable(self) -> Value:
        seen: set[tuple[str, ...]] = set()
        for variant in self.variants:
            if not variant.when and variant.band is None:
                # A variant with nothing selecting it is the base value written
                # twice, and nothing downstream could say which one applies.
                raise ValueError(
                    f"{self.name}: a variant must state the condition(s) or the "
                    f"lot band it applies under"
                )
            key = variant.key
            if key in seen:
                raise ValueError(
                    f"{self.name}: two variants apply under the same conditions "
                    f"{sorted(key)} — one of them is wrong"
                )
            seen.add(key)
        return self

    @model_validator(mode="after")
    def _bands_do_not_overlap(self) -> Value:
        """Two columns of a banded table may not both claim the same lot.

        The bands are read off a table row by row, and a transcription that
        types 4,999 as 4,099 leaves a hole, while one that types 5,999 leaves
        an overlap. The hole is visible — a lot in it falls through to the
        base. The overlap is not: whichever variant sorted first would win,
        silently and differently per field.
        """
        banded = [v for v in self.variants if v.band is not None]
        for i, a in enumerate(banded):
            for b in banded[i + 1 :]:
                if a.band.measure != b.band.measure:
                    continue
                if frozenset(a.when) != frozenset(b.when):
                    continue
                (lo_a, closed_a), (lo_b, closed_b) = a.band.lower, b.band.lower
                if lo_a == lo_b:
                    low, closed = lo_a, closed_a and closed_b
                elif lo_a > lo_b:
                    low, closed = lo_a, closed_a
                else:
                    low, closed = lo_b, closed_b
                high = min(a.band.upper, b.band.upper)
                # Touching at a single point is an overlap only when the lower
                # bound includes that point: "over 10,000" and "up to 10,000"
                # meet at 10,000 and share no lot.
                if low < high or (low == high and closed):
                    raise ValueError(
                        f"{self.name}: lot bands {a.band.token} and {b.band.token} "
                        f"overlap — a lot in both would take whichever sorted first"
                    )
        return self

    # -- reading a value under a configuration -------------------------

    @property
    def levers(self) -> frozenset[str]:
        """Conditions that change this standard.

        What makes the batch view possible: a lever is worth offering only when
        flipping it moves a number some lot in the selection is bound by.
        """
        return frozenset(c for variant in self.variants for c in variant.when)



    @property
    def banded(self) -> bool:
        """True when the code states this standard per lot-size column.

        Load-bearing at the call site: the base of a banded standard is the
        residual column, not a safe default, so a screen that cannot measure
        the lot must not quietly use it.
        """
        return any(v.band is not None for v in self.variants)

    def under(
        self,
        active: Collection[str] = (),
        lot: Mapping[str, float] | None = None,
    ) -> Effective:
        """The value that applies when these conditions hold, on this lot.

        A variant applies when every condition it names is active and its band,
        if it has one, contains the lot. The most specific match wins —
        "affordable and corner" beats "affordable" — because a code that states
        both meant the pair to be different from either alone. A band counts
        toward specificity for the same reason a condition does.

        Two equally-specific matches are not resolved. Picking one would mean
        guessing which of two encoded rules the drafters meant, and that guess
        would be invisible in the output. The ambiguity is reported instead and
        the screen routes the lot to UNKNOWN, which is what not knowing is.

        An unmeasured lot against a banded standard is that same refusal. The
        base is the table's last column, so falling through to it would hand a
        2,000 sq ft lot the setbacks written for 7,000 sq ft ones and call the
        answer known.
        """
        if not self.variants:
            return Effective(self.value, self.prov, self.status, self.reviewer, self.reviewed)
        held = set(active)
        matches = []
        unmeasured: list[Variant] = []
        for v in self.variants:
            if not set(v.when) <= held:
                continue
            if v.band is None:
                matches.append(v)
                continue
            holds = v.band.holds(lot)
            if holds:
                matches.append(v)
            elif holds is None:
                unmeasured.append(v)
        if unmeasured:
            return Effective(
                self.value,
                self.prov,
                self.status,
                self.reviewer,
                self.reviewed,
                ambiguous=tuple(sorted(v.band.token for v in unmeasured)),
            )
        if not matches:
            return Effective(self.value, self.prov, self.status, self.reviewer, self.reviewed)
        deepest = max(_depth(v) for v in matches)
        best = [v for v in matches if _depth(v) == deepest]
        if len(best) > 1:
            return Effective(
                self.value,
                self.prov,
                self.status,
                self.reviewer,
                self.reviewed,
                ambiguous=tuple(sorted("+".join(v.key) for v in best)),
            )
        winner = best[0]
        return Effective(
            winner.value,
            winner.prov,
            winner.status,
            winner.reviewer,
            winner.reviewed,
            when=winner.key,
        )


def _depth(v: Variant) -> int:
    """How specific a variant is — every thing that had to be true to pick it."""
    return len(v.when) + (1 if v.band is not None else 0)


def check_kind(name: str, v: Any) -> None:
    """Whatever this field is declared to hold, is this that?

    Shared by a value and by every variant of it. A variant is a different
    number under a different condition, not a different kind of thing, so
    "10 ft. when affordable" is checked exactly as the base 5 ft. was.
    """
    fd = field(name)
    kind = fd.kind
    if v is None:
        raise ValueError(f"{name}: value may not be null — omit the field instead")
    if kind == "bool":
        if not isinstance(v, bool):
            raise ValueError(f"{name}: expected a boolean, got {type(v).__name__}")
    elif kind == "count":
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"{name}: expected a non-negative integer, got {v!r}")
    elif kind in ("length_ft", "area_sqft", "ratio", "percent"):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise ValueError(f"{name}: expected a non-negative number, got {v!r}")
        if kind == "percent" and v > 100:
            raise ValueError(f"{name}: percent value {v} exceeds 100")
    elif kind == "curve":
        _validate_curve(name, v)
    elif kind == "enum":
        if v not in fd.choices:
            raise ValueError(f"{name}: {v!r} not one of {list(fd.choices)}")


def _validate_curve(name: str, v: Any) -> None:
    """A coverage curve is an ascending table of [lot_floor, base_sqft, pct_over]."""
    if not isinstance(v, list) or not v:
        raise ValueError(f"{name}: expected a non-empty list of tiers")
    last_floor = -1.0
    for i, tier in enumerate(v):
        if not isinstance(tier, (list, tuple)) or len(tier) != 3:
            raise ValueError(f"{name}: tier {i} must be [lot_sqft_floor, base_sqft, pct_over_floor]")
        floor, base, pct = tier
        for label, n in (("floor", floor), ("base", base), ("pct", pct)):
            if isinstance(n, bool) or not isinstance(n, (int, float)) or n < 0:
                raise ValueError(f"{name}: tier {i} {label} must be a non-negative number, got {n!r}")
        if floor <= last_floor:
            raise ValueError(f"{name}: tier {i} floor {floor} must exceed the previous tier's {last_floor}")
        last_floor = float(floor)


#: The pseudo-field an incorporation clause is signed under. It shares the
#: verification key space with real standards, because it is the same kind of
#: claim: somebody read a sentence and says this is what it means.
LIKE = "like"


class Incorporation(BaseModel):
    """This zone's standards are another zone's, by reference.

    Fairview's VSF zone states no dimensional standards at all. It says the R-6
    standards apply — in a different chapter — and carries a conflict clause
    naming which text governs where the two disagree. That is a common shape and
    it cannot be encoded by copying R-6's numbers across: the copies would stop
    tracking their source the first time R-6 is amended, silently, and no
    reviewer looking at VSF would have any way to notice.

    So the reference is the encoding. VSF holds a pointer and whatever it states
    for itself; resolution reads R-6 through it and every resolved value still
    cites the R-6 section it was actually read from.
    """

    model_config = ConfigDict(frozen=True)

    #: The zone code adopted. Looked up in this layer, then up the hierarchy —
    #: a city adopting a county zone is the same shape as adopting its own.
    zone: str = Field(min_length=1)
    #: Which text governs where both state the same standard. Codes write it
    #: both ways, so it is read from the conflict clause rather than assumed.
    wins: str = Field(default="local", pattern="^(local|referenced)$")
    prov: Provenance
    status: Status = Status.draft
    reviewer: str | None = None
    reviewed: date | None = None

    @property
    def trusted(self) -> bool:
        return self.status.trusted

    @model_validator(mode="after")
    def _verified_needs_a_reviewer(self) -> Incorporation:
        if self.status is Status.verified and not (self.reviewer and self.reviewed):
            raise ValueError("a verified incorporation requires both 'reviewer' and 'reviewed'")
        return self


class Zone(BaseModel):
    """One base zone within one jurisdiction layer."""

    model_config = ConfigDict(frozen=True)

    zone: str
    values: dict[str, Value] = Field(default_factory=dict)
    notes: str | None = None
    #: Clause-ledger ids asserted to cover this zone's code section. Populated
    #: by the RASE extraction pass; completeness is checked in `ledger.py`.
    clauses: tuple[str, ...] = ()
    #: Another zone whose standards this one adopts. See :class:`Incorporation`.
    like: Incorporation | None = None
    #: Code section numbers whose text states this zone's standards — "4.122",
    #: "19.115". Declared rather than inferred: most codes state standards in
    #: prose under a per-zone heading, and a paragraph is bound to a zone only
    #: by the section enclosing it. Guessing which heading means which zone
    #: would attribute one zone's setback to another, so an encoder says it
    #: once and a reviewer can check the claim in one glance.
    section: tuple[str, ...] = ()

    @property
    def trusted(self) -> bool:
        """A zone is trusted only when every value it carries is verified.

        One draft or stale value poisons the zone: the screen cannot tell which
        answer the untrusted number changed, so the whole zone routes to REVIEW.

        A zone that borrows is judged on what it holds locally; whether the
        borrowed half is trusted is a question about the zone it borrowed from,
        and the resolver answers it there. What is required here is that the
        *claim* to borrow has been read — an unverified reference could be
        pointing at the wrong zone entirely.
        """
        if self.like is not None:
            return self.like.trusted and all(v.trusted for v in self.values.values())
        return bool(self.values) and all(v.trusted for v in self.values.values())

    def untrusted_fields(self) -> tuple[str, ...]:
        out = sorted(n for n, v in self.values.items() if not v.trusted)
        if self.like is not None and not self.like.trusted:
            out.append(LIKE)
        return tuple(out)


class CodeDocument(BaseModel):
    """One document that holds part of a jurisdiction's code.

    Which URL serves the actual ordinance text — as opposed to a landing page,
    a table of contents, or a JavaScript shell — is per-jurisdiction knowledge
    that somebody worked out once, usually by trying four of them. Leaving it
    in the shell history of whoever was encoding that week is how a coverage
    gap becomes permanent, and it is why nothing could re-fetch the corpus to
    watch it for amendments.

    So it is declared beside the rules it backs, and re-fetching a jurisdiction
    is one command that needs no arguments.
    """

    model_config = ConfigDict(frozen=True)

    #: Chapter or section number, e.g. "33.110". Becomes the stored filename,
    #: so it is what every quote in this jurisdiction points into.
    id: str = Field(min_length=1)
    url: str = Field(min_length=5)
    title: str = ""
    #: Literal marker where the stored slice begins. Codifier boilerplate churns
    #: constantly and the ordinance rarely does, so storing the chapter rather
    #: than the page is what keeps drift detection meaningful.
    start: str = ""
    end: str = ""
    #: Which occurrence of ``start`` opens the slice. A chapter PDF lists every
    #: section in its contents before printing any of them, so this is often 2.
    nth: int = Field(default=1, ge=1)
    #: How a PDF's text is pulled out. ``layout`` keeps horizontal geometry,
    #: which is what lets a table cell stay under its zone's column — the
    #: default because losing that silently mis-attributes numbers. ``plain``
    #: is for the PDFs where layout mode fuses words together
    #: ("areasintheCity..."), which blinds every subject phrase; declared by
    #: whoever measured the document, like everything else in this block.
    extraction: str = Field(default="layout", pattern="^(layout|plain)$")
    #: True where this document's text layer is letter-spaced — kerning pairs
    #: come out as spaces, so "10,000 square feet" arrives as "1 0 , 000 squ
    #: are f eet" and no reader can key on it. Declared, never guessed: the
    #: repair joins digits across a single space, and in a table whose cells
    #: are single digits that is two cells, not one number. Somebody looks at
    #: the stored text and says so.
    spaced: bool = False
    #: Set only for a genuinely short section, and only by somebody who has read
    #: it. Never to silence a URL that is serving the wrong thing.
    allow_thin: bool = False

    @model_validator(mode="after")
    def _id_is_a_filename(self) -> CodeDocument:
        if "/" in self.id or "\\" in self.id:
            raise ValueError(f"document id {self.id!r} may not contain a path separator")
        return self


class Layer(BaseModel):
    """One node of the state → county → city hierarchy.

    ``defaults`` are values that apply to every zone in the layer unless a more
    specific layer or the zone itself overrides them. State preemption
    (OAR 660-046 parking caps, for instance) lives here.
    """

    model_config = ConfigDict(frozen=True)

    layer: str = Field(description="Hierarchy path, e.g. 'or/41051-multnomah/4159000-portland'.")
    kind: str = Field(description="state | county | city | unincorporated")
    label: str
    eligible: bool = True
    defaults: dict[str, Value] = Field(default_factory=dict)
    zones: dict[str, Zone] = Field(default_factory=dict)
    notes: str | None = None
    #: Ingest hints — which GIS zoning layer and attribute carry this layer's
    #: zone codes. Not a zoning standard; kept beside them for locality.
    ingest: dict[str, Any] = Field(default_factory=dict)
    #: The documents this jurisdiction's rules are read from.
    code: tuple[CodeDocument, ...] = ()

    @property
    def depth(self) -> int:
        return self.layer.count("/")

    @property
    def doc_root(self) -> str:
        """Where this layer's documents live in the provenance store.

        Directory names carry a Census GEOID prefix so two Springfields can sit
        side by side; the store drops it, because a quote is a thing a person
        reads in a review queue and ``or/multnomah/portland/33.110.txt#L454``
        is legible in a way the GEOID form is not.
        """
        return "/".join(part.split("-", 1)[-1] if _GEOID.match(part) else part
                        for part in self.layer.split("/"))

    def document_path(self, doc_id: str) -> str:
        """Store path for one of this layer's documents."""
        return f"{self.doc_root}/{doc_id}.txt"

    def documents(self) -> dict[str, CodeDocument]:
        """Declared documents keyed by the store path each lands at."""
        return {self.document_path(d.id): d for d in self.code}

    def ancestors(self) -> list[str]:
        """Hierarchy paths from this layer up to the state root, most specific first."""
        parts = self.layer.split("/")
        return ["/".join(parts[: i + 1]) for i in range(len(parts) - 1, -1, -1)]
