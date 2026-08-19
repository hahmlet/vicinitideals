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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from flats.rules.conditions import condition
from flats.rules.fields import (
    MEASURED_ON_FIELDS,
    PER_DWELLING_FIELDS,
    PER_UNIT_AREA_FIELDS,
    FieldDef,
    field,
)


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
        # What a term means in this jurisdiction -- corner lot, front lot line.
        # A measurement is a rule and belongs beside the numbers it governs.
        "definitions",
        "definitions_from",
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
    #: An exclusive upper bound, the mirror of ``more_than``. Lake Oswego
    #: permits four townhouses per the lot area one single-family dwelling
    #: would need, so the pod is allowed at exactly 7,500 sq ft in R-7.5 and
    #: not below -- and a band written ``at_most: 7499`` leaves a hole the
    #: width of one square foot, through which a lot reaches the base value
    #: unannounced.
    less_than: float | None = None

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
        if self.at_most is not None and self.less_than is not None:
            raise ValueError(
                f"{self.measure}: a band has one upper bound — "
                f"'at_most' includes it, 'less_than' does not"
            )
        if (
            self.at_least is None
            and self.at_most is None
            and self.more_than is None
            and self.less_than is None
        ):
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
        low, _ = self.lower
        if self.less_than is not None and low >= self.less_than:
            raise ValueError(
                f"{self.measure}: band {_num(low)} to under {_num(self.less_than)} is empty"
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
        if self.less_than is not None:
            return self.less_than
        return self.at_most if self.at_most is not None else float("inf")

    @property
    def upper_closed(self) -> bool:
        """Whether a lot sitting exactly on the upper bound is in the band."""
        return self.less_than is None

    @property
    def token(self) -> str:
        """How a reviewer names this band on the command line.

        A signature is over one sentence, and for a banded table the sentence
        is one column. ``--when lot_sqft:3000-4999`` addresses it the way
        ``--when affordable`` addresses a footnote.
        """
        if self.less_than is not None:
            high = f"<{_num(self.less_than)}"
        else:
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
        if self.less_than is not None and got >= self.less_than:
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

    value: Any = None
    #: True where the conditions do not change this standard's number but
    #: switch it off. Codes state this constantly and it is not a number:
    #: Fairview caps lot depth at three times the width and then writes
    #: "Townhomes and cottage clusters none" in the same cell; Lake Oswego
    #: exempts cottage clusters from lot coverage outright. Encoding the
    #: exemption as some very large number would be a lie that screens
    #: correctly, right up until somebody reads it.
    exempt: bool = False
    #: A percentage the code allows the base to be cut by, where the code
    #: states the percentage and never the result. Portland's Table 110-7
    #: zones may have their minimum lot area "reduced by up to 10 percent",
    #: and 33.110 prints 12,000 and prints 10 and prints 10,800 nowhere. A
    #: file that typed 10,800 would be citing a sentence for a number the
    #: sentence does not contain, which is the misquote this whole ladder
    #: exists to catch -- so the file states the percentage the code states,
    #: and the arithmetic is done here where it can be checked.
    reduce_pct: float | None = None
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

    @model_validator(mode="after")
    def _a_reduction_is_a_percentage(self) -> Variant:
        if self.reduce_pct is None:
            return self
        if self.exempt:
            raise ValueError("a variant is exempt or reduced, not both")
        if not 0 < self.reduce_pct <= 100:
            raise ValueError(
                f"reduce_pct {self.reduce_pct} is not a percentage of the base value"
            )
        return self

    @model_validator(mode="after")
    def _exempt_carries_no_number(self) -> Variant:
        # The two are alternatives, not a value with a flag on it. A variant
        # that said both "exempt" and "3" would leave every reader of the file
        # to guess which half the engine honours.
        if self.exempt and self.value is not None:
            raise ValueError("an exempt variant states no value — the standard does not apply")
        if not self.exempt and self.value is None:
            raise ValueError("a variant states a value, or states that it is exempt")
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
    #: Where this number was derived rather than read: the percentage the
    #: code allows the base to be cut by. Carried so attribution can say "the
    #: base, reduced by ten percent under 33.110.240.B.2" rather than
    #: presenting a number that appears nowhere in the cited text.
    reduce_pct: float | None = None
    #: True where the standard does not apply to this configuration at all.
    #: ``value`` is None and there is nothing to compare a lot against — not a
    #: pass by a wide margin, an absence of the test. A screen that read the
    #: None as a zero would fail every lot on a standard the code exempts it
    #: from, which is the worst of the two ways to be wrong.
    exempt: bool = False

    @property
    def trusted(self) -> bool:
        """Verified, and unambiguous. Ambiguity is not a trust question a
        signature can settle — both variants may be correctly transcribed and
        the encoding still not say which one governs."""
        return self.status.trusted and not self.ambiguous

    @property
    def conditional(self) -> bool:
        return bool(self.when)


class Preempt(str, enum.Enum):
    """How a less specific layer's value survives a more specific one.

    Preemption is not one thing. Two statutes in this rule set preempt in
    genuinely different shapes, and collapsing them cost real buildable area:

    ``always``  the ancestor answers the question and the local layer does not
                get a say either way. ORS 92.031(2)(b) settles WHICH standards
                a middle housing land division is measured against; a city may
                not decide that differently in any direction.

    ``cap``     the ancestor states the strictest a local layer may be. OAR
                660-046-0220 caps required parking at one stall per unit: a
                city asking two is clipped to one, and a city asking none --
                Portland, since it repealed its minimums -- keeps none. A lock
                here would invent a requirement the city does not impose.

    Which way "looser" runs is not stored on the preemption; it is read off the
    field, because it is a property of the standard. A minimum gets looser as
    it falls and a maximum as it rises, and `FieldDef.is_maximum` already
    knows which is which.
    """

    none = "none"
    always = "always"
    cap = "cap"

    @property
    def binds(self) -> bool:
        return self is not Preempt.none

    @classmethod
    def read(cls, raw: object) -> "Preempt":
        """Parse what a rule file wrote.

        ``true`` predates the distinction and every existing use of it means
        ``always``, so it keeps that reading. Anything else unrecognised is
        refused rather than guessed at -- a typo that quietly resolved to
        "no preemption" would drop a statute without a word.
        """
        if isinstance(raw, cls):
            return raw
        if raw is None or raw is False:
            return cls.none
        if raw is True:
            return cls.always
        try:
            return cls(str(raw))
        except ValueError:
            raise ValueError(
                f"preempts: expected true, false, or one of "
                f"{', '.join(x.value for x in cls)} \u2014 got {raw!r}"
            ) from None


class Value(BaseModel):
    """One encoded standard plus its proof and review state."""

    model_config = ConfigDict(frozen=True)

    name: str
    #: None only where `exempt` is set -- the code states no such standard
    #: here. A non-exempt value with no number is refused by `check_kind`.
    value: Any = None
    prov: Provenance
    status: Status = Status.draft
    reviewer: str | None = None
    reviewed: date | None = None
    #: Exceptions to this standard, each under its own conditions. The base
    #: value applies when none of them do.
    variants: tuple[Variant, ...] = ()
    #: How this value survives a more specific layer. ``"always"`` wins
    #: outright; ``"cap"`` is the strictest a local layer may be, so a looser
    #: local number passes through and a stricter one is clipped to this; the
    #: default binds nothing. The one place the flat rule set needs
    #: defeasibility, and it needs a direction with it -- see `Preempt`.
    preempts: Preempt = Preempt.none
    #: The per-dwelling figure the code prints, where it prints one instead of
    #: the total. MCC 39.4862(C) states the LR-7 minimum lot size as "5,000
    #: square feet for each dwelling unit"; 20,000 appears nowhere in the
    #: article. `value` carries the product because that is what the field
    #: means, and this carries what the sentence says, so the citation check
    #: compares the number a reader will find. Same shape as `reduce_pct` on a
    #: variant, and for the same reason.
    per_dwelling: float | None = None
    #: The site area per dwelling unit the code prints, where it states a
    #: density that way. Portland's Table 120-4 asks "1 unit per 2,500 sq. ft.
    #: of site area" in RM1; `value` carries the density that comes to and this
    #: carries the figure a reader will find. Same bargain as `per_dwelling`.
    sqft_per_unit: float | None = None
    #: The quantity a rate is measured against, where the code names one this
    #: screen does not hold. A density per *net acre* is computed on the lot
    #: less rights-of-way, floodplain, steep slopes and Goal 5 resources, and
    #: nothing here surveys those. Deliberately not a lever: a lever says the
    #: number could move, and this says the comparison rests on a quantity
    #: nobody measured. The lot's own area is a bound on it, which settles the
    #: check in one direction and leaves it open in the other -- see
    #: :func:`flats.score.screen._checks`.
    measured_on: str | None = None
    #: True where the zone was read and states no such standard at all --
    #: Portland's RX prints a front lot line and no lot area, and its parking
    #: chapter prints maximums and no minimum. Distinct from a zone that is
    #: silent because nobody has read it yet, which is a missing field, and
    #: from a standard of zero, which is a test every lot passes for a reason
    #: the code did not give. ``value`` is None and there is nothing to
    #: compare a lot against.
    exempt: bool = False

    @field_validator("preempts", mode="before")
    @classmethod
    def _read_preempts(cls, raw: object) -> Preempt:
        # `True` is what every rule file and every caller wrote before
        # preemption had a direction, and it still means "wins outright".
        # Accepted here rather than only in the loader so the model is the one
        # place that decides, whoever is constructing the value.
        return Preempt.read(raw)

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
        if not self.exempt:
            check_kind(self.name, self.value)
        for variant in self.variants:
            if not variant.exempt:
                check_kind(self.name, variant.value)
        return self

    @model_validator(mode="after")
    def _per_dwelling_is_a_positive_area(self) -> Value:
        if self.per_dwelling is None:
            return self
        if self.name not in PER_DWELLING_FIELDS:
            raise ValueError(
                f"{self.name}: 'per_dwelling' applies to "
                f"{', '.join(sorted(PER_DWELLING_FIELDS))} — an area scales with "
                f"the number of dwellings and a width does not"
            )
        if self.per_dwelling <= 0:
            raise ValueError(f"{self.name}: per_dwelling {self.per_dwelling} is not an area")
        return self

    @model_validator(mode="after")
    def _sqft_per_unit_is_a_positive_area(self) -> Value:
        if self.sqft_per_unit is None:
            return self
        if self.name not in PER_UNIT_AREA_FIELDS:
            raise ValueError(
                f"{self.name}: 'sqft_per_unit' states a density as an area per "
                f"dwelling, and applies to {', '.join(sorted(PER_UNIT_AREA_FIELDS))}"
            )
        if self.sqft_per_unit <= 0:
            raise ValueError(f"{self.name}: sqft_per_unit {self.sqft_per_unit} is not an area")
        return self

    @model_validator(mode="after")
    def _measured_on_names_a_registered_fact(self) -> Value:
        if self.measured_on is None:
            return self
        if self.name not in MEASURED_ON_FIELDS:
            raise ValueError(
                f"{self.name}: 'measured_on' names the quantity a rate is "
                f"computed on, and applies to {', '.join(sorted(MEASURED_ON_FIELDS))}"
            )
        try:
            fact = condition(self.measured_on)
        except KeyError as exc:
            raise ValueError(exc.args[0]) from None
        if fact.assume is not None:
            # A denominator with an assumption behind it would let a lot come
            # back GREEN on arithmetic nobody did. The point of naming it is
            # that it is unknown.
            raise ValueError(
                f"{self.name}: {self.measured_on!r} is assumed {fact.assume}, so "
                f"naming it here would certify a rate nothing measured"
            )
        return self

    @model_validator(mode="after")
    def _exempt_carries_no_number(self) -> Value:
        # A value that said both "the code states no such standard" and "5"
        # would leave every reader of the file guessing which half to believe.
        if self.exempt and self.value is not None:
            raise ValueError(
                f"{self.name}: an exempt value states no number — the standard does not apply"
            )
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
                high_closed = (a.band.upper_closed or a.band.upper > high) and (
                    b.band.upper_closed or b.band.upper > high
                )
                # Touching at a single point is an overlap only when the lower
                # bound includes that point: "over 10,000" and "up to 10,000"
                # meet at 10,000 and share no lot.
                if low < high or (low == high and closed and high_closed):
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
            return Effective(
                self.value,
                self.prov,
                self.status,
                self.reviewer,
                self.reviewed,
                exempt=self.exempt,
            )
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
                exempt=self.exempt,
            )
        if not matches:
            return Effective(
                self.value,
                self.prov,
                self.status,
                self.reviewer,
                self.reviewed,
                exempt=self.exempt,
            )
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
                exempt=self.exempt,
            )
        winner = best[0]
        return Effective(
            winner.value,
            winner.prov,
            winner.status,
            winner.reviewer,
            winner.reviewed,
            when=winner.key,
            exempt=winner.exempt,
            reduce_pct=winner.reduce_pct,
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


class Wanted(BaseModel):
    """A standard somebody believed, that no stored passage says.

    It is not a rule. A number with a citation but no quote has never been read
    against the code — the citation names a chapter, and nothing in the store
    proves the chapter says it. FLATS will not screen on it and will not print
    it: a value that cannot be shown to a planner is a value that cannot be
    defended, and one that quietly decides a lot is buildable is worse than a
    gap, because a gap is visible.

    So it is loaded here instead of into the zone, and becomes work: find the
    passage, quote it, and the number turns back into a rule. What it was
    believed to be is kept, because a searcher who knows the answer is probably
    "10 feet" finds it faster than one starting from nothing.
    """

    model_config = ConfigDict(frozen=True)

    zone: str
    field: str
    #: The rule it would have been, kept whole: the number somebody believed,
    #: the chapter they cited, the exceptions they wrote. A searcher who knows
    #: the answer is probably "10 feet" in PCC 33.110.220 finds the passage far
    #: faster than one starting from nothing, and every encoding tool that
    #: hunts quotes already knows how to read a Value.
    value: Value

    @property
    def cite(self) -> str:
        return self.value.prov.cite

    @property
    def url(self) -> str:
        return self.value.prov.url


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
    #: True where this document's tables print footnote markers hard against
    #: the numbers they mark -- Milwaukie's "Street side yard 154" is fifteen
    #: feet with note 4, not a hundred and fifty-four. Declared, never
    #: guessed: in a table that really does state 154, guessing would let the
    #: corroboration check bless an encoding of 15.
    glued_markers: bool = False
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
    #: Standards this layer claimed but cannot show — see :class:`Wanted`. Held
    #: on the layer rather than dropped silently, so "we do not know" is a thing
    #: the system can say out loud rather than an absence somebody has to notice.
    wanted: tuple[Wanted, ...] = ()
    #: Ingest hints — which GIS zoning layer and attribute carry this layer's
    #: zone codes. Not a zoning standard; kept beside them for locality.
    ingest: dict[str, Any] = Field(default_factory=dict)
    #: The documents this jurisdiction's rules are read from.
    code: tuple[CodeDocument, ...] = ()
    #: How this jurisdiction decides a term the rules hang variants on. Held
    #: per layer because four codes define "corner lot" four incompatible ways
    #: and a borrowed default is a wrong answer rather than a safe one. See
    #: :mod:`flats.rules.definitions`. Empty means unread, not "the usual one".
    definitions: dict[str, Any] = Field(default_factory=dict)

    #: Layer ids whose definitions this one adopts, most authoritative first.
    #: Written only where the code says it adopts them, with the adopting
    #: clause quoted in the layer's notes. It exists because the honest answer
    #: to "who does Milwaukie borrow from" is nobody, and the way to hold that
    #: answer is a field that stays empty rather than a chain walk that fills
    #: it in. An incorporated city's development code is self-contained; the
    #: county's governs unincorporated land. Silence is not adoption.
    definitions_from: list[str] = Field(default_factory=list)

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

    def unread(self) -> dict[tuple[str, str], Value]:
        """The queue, keyed the way every encoding tool addresses a value.

        ``(zone, field) -> the Value it would have been``. Corroboration, quote
        attachment and the gaps ladder all work on these and only these: a zone
        holds what has been read, and this holds what has not.
        """
        return {(w.zone, w.field): w.value for w in self.wanted}

    def documents(self) -> dict[str, CodeDocument]:
        """Declared documents keyed by the store path each lands at."""
        return {self.document_path(d.id): d for d in self.code}

    def ancestors(self) -> list[str]:
        """Hierarchy paths from this layer up to the state root, most specific first."""
        parts = self.layer.split("/")
        return ["/".join(parts[: i + 1]) for i in range(len(parts) - 1, -1, -1)]
