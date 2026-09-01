"""Where the site plan's zone numbers and the FLATS corpus disagree.

Two files carry a zone's dimensions. `config/rules.yaml` is what the pipeline
screens with, and it was written first, by hand, from whatever the reader had
in front of them at the time. `flats/config/jurisdictions/**` is what the
corpus reads now: every figure quoted to a line of a stored document, with its
footnotes ruled and its refusals counted.

They had never been checked against each other. This does that, and the first
run found twenty-eight places they differ. Working through them retired nearly
all of the list, and the pattern was the same mistake over and over: rules.yaml
had been reading the DETACHED HOUSE'S row of a table that prints one row per
housing type. Oregon City's coverage cap for a quadplex is 70 percent, not the
50 the house gets. Happy Valley's is 60, not 50. Milwaukie's minimum lot is
3,000, not 5,000. Each of those was a lot thrown away for nothing, and the one
that ran the other way -- Milwaukie R-HD screened on a 5-foot front setback
that the code applies only to a mapped handful of properties -- was a false
green in the densest zone of its city.

What is left is not drift, and the run sorts it into four kinds:

MISSING STEP-BACK. Gresham prints a 15-foot rear setback in five districts and
then says at 7.0420(G)(1) that the roof may be no more than 21 feet at that
line, rising a foot for every foot further back -- so a 26-foot pod stands at
20, not 15. Milwaukie does the same to its side yards. The corpus carries both
figures, the effective one and the printed one it came from; rules.yaml carries
only the printed one, because the pipeline has no step-back model at all.

COLLAPSED COMBINED YARD. Lake Oswego asks 5 feet on one side and 15 feet across
both. rules.yaml has one symmetric side field and no total, so the only faithful
number it can hold is 7.5 -- and "correcting" it to the corpus base of 5 would
screen a 10-foot combined yard where the code demands 15. The corpus is richer,
rules.yaml is right, and the audit says so rather than counting it as drift.

PERMISSION UNRESOLVED. Wilsonville's RN prints "quadplexes are not permitted"
against a state-preemption argument that is real and untested. Until somebody
answers that, its five dimensional differences are a question about a zone that
may not be screened at all, so they are held behind the permission split rather
than reconciled one number at a time.

A NAME THE TWO FILES SPELL DIFFERENTLY. Thirty-three numbers looked uncited --
stated by rules.yaml with nothing in the corpus behind them -- and not one of
them was. Eighteen belonged to three zones that adopt another zone's standards
by reference: Fairview's R/SFLD says the R-10 chapter applies, its RM/TOZ says
RM, Happy Valley's R20CC says R20. `like:` is how the corpus writes that, on
purpose, so a reference keeps tracking its source instead of going stale as a
copy. Reading a zone's own block and stopping there makes every one of them
look unread, and this audit did exactly that until it was taught to walk the
chain. The other fifteen were nothing of the kind either. rules.yaml calls the standard `min_frontage_ft`; the corpus reads it off a
row headed "Minimum lot width" and files it as `min_lot_width_ft`. Every number
agrees. What does not necessarily agree is the LINE ON THE GROUND. s7 measures
the run of boundary that touches a street; Oregon City 17.04.700 measures
"between the midpoints of the two principal opposite side lot lines" and
Tualatin TDC 31.060 "at the center of the lot". On a rectangle those are the
same. On a cul-de-sac wedge, a flag lot or anything that tapers they are not,
and 988 lots -- 896 in Oregon City, 92 in Tualatin -- are currently excluded at
`below_min_frontage` by a number the code never applied to their street edge.
West Linn is the control: its tables head the row "Minimum lot width AT FRONT
LOT LINE", which is the same edge, and its 739 exclusions stand.

That one is not fixed here, because fixing it needs a measurement the pipeline
does not take. Deleting the gate instead would trade 988 possible false reds for
an unknown number of false greens, which is the wrong direction for a screen
whose whole job is to be trusted when it says yes.

Variant-aware on purpose. A corpus value is a base plus banded and conditioned
variants -- Wilsonville PDR-1's front setback is 15 on a small lot and 20 on a
large one, and rules.yaml can only carry one number -- so a rules.yaml figure
that matches ANY of a value's limbs counts as agreement. What is left is
disagreement about the number itself, which is the only kind worth a reader.

    uv run python "Lot Analysis/quadfit/audit_zone_mirror.py"

The frozen lists in tests/test_zone_mirror.py are the ratchet: a new divergence
fails the suite, and so does fixing one without saying so.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
RULES = REPO / "Lot Analysis" / "quadfit" / "config" / "rules.yaml"

#: rules.yaml zone key -> FLATS field registry name. Only the dimensions both
#: sides state. Height and depth are deliberately absent: rules.yaml keeps them
#: in prose in its `notes`, so there is nothing to compare.
MIRRORED: dict[str, str] = {
    "setback_front_ft": "setback_front_ft",
    "setback_side_ft": "setback_side_ft",
    "setback_rear_ft": "setback_rear_ft",
    "setback_street_side_ft": "setback_street_side_ft",
    "min_lot_sqft": "min_lot_sqft",
    "max_coverage_pct": "max_coverage_pct",
    "min_frontage_ft": "min_frontage_ft",
}

#: rules.yaml names a standard the corpus files under a different name. A match
#: here is NOT agreement. It says the number came from a real quoted standard
#: read under another heading, which leaves the only question that matters:
#: whether the two names measure the SAME EDGE of the lot.
#:
#: s7 compares a lot's measured `frontage_ft` -- the run of boundary that
#: touches a street -- against `min_frontage_ft`. A code's "lot width" is
#: usually not that. Oregon City 17.04.700 measures it "between the midpoints of
#: the two principal opposite side lot lines"; Tualatin TDC 31.060 measures it
#: "at the center of the lot". Both are the middle of the lot, not the street
#: edge, and a wedge lot on a cul-de-sac passes one and fails the other.
ALIASES: dict[str, str] = {"min_frontage_ft": "min_lot_width_ft"}

#: The jurisdictions where the alias is safe, and why. Per-city on purpose:
#: this is a question about one table's wording, and the answer does not
#: travel. Anything not listed here is screening the wrong edge.
ALIAS_SAME_EDGE: dict[str, str] = {
    "west_linn": (
        "CDC 08.070 through 16.070 head the row 'Minimum lot width AT FRONT "
        "LOT LINE' and print a second 'Average minimum lot width' beneath it. "
        "The first is the street edge, which is what s7 measures, and it is "
        "the one rules.yaml carries."
    ),
}


@dataclass(frozen=True)
class Divergence:
    """One dimension rules.yaml states that no limb of the corpus value holds.

    Four kinds, and only the last one is somebody's mistake. Ask the `is_`
    properties in the order `main` uses them: a zone whose permission is in
    dispute swallows every other question about it.
    """

    jurisdiction: str
    zone: str
    field: str
    shipped: float
    corpus: tuple[float, ...]
    printed: float | None = None
    side_total: float | None = None
    permission_split: bool = False

    @property
    def key(self) -> str:
        return f"{self.jurisdiction}/{self.zone}.{self.field}"

    @property
    def zone_key(self) -> str:
        return f"{self.jurisdiction}/{self.zone}"

    @property
    def is_permission_blocked(self) -> bool:
        """The two files disagree about whether the pod may be built here at
        all, which makes every number in the zone an answer to a question
        nobody has asked yet."""
        return self.permission_split

    @property
    def is_step_back(self) -> bool:
        """rules.yaml has the number the code prints; the corpus has the number
        a 26-foot building actually has to stand at."""
        return self.printed is not None and self.printed == self.shipped

    @property
    def is_side_total_collapse(self) -> bool:
        """The code states a per-side minimum AND a combined minimum across both
        sides. rules.yaml has one symmetric field, so half the combined figure
        is the only number that satisfies the rule it can express."""
        return (
            self.field == "setback_side_ft"
            and self.side_total is not None
            and self.shipped * 2 == self.side_total
        )

    @property
    def is_drift(self) -> bool:
        """Nobody's reading is richer than the other's -- one file was edited
        and the other was not."""
        return not (
            self.is_permission_blocked
            or self.is_step_back
            or self.is_side_total_collapse
        )

    def __str__(self) -> str:
        limbs = "/".join(_n(c) for c in self.corpus)
        if self.is_step_back:
            return (f"{self.key}: rules.yaml {_n(self.shipped)} is the printed "
                    f"setback; the step-back makes it {limbs}")
        if self.is_side_total_collapse:
            return (f"{self.key}: rules.yaml {_n(self.shipped)} is half the "
                    f"corpus's {_n(self.side_total)} ft combined side yard, "
                    f"whose per-side minimum is {limbs}")
        return f"{self.key}: rules.yaml {_n(self.shipped)} vs corpus {limbs}"


@dataclass(frozen=True)
class Alias:
    """One dimension the two files hold under different names.

    `same_edge` is the whole finding. When it is true the corpus simply files a
    front-lot-line width as a width, and nothing is wrong. When it is false the
    pipeline is testing a lot's street frontage against a number the code
    measures across the middle of the lot -- two different lines on the same
    parcel, which agree on a rectangle and part company on every wedge, flag
    and cul-de-sac lot in the city.
    """

    jurisdiction: str
    zone: str
    shipped_field: str
    corpus_field: str
    shipped: float
    corpus: tuple[float, ...]
    same_edge: bool
    why: str

    @property
    def key(self) -> str:
        return f"{self.jurisdiction}/{self.zone}.{self.shipped_field}"

    @property
    def agrees(self) -> bool:
        return self.shipped in self.corpus

    def __str__(self) -> str:
        limbs = "/".join(_n(c) for c in self.corpus)
        verdict = "same edge" if self.same_edge else "DIFFERENT EDGE"
        return (f"{self.key}={_n(self.shipped)} <- corpus {self.corpus_field}"
                f"={limbs} [{verdict}]")


def _n(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def _limbs(value) -> list[float]:
    """Every number one corpus value can produce -- base and variants."""
    out: list[float] = []
    if value.value is not None:
        try:
            out.append(float(value.value))
        except (TypeError, ValueError):
            return []
    for v in getattr(value, "variants", ()) or ():
        if v.value is not None:
            try:
                out.append(float(v.value))
            except (TypeError, ValueError):
                continue
    return out


class _Effective:
    """What `_pairs` hands out: a zone block whose `.values` include everything
    it adopts. Kept as a wrapper rather than a rebuilt Zone so the audit never
    has to know what else a Zone carries."""

    __slots__ = ("_zl", "values")

    def __init__(self, zl, values: dict) -> None:
        self._zl = zl
        self.values = values

    def __getattr__(self, name: str):
        return getattr(self._zl, name)


def _effective(layer, zl) -> dict:
    """A zone's standards including the ones it adopts by reference.

    `load_rules` returns what each zone block states for itself. A zone that
    says "the R-10 standards apply" -- Fairview's R/SFLD, its RM/TOZ, Happy
    Valley's R20CC -- states almost nothing of its own, and reading `zl.values`
    straight makes it look unread. It is read; the reference IS the encoding,
    which is the point of `like:` and the reason the corpus does not copy
    numbers between zones.

    Follows `flats.rules.resolver`'s order: blocks are applied in sequence and
    the last one wins, so `wins: local` puts the zone's own block last and
    `wins: referenced` puts the adopted chapter last.
    """
    chain: list = []
    seen: set[str] = set()

    def walk(block) -> None:
        if block is None or block.zone in seen:
            return
        seen.add(block.zone)
        like = getattr(block, "like", None)
        if like is None:
            chain.append(block)
            return
        parent = layer.zones.get(like.zone)
        if parent is None:  # up-hierarchy adoption; nothing more to add here
            chain.append(block)
            return
        if like.wins == "referenced":
            chain.append(block)
            walk(parent)
            return
        walk(parent)
        chain.append(block)

    walk(zl)
    out: dict = {}
    for block in chain:
        out.update(block.values)
    return out


def _load() -> tuple[dict, dict]:
    from flats.rules.loader import load_rules

    rules = yaml.safe_load(io.open(RULES, encoding="utf-8"))
    return rules.get("jurisdictions", rules), load_rules()


def _pairs(top: dict, corpus: dict):
    """Every (jurisdiction, rules.yaml zone dict, corpus zone, corpus layer)
    the two files both hold."""
    from flats.encode.port_quadfit import layer_id_for

    for juris, spec in sorted(top.items()):
        if not isinstance(spec, dict) or "zones" not in spec:
            continue
        layer = corpus.get(layer_id_for(juris))
        if layer is None:
            continue
        for z in spec["zones"] or []:
            zl = layer.zones.get(z.get("zone"))
            if zl is None:
                continue
            yield juris, z, _Effective(zl, _effective(layer, zl)), layer


def permission_splits() -> list[str]:
    """Zones where the two files disagree about whether the pod may be built.

    Kept apart from the dimensions because it is a different kind of error. A
    setback off by five feet moves a lot between green and review; a
    `quadplex_allowed` that disagrees decides whether the zone is screened at
    all, and it is the one row where rules.yaml being looser than the corpus
    means every lot in the zone is a false green.
    """
    top, corpus = _load()
    out: list[str] = []
    for juris, z, zl, _layer in _pairs(top, corpus):
        allowed = zl.values.get("quadplex_allowed")
        if allowed is None or allowed.value is None:
            continue
        shipped = z.get("quadplex_allowed")
        if shipped is None or bool(shipped) == bool(allowed.value):
            continue
        out.append(
            f"{juris}/{z['zone']}: rules.yaml quadplex_allowed="
            f"{bool(shipped)} vs corpus {bool(allowed.value)}"
        )
    return out


def aliases() -> list[Alias]:
    """Dimensions the two files hold under different names.

    Split out from `scan` because they are not drift and not agreement. The
    number is quoted and the reading is sound; what is unresolved is whether
    the pipeline's test measures the thing the code measures. A row with
    `same_edge` false is a lot the screen may be killing for a rule the city
    does not have -- or passing on a rule it does.
    """
    top, corpus = _load()
    out: list[Alias] = []
    for juris, z, zl, layer in _pairs(top, corpus):
        for mine, alt in ALIASES.items():
            shipped = z.get(mine)
            if shipped is None:
                continue
            theirs = MIRRORED.get(mine, mine)
            if zl.values.get(theirs) or layer.defaults.get(theirs):
                continue  # the corpus states it under its own name
            value = zl.values.get(alt) or layer.defaults.get(alt)
            if value is None:
                continue
            limbs = _limbs(value)
            if not limbs:
                continue
            why = ALIAS_SAME_EDGE.get(juris, "")
            out.append(
                Alias(juris, z["zone"], mine, alt, float(shipped),
                      tuple(limbs), bool(why), why)
            )
    return out


def scan() -> tuple[list[Divergence], list[str], int]:
    """Returns (mismatches, dimensions rules.yaml states alone, agreements).

    The mismatch list holds all four kinds; sort it with the `is_` properties.
    """
    top, corpus = _load()
    blocked = {s.split(":")[0] for s in permission_splits()}

    diverge: list[Divergence] = []
    uncited: list[str] = []
    agree = 0

    for juris, z, zl, layer in _pairs(top, corpus):
        total = zl.values.get("setback_side_total_ft") or layer.defaults.get(
            "setback_side_total_ft"
        )
        total_v = None if total is None or total.value is None else float(total.value)
        for mine, theirs in MIRRORED.items():
            shipped = z.get(mine)
            if shipped is None:
                continue
            value = zl.values.get(theirs) or layer.defaults.get(theirs)
            if value is None:
                alt = ALIASES.get(mine)
                if alt and (zl.values.get(alt) or layer.defaults.get(alt)):
                    continue  # counted by aliases(), not missing
                uncited.append(f"{juris}/{z['zone']}.{mine}={_n(shipped)}")
                continue
            limbs = _limbs(value)
            if not limbs:
                continue
            if float(shipped) in limbs:
                agree += 1
            else:
                printed = getattr(value, "before_step_back", None)
                diverge.append(
                    Divergence(
                        juris, z["zone"], mine, float(shipped),
                        tuple(limbs),
                        None if printed is None else float(printed),
                        total_v,
                        f"{juris}/{z['zone']}" in blocked,
                    )
                )
    return diverge, uncited, agree


def main() -> None:
    diverge, uncited, agree = scan()
    print(f"{agree} dimensions agree")

    alias = aliases()
    wrong_edge = [a for a in alias if not a.same_edge]
    print(f"{len(alias)} match under a name the two files spell differently "
          f"({len(alias) - len(wrong_edge)} measure the same edge of the lot, "
          f"{len(wrong_edge)} do not)")
    for a in alias:
        print("   ", a)
    if wrong_edge:
        print("    ^ these compare a lot's STREET FRONTAGE against a width the")
        print("      code measures across the middle of the lot. See ALIASES.")

    print(f"{len(uncited)} stated by rules.yaml with nothing in the corpus behind them")
    for u in uncited:
        print("   ", u)

    buckets = [
        ("DIVERGENT -- one file was edited and the other was not",
         [d for d in diverge if d.is_drift]),
        ("where the pipeline is missing the step-back, not drifting",
         [d for d in diverge if not d.is_permission_blocked and d.is_step_back]),
        ("where rules.yaml collapses a combined side yard it has no field for",
         [d for d in diverge if not d.is_permission_blocked
          and not d.is_step_back and d.is_side_total_collapse]),
        ("held behind a zone whose permission the two files dispute",
         [d for d in diverge if d.is_permission_blocked]),
    ]
    for label, rows in buckets:
        print(f"{len(rows)} {label}")
        for d in rows:
            print("   ", d)

    splits = permission_splits()
    print(f"{len(splits)} zones disagree about whether the pod is permitted")
    for s in splits:
        print("   ", s)


if __name__ == "__main__":
    main()
