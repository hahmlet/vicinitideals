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
from typing import Any, Collection

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
    #: Registered condition names, all of which must hold. An empty tuple is
    #: rejected: that is the base value, and two bases cannot be told apart.
    when: tuple[str, ...]
    prov: Provenance
    status: Status = Status.draft
    reviewer: str | None = None
    reviewed: date | None = None

    @property
    def trusted(self) -> bool:
        return self.status.trusted

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
        seen: set[frozenset[str]] = set()
        for variant in self.variants:
            if not variant.when:
                # A variant with no conditions is the base value written twice,
                # and nothing downstream could say which one applies.
                raise ValueError(
                    f"{self.name}: a variant must state the condition(s) it applies under"
                )
            key = frozenset(variant.when)
            if key in seen:
                raise ValueError(
                    f"{self.name}: two variants apply under the same conditions "
                    f"{sorted(key)} — one of them is wrong"
                )
            seen.add(key)
        return self

    # -- reading a value under a configuration -------------------------

    @property
    def levers(self) -> frozenset[str]:
        """Conditions that change this standard.

        What makes the batch view possible: a lever is worth offering only when
        flipping it moves a number some lot in the selection is bound by.
        """
        return frozenset(c for variant in self.variants for c in variant.when)

    def under(self, active: Collection[str] = ()) -> Effective:
        """The value that applies when these conditions hold.

        A variant applies when every condition it names is active. The most
        specific match wins — "affordable and corner" beats "affordable" —
        because a code that states both meant the pair to be different from
        either alone.

        Two equally-specific matches are not resolved. Picking one would mean
        guessing which of two encoded rules the drafters meant, and that guess
        would be invisible in the output. The ambiguity is reported instead and
        the screen routes the lot to UNKNOWN, which is what not knowing is.
        """
        if not self.variants:
            return Effective(self.value, self.prov, self.status, self.reviewer, self.reviewed)
        held = set(active)
        matches = [v for v in self.variants if set(v.when) <= held]
        if not matches:
            return Effective(self.value, self.prov, self.status, self.reviewer, self.reviewed)
        deepest = max(len(v.when) for v in matches)
        best = [v for v in matches if len(v.when) == deepest]
        if len(best) > 1:
            return Effective(
                self.value,
                self.prov,
                self.status,
                self.reviewer,
                self.reviewed,
                ambiguous=tuple(sorted("+".join(sorted(v.when)) for v in best)),
            )
        winner = best[0]
        return Effective(
            winner.value,
            winner.prov,
            winner.status,
            winner.reviewer,
            winner.reviewed,
            when=tuple(sorted(winner.when)),
        )


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
