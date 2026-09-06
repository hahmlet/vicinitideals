"""Load the jurisdiction hierarchy off disk into validated :class:`Layer` objects.

Layer identity comes from the file's path under ``config/jurisdictions``:

===========================================  ==========================================
path                                          layer id
===========================================  ==========================================
``or/_state.yaml``                            ``or``
``or/41051-multnomah/_county.yaml``           ``or/41051-multnomah``
``or/41051-multnomah/_unincorporated.yaml``   ``or/41051-multnomah/_unincorporated``
``or/41051-multnomah/4159000-portland.yaml``  ``or/41051-multnomah/4159000-portland``
===========================================  ==========================================

Directory names carry a Census GEOID prefix for humans; the authoritative GEOID
is joined from TIGER at ingest and never hand-typed here.

Errors accumulate rather than short-circuiting — porting a jurisdiction should
surface every problem in one pass, not one per run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from flats.rules.fields import DESIGN_HEIGHT_FT, DWELLINGS, SQFT_PER_ACRE, field
from flats.rules.definitions import parse as parse_definitions
from flats.rules.model import (
    CROSSREF_OUTCOMES,
    READING_OUTCOMES,
    WORD_OUTCOMES,
    LAYER_META,
    ZONE_META,
    CodeDocument,
    Incorporation,
    Layer,
    Preempt,
    Provenance,
    Reading,
    Ruling,
    Status,
    Value,
    Band,
    Variant,
    Wanted,
    Zone,
)

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config" / "jurisdictions"

_PROV_KEYS = ("cite", "url", "retrieved", "quote", "clause", "drawn", "read_by", "read_on")
_REVIEW_KEYS = ("status", "reviewer", "reviewed", "preempts")


def _prov_args(src) -> dict:
    """Provenance keyword arguments, absent keys included as None.

    Every key is passed even when the YAML omits it, so a value that inherits
    half its provenance from `cite_default` still gets a complete Provenance.
    `drawn` is the exception: it is a flag, not a string, and pydantic will not
    read a missing one as False on its own.
    """
    args = {k: src.get(k) for k in _PROV_KEYS}
    args["drawn"] = bool(args["drawn"])
    return args


class RuleLoadError(Exception):
    """One or more rule files failed to load. Carries every problem found."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        joined = "\n  - ".join(problems)
        super().__init__(f"{len(problems)} rule problem(s):\n  - {joined}")


def _layer_id(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    # `_state` / `_county` name their parent directory; anything else is its own node.
    if parts[-1] in ("_state", "_county"):
        parts = parts[:-1]
    return "/".join(parts)


def _kind_for(layer_id: str, stem: str) -> str:
    if stem == "_state":
        return "state"
    if stem == "_county":
        return "county"
    if stem == "_unincorporated":
        return "unincorporated"
    return "city"


def _parse_values(
    raw: dict[str, Any],
    cite_default: dict[str, Any] | None,
    where: str,
    problems: list[str],
    wanted: list[Wanted] | None = None,
    zone: str = "",
) -> dict[str, Value]:
    """Turn a mapping of field name → (scalar | full object) into Values.

    A value with no ``quote`` does not become one. It has a citation naming a
    chapter and nothing in the store that says the chapter states it, which
    means nobody has read it against the code — and FLATS screening on a number
    nobody read is the failure the whole provenance chain exists to prevent. It
    goes to ``wanted`` instead, and becomes work rather than an answer.
    """
    out: dict[str, Value] = {}

    def _borrows(node: Any) -> bool:
        return isinstance(node, dict) and node.get("same_as") is not None

    # A value stated as equal to another resolves against the block it sits
    # in, so it is parsed after everything that block might lend it. Sorting on
    # a bool is stable, which leaves the file's own order intact otherwise --
    # and the file's order is what a reviewer reads.
    for key, node in sorted(raw.items(), key=lambda kv: _borrows(kv[1])):
        try:
            field(key)
        except KeyError as exc:
            problems.append(f"{where}: {exc.args[0]}")
            continue

        if isinstance(node, dict) and (
            {"value", "exempt", "per_dwelling", "sqft_per_unit", "per_units",
             "spaces_total", "acres", "acres_per_dwelling", "per_height_ft",
             "floor_ft", "same_as", "step_back", "qualified_by"} & set(node)
        ):
            body = dict(node)
            value = body.pop("value", None)
            exempt = bool(body.pop("exempt", False))
            per_dwelling = body.pop("per_dwelling", None)
            sqft_per_unit = body.pop("sqft_per_unit", None)
            per_units = body.pop("per_units", None)
            spaces_total = body.pop("spaces_total", None)
            acres = body.pop("acres", None)
            acres_each = body.pop("acres_per_dwelling", None)
            per_height = body.pop("per_height_ft", None)
            floor_ft = body.pop("floor_ft", None)
            same_as = body.pop("same_as", None)
            step_back = _parse_step_back(
                body.pop("step_back", None), f"{where}.{key}", problems
            )
            measured_on, measured_on_cite, measured_on_quote = _parse_measured_on(
                body.pop("measured_on", None), f"{where}.{key}", problems
            )
            qualified, qualified_cite, qualified_quote = _parse_qualified_by(
                body.pop("qualified_by", None), f"{where}.{key}", problems
            )
            unless = body.pop("unless", ()) or ()
            raw_variants = body.pop("variants", None) or ()
            unknown = set(body) - set(_PROV_KEYS) - set(_REVIEW_KEYS)
            if unknown:
                problems.append(f"{where}.{key}: unknown key(s) {sorted(unknown)}")
            if exempt and value is not None:
                problems.append(
                    f"{where}.{key}: a value states a number or states that the code "
                    f"imposes no such standard, not both"
                )
                continue
            if per_dwelling is not None:
                if value is not None or exempt:
                    problems.append(
                        f"{where}.{key}: a value states a total or a per-dwelling "
                        f"figure, not both"
                    )
                    continue
                if not isinstance(per_dwelling, (int, float)) or isinstance(
                    per_dwelling, bool
                ):
                    problems.append(f"{where}.{key}: 'per_dwelling' expects a number")
                    continue
                # The product, computed here rather than typed into the file.
                # A code that says "5,000 square feet for each dwelling unit"
                # never prints 20,000, and a file that did would be citing a
                # sentence for a number the sentence does not contain.
                value = _per_dwelling(float(per_dwelling))
            if sqft_per_unit is not None:
                if value is not None or exempt:
                    problems.append(
                        f"{where}.{key}: a value states a density or an area per "
                        f"dwelling, not both"
                    )
                    continue
                if not isinstance(sqft_per_unit, (int, float)) or isinstance(
                    sqft_per_unit, bool
                ):
                    problems.append(f"{where}.{key}: 'sqft_per_unit' expects a number")
                    continue
                if sqft_per_unit <= 0:
                    problems.append(
                        f"{where}.{key}: sqft_per_unit {sqft_per_unit} is not an area"
                    )
                    continue
                # "1 unit per 2,500 sq. ft. of site area" is 17.424 units per
                # acre, and 17.424 is in no ordinance anywhere.
                value = _as_density(float(sqft_per_unit))
            if per_units is not None:
                if value is not None or exempt:
                    problems.append(
                        f"{where}.{key}: a value states a rate or the units it "
                        f"is shared between, not both"
                    )
                    continue
                if not isinstance(per_units, (int, float)) or isinstance(
                    per_units, bool
                ):
                    problems.append(f"{where}.{key}: 'per_units' expects a number")
                    continue
                if per_units <= 0:
                    problems.append(
                        f"{where}.{key}: per_units {per_units} is not a count of units"
                    )
                    continue
                # "1 per 2 units" is half a space per unit, and 0.5 is in no
                # ordinance anywhere.
                value = _per_units(float(per_units))
            if spaces_total is not None:
                # Ahead of the value check, because `per_units` above has
                # already put its quotient in `value` and the conflict a
                # reader needs told about is the two carriers, not the
                # arithmetic one of them just did.
                if per_units is not None:
                    problems.append(
                        f"{where}.{key}: a table states parking per unit or in "
                        f"total, not both"
                    )
                    continue
                if value is not None or exempt:
                    problems.append(
                        f"{where}.{key}: a value states a rate or a count of "
                        f"spaces for the whole building, not both"
                    )
                    continue
                if not isinstance(spaces_total, (int, float)) or isinstance(
                    spaces_total, bool
                ):
                    problems.append(
                        f"{where}.{key}: 'spaces_total' expects a number"
                    )
                    continue
                if spaces_total <= 0:
                    problems.append(
                        f"{where}.{key}: spaces_total {spaces_total} is not a "
                        f"count of spaces — a code that asks for none states "
                        f"'exempt: true'"
                    )
                    continue
                # "two spaces in total" for a Quadplex is half a space per
                # unit, and OAR 660-046-0220 prints 0.5 nowhere.
                value = _in_total(float(spaces_total))
            if acres is not None:
                if value is not None or exempt:
                    problems.append(
                        f"{where}.{key}: a value states an area in square feet "
                        f"or in acres, not both"
                    )
                    continue
                if not isinstance(acres, (int, float)) or isinstance(acres, bool):
                    problems.append(f"{where}.{key}: 'acres' expects a number")
                    continue
                if acres <= 0:
                    problems.append(f"{where}.{key}: acres {acres} is not an area")
                    continue
                # "80 acres in the EFU base zone" is 3,484,800 square feet, and
                # 3,484,800 is in no ordinance anywhere.
                value = _in_acres(float(acres))
            if acres_each is not None:
                if value is not None or exempt:
                    problems.append(
                        f"{where}.{key}: a value states an area outright or per "
                        f"dwelling unit, not both"
                    )
                    continue
                if not isinstance(acres_each, (int, float)) or isinstance(
                    acres_each, bool
                ):
                    problems.append(
                        f"{where}.{key}: 'acres_per_dwelling' expects a number"
                    )
                    continue
                if acres_each <= 0:
                    problems.append(
                        f"{where}.{key}: acres_per_dwelling {acres_each} is not "
                        f"an area"
                    )
                    continue
                # MCC 39.5340(A) divides the site by the underlying district's
                # minimum lot area per dwelling unit, which in Rural Residential
                # is five acres. Four dwellings therefore need twenty, and
                # twenty is a figure the code prints nowhere.
                value = _per_dwelling(_in_acres(float(acres_each)))
            if floor_ft is not None and per_height is None and same_as is None:
                problems.append(
                    f"{where}.{key}: 'floor_ft' is the least a height-"
                    f"proportional or borrowed standard may come to, and there "
                    f"is no 'per_height_ft' and no 'same_as' here for it to floor"
                )
                continue
            if floor_ft is not None and (
                not isinstance(floor_ft, (int, float))
                or isinstance(floor_ft, bool)
                or floor_ft < 0
            ):
                problems.append(
                    f"{where}.{key}: floor_ft {floor_ft!r} is not a distance"
                )
                continue
            if per_height is not None:
                if value is not None or exempt:
                    problems.append(
                        f"{where}.{key}: a value states a distance or a ratio of "
                        f"building height, not both"
                    )
                    continue
                if not isinstance(per_height, (int, float)) or isinstance(
                    per_height, bool
                ):
                    problems.append(f"{where}.{key}: 'per_height_ft' expects a number")
                    continue
                if per_height <= 0:
                    problems.append(
                        f"{where}.{key}: per_height_ft {per_height} is not a ratio"
                    )
                    continue
                # "1 ft. for every 2 ft. of building height but not less than
                # 10 ft." is 13 ft for a 26 ft pod, and 13 is printed nowhere.
                value = _off_the_building(
                    float(per_height), None if floor_ft is None else float(floor_ft)
                )
            if same_as is not None:
                if value is not None or exempt:
                    problems.append(
                        f"{where}.{key}: a value states a standard of its own or "
                        f"states that it equals another, not both"
                    )
                    continue
                lent = out.get(str(same_as))
                if lent is None or not isinstance(lent.value, (int, float)) or (
                    isinstance(lent.value, bool)
                ):
                    problems.append(
                        f"{where}.{key}: 'same_as' borrows {same_as!r}, and "
                        f"there is no number for it here. The lender lives in "
                        f"the same block on purpose -- a borrowed standard is "
                        f"only as readable as the row it borrows from"
                    )
                    continue
                # "the same distance as the required building setbacks...
                # Regardless of other provisions, a minimum setback of ten
                # feet". Twenty-two is the answer in six Happy Valley
                # districts, and the sentence prints ten.
                value = float(lent.value)
                if floor_ft is not None:
                    value = max(value, float(floor_ft))
            if not exempt and value is None:
                problems.append(f"{where}.{key}: expected a 'value' or 'exempt: true'")
                continue
            before_step_back = None
            if step_back is not None and step_back.at_ft is not None:
                if exempt or not isinstance(value, (int, float)) or isinstance(
                    value, bool
                ):
                    problems.append(
                        f"{where}.{key}: a step-back is added to the district's "
                        f"own setback, and there is no distance here to add it to"
                    )
                    continue
                if step_back.rise is None or step_back.rise <= 0:
                    problems.append(
                        f"{where}.{key}: a step-back rises at a rate the code "
                        f"prints — state it as 'rise_per_ft'"
                    )
                    continue
                # Applied below, after the variants are parsed: a step-back
                # is a property of the standard rather than of its base, so
                # whatever setback the district's own rules produce, the roof
                # plane pushes it back by the same amount. Parsing the variants
                # against a base that had already moved would compound it.
                before_step_back = value
        else:
            # Shorthand: the scalar is the value, everything else is inherited.
            body = {}
            value = node
            exempt = False
            per_height = None
            floor_ft = None
            same_as = None
            step_back = None
            before_step_back = None
            per_dwelling = None
            sqft_per_unit = None
            per_units = None
            spaces_total = None
            acres = None
            acres_each = None
            measured_on = measured_on_cite = measured_on_quote = None
            qualified = qualified_cite = qualified_quote = None
            unless = ()
            raw_variants = ()

        prov_src: dict[str, Any] = dict(cite_default or {})
        prov_src.update({k: body[k] for k in _PROV_KEYS if k in body})
        missing = [k for k in ("cite", "url", "retrieved") if not prov_src.get(k)]
        if missing:
            problems.append(
                f"{where}.{key}: missing provenance {missing} — supply it on the value "
                f"or via cite_default. No unsourced numbers."
            )
            continue

        declared = str(body.get("status", "draft"))
        if declared in (Status.verified.value, Status.stale.value, Status.disputed.value):
            # Trust is not typeable. `verified` is a signature over the value,
            # its cite and its quote (flats/config/verifications.jsonl), and
            # `stale` is derived at load. Accepting either here would let an
            # edit to a YAML file certify a number nobody read.
            problems.append(
                f"{where}.{key}: a file may not declare status {declared!r} — "
                f"verify or dispute it with a signature, and leave stale to be derived"
            )
            continue

        try:
            prov = Provenance(**_prov_args(prov_src))
            variants = _parse_variants(
                raw_variants, prov_src, f"{where}.{key}", problems, base=value
            )
            if before_step_back is not None:
                # 21 ft of roof at the rear setback line, rising one foot per
                # foot further back, and a 26 ft box. Five more feet, and 20 is
                # printed in neither chapter.
                value = _stepped_back(
                    float(value), float(step_back.at_ft), float(step_back.rise)
                )
                variants = tuple(
                    variant
                    if not isinstance(variant.value, (int, float))
                    or isinstance(variant.value, bool)
                    else variant.model_copy(
                        update={
                            "before_step_back": float(variant.value),
                            "value": _stepped_back(
                                float(variant.value),
                                float(step_back.at_ft),
                                float(step_back.rise),
                            ),
                        }
                    )
                    for variant in variants
                )
            built = Value(
                name=key,
                value=value,
                exempt=exempt,
                per_dwelling=None if per_dwelling is None else float(per_dwelling),
                sqft_per_unit=None if sqft_per_unit is None else float(sqft_per_unit),
                per_units=None if per_units is None else float(per_units),
                spaces_total=(
                    None if spaces_total is None else float(spaces_total)
                ),
                acres=None if acres is None else float(acres),
                acres_per_dwelling=(
                    None if acres_each is None else float(acres_each)
                ),
                per_height_ft=None if per_height is None else float(per_height),
                floor_ft=None if floor_ft is None else float(floor_ft),
                same_as=None if same_as is None else str(same_as),
                step_back_at_ft=None if step_back is None else step_back.at_ft,
                step_back_rise=None if step_back is None else step_back.rise,
                step_back_degrees=None if step_back is None else step_back.degrees,
                step_back_cite=None if step_back is None else step_back.cite,
                step_back_quote=None if step_back is None else step_back.quote,
                before_step_back=before_step_back,
                measured_on=None if measured_on is None else str(measured_on),
                measured_on_cite=measured_on_cite,
                measured_on_quote=measured_on_quote,
                qualified_by=qualified,
                qualified_cite=qualified_cite,
                qualified_quote=qualified_quote,
                unless=tuple(unless),
                prov=prov,
                status=Status(declared),
                reviewer=body.get("reviewer"),
                reviewed=body.get("reviewed"),
                preempts=Preempt.read(body.get("preempts")),
                variants=variants,
            )
            if not (built.prov.quote or "").strip() and not built.prov.drawn:
                # Not an error in the file — encoding debt. The honest place for
                # it is a queue somebody can work, not a zone somebody screens.
                #
                # `drawn` is the one exception, and it is why the flag exists at
                # all. This quarantine reads a missing quote as "nobody has
                # sourced this number", which is true of every value that
                # reaches it but one: a figure that is drawn on the sheet rather
                # than written in it has been sourced, to a named person on a
                # named date, and it will never acquire a quote no matter how
                # long it sits in a queue. Holding it here would mean the
                # corpus could hold a number it can never use. The model
                # enforces what `drawn` must carry before it gets this
                # exemption; see `_check_drawn`.
                if wanted is not None:
                    wanted.append(Wanted(zone=zone, field=key, value=built))
                continue
            out[key] = built
        except Exception as exc:  # pydantic ValidationError or ValueError
            problems.append(f"{where}.{key}: {_terse(exc)}")
    return out


def _per_dwelling(each: float) -> float:
    """What a per-dwelling area comes to for the pod, kept whole where it is.

    5,000 square feet for each dwelling unit is 20,000 for a fourplex, not
    20,000.0 — for the same reason `_reduced` rounds: a file that reads
    20000.0 back out invites somebody to wonder which of the two the code said.
    """
    total = each * DWELLINGS
    return int(total) if float(total).is_integer() else total


def _in_acres(size: float) -> float:
    """Acres to square feet — the unit rural Oregon writes its lot sizes in.

    MCC 39.4245(A) asks 80 acres of a new EFU parcel; a parcel record answers
    in square feet, and 3,484,800 appears in no ordinance. The product is made
    here so that the file keeps the figure a reader can find, and kept whole
    where it is whole, for the reason `_per_dwelling` gives.
    """
    total = round(size * SQFT_PER_ACRE, 3)
    return int(total) if float(total).is_integer() else total


def _off_the_building(per_height: float, floor: float | None) -> float:
    """What a height-proportional standard comes to for the pod.

    Portland's Table 150-2 states IR's minimum setback as "1 ft. for every 2
    ft. of building height but not less than 10 ft." Both figures are printed
    and 13 is not, so the file keeps the two a reader can find and the quotient
    is made here -- the same bargain `_in_acres` and `_per_dwelling` strike.

    The floor is a maximum against the ratio, not a substitute for it: below
    the floor the ratio governs and above it the floor does, and which one
    binds depends on the building rather than on the code.
    """
    off_height = round(DESIGN_HEIGHT_FT / per_height, 3)
    total = max(off_height, floor) if floor is not None else off_height
    return int(total) if float(total).is_integer() else total


def _stepped_back(setback: float, at_ft: float, rise: float) -> float:
    """How far a building of this height stands back, given a roof-plane rule.

    Gresham 7.0420(G)(1): "The maximum roof height at the rear setback line is
    21 feet and increases at a rate of one foot in height for every one foot of
    distance further from the rear property line." A 26 ft box is five feet
    over the allowance at the line, and at one foot per foot it buys those five
    feet by standing five feet further back.

    A building shorter than the allowance owes nothing extra, which is the
    `max(0, ...)`: the rule limits a roof, and a roof under the limit is not
    pushed anywhere.
    """
    owed = max(0.0, (DESIGN_HEIGHT_FT - at_ft) / rise)
    total = round(setback + owed, 3)
    return int(total) if float(total).is_integer() else total


def _in_total(spaces: float) -> float:
    """A count of spaces a rule states for the whole building, said per unit.

    The denominator is not in the sentence as a digit; it is in the sentence as
    a word. OAR 660-046-0220(2)(e)(B) opens "For Quadplexes", and a quadplex is
    four dwellings -- :data:`DWELLINGS`, the same constant the per-dwelling
    conversions multiply by, used here the other way round.
    """
    return round(spaces / DWELLINGS, 3)


def _per_units(shared_between: float) -> float:
    """A rate a table prints as "1 per N units", said per unit.

    Only the numerator 1 is handled, because that is the shape every parking
    table in this corpus prints -- "1 per 2 units", "1 per 4 bedrooms". A cell
    reading "2 per 3 units" would need its own carrier rather than a division
    done here, and it would be better to notice that when it appears than to
    generalise for it now and get the rounding wrong for the case that exists.
    """
    return round(1.0 / shared_between, 3)


def _as_density(each: float) -> float:
    """An area per dwelling unit, said as dwellings per acre.

    Rounded to three places. The quotient is rarely whole -- 43,560 over 2,500
    is 17.424 -- and carrying the full float would put a number with fifteen
    digits of precision in front of a reader who is checking it against a table
    cell that says "2,500".
    """
    return round(SQFT_PER_ACRE / each, 3)


def _reduced(base: float, pct: float) -> float:
    """The base cut by a percentage, kept whole where the base is whole.

    A minimum lot area of 12,000 reduced by ten percent is 10,800 square feet,
    not 10,800.0 -- and a file that reads 10800.0 back out invites somebody to
    wonder which of the two the code said.
    """
    cut = base * (1.0 - pct / 100.0)
    rounded = round(cut, 6)
    return int(rounded) if float(rounded).is_integer() else rounded


def _parse_variants(
    raw: Any,
    prov_src: dict[str, Any],
    where: str,
    problems: list[str],
    base: Any = None,
) -> tuple[Variant, ...]:
    """Parse the exceptions attached to one standard.

    A variant inherits the base value's citation, because the usual case is one
    table cell with a footnote hanging off it. Overriding matters when the
    exception lives somewhere else entirely — a bonus chapter, a different
    section — and then the variant carries the citation for where *it* was read,
    which is what a reviewer will be sent to.
    """
    if not raw:
        return ()
    if not isinstance(raw, list):
        problems.append(f"{where}.variants: expected a list")
        return ()

    out: list[Variant] = []
    for i, node in enumerate(raw):
        at = f"{where}.variants[{i}]"
        if not isinstance(node, dict) or not (
            {
                "value",
                "exempt",
                "reduce_pct",
                "acres",
                "per_dwelling",
                "acres_per_dwelling",
                "spaces_total",
            }
            & set(node)
        ):
            problems.append(
                f"{at}: expected a mapping with a 'value', a 'reduce_pct', an "
                f"'acres', a 'per_dwelling', an 'acres_per_dwelling', a "
                f"'spaces_total', or 'exempt: true'"
            )
            continue
        body = dict(node)
        value = body.pop("value", None)
        exempt = bool(body.pop("exempt", False))
        acres = body.pop("acres", None)
        if acres is not None:
            if value is not None:
                problems.append(
                    f"{at}: a variant states a number or an acreage, not both"
                )
                continue
            if not isinstance(acres, (int, float)) or isinstance(acres, bool):
                problems.append(f"{at}: 'acres' expects a number")
                continue
            if acres <= 0:
                problems.append(f"{at}: acres {acres} is not an area")
                continue
            value = _in_acres(float(acres))
        each = body.pop("per_dwelling", None)
        if each is not None:
            if value is not None:
                problems.append(
                    f"{at}: a variant states a number or an area per dwelling "
                    f"unit, not both"
                )
                continue
            if not isinstance(each, (int, float)) or isinstance(each, bool):
                problems.append(f"{at}: 'per_dwelling' expects a number")
                continue
            if each <= 0:
                problems.append(f"{at}: per_dwelling {each} is not an area")
                continue
            # GMC 17.12.050 asks an average of 1,500 sq ft of each townhouse
            # dwelling. Four of them, 6,000 -- a figure the table prints
            # nowhere, and the one that binds.
            value = _per_dwelling(float(each))
        acres_each = body.pop("acres_per_dwelling", None)
        if acres_each is not None:
            if value is not None:
                problems.append(
                    f"{at}: a variant states a number or an acreage per "
                    f"dwelling unit, not both"
                )
                continue
            if not isinstance(acres_each, (int, float)) or isinstance(
                acres_each, bool
            ):
                problems.append(f"{at}: 'acres_per_dwelling' expects a number")
                continue
            if acres_each <= 0:
                problems.append(
                    f"{at}: acres_per_dwelling {acres_each} is not an area"
                )
                continue
            # MCC 39.5340(A) divides the site by the underlying district's
            # minimum lot area per dwelling unit. One acre in OR, four
            # dwellings, four acres -- a figure neither article prints.
            value = _per_dwelling(_in_acres(float(acres_each)))
        spaces_total = body.pop("spaces_total", None)
        if spaces_total is not None:
            if value is not None:
                problems.append(
                    f"{at}: a variant states a number or a count of spaces for "
                    f"the whole building, not both"
                )
                continue
            if not isinstance(spaces_total, (int, float)) or isinstance(
                spaces_total, bool
            ):
                problems.append(f"{at}: 'spaces_total' expects a number")
                continue
            if spaces_total <= 0:
                problems.append(
                    f"{at}: spaces_total {spaces_total} is not a count of "
                    f"spaces — a band that allows none states 'exempt: true'"
                )
                continue
            # OAR 660-046-0220(2)(e)(B) bands a quadplex's parking ceiling by
            # lot size: one space in total under 3,000 sq ft, four at 7,000.
            # A quarter of a space per unit is a figure the rule never prints.
            value = _in_total(float(spaces_total))
        reduce_pct = body.pop("reduce_pct", None)
        if reduce_pct is not None:
            if value is not None:
                problems.append(f"{at}: a variant states a number or a reduction, not both")
                continue
            if not isinstance(base, (int, float)) or isinstance(base, bool):
                # The reduction is arithmetic on the base, so a base that is a
                # curve, a flag or absent leaves nothing to reduce -- and
                # inventing a number here is exactly what the key exists to
                # stop.
                problems.append(
                    f"{at}: 'reduce_pct' needs a numeric base value to reduce; "
                    f"this standard's base is {base!r}"
                )
                continue
            try:
                value = _reduced(base, float(reduce_pct))
            except (TypeError, ValueError) as exc:
                problems.append(f"{at}.reduce_pct: {exc}")
                continue
        when = body.pop("when", None)
        if isinstance(when, str):
            when = [when]
        if when is None:
            when = []
        if not isinstance(when, list):
            problems.append(f"{at}: 'when' must list the condition(s) this applies under")
            continue
        raw_band = body.pop("band", None)
        band: Band | None = None
        if raw_band is not None:
            if not isinstance(raw_band, dict):
                problems.append(
                    f"{at}.band: expected a mapping — measure, and a bound: "
                    f"at_least or more_than, and/or at_most"
                )
                continue
            try:
                band = Band(**raw_band)
            except Exception as exc:
                problems.append(f"{at}.band: {_terse(exc)}")
                continue
        if not when and band is None:
            problems.append(
                f"{at}: 'when' must list the condition(s) this applies under, "
                f"or 'band' the lot sizes it was written for"
            )
            continue
        unknown = set(body) - set(_PROV_KEYS) - set(_REVIEW_KEYS)
        if unknown:
            problems.append(f"{at}: unknown key(s) {sorted(unknown)}")

        declared = str(body.get("status", "draft"))
        if declared in (Status.verified.value, Status.stale.value, Status.disputed.value):
            # Same rule as a base value: trust is a signature, not a keyword.
            # A variant is if anything easier to wave through, because it looks
            # like a detail of a value somebody already checked.
            problems.append(
                f"{at}: a file may not declare status {declared!r} — "
                f"verify or dispute it with a signature, and leave stale to be derived"
            )
            continue

        merged = dict(prov_src)
        merged.update({k: body[k] for k in _PROV_KEYS if k in body})
        try:
            out.append(
                Variant(
                    value=value,
                    exempt=exempt,
                    reduce_pct=None if reduce_pct is None else float(reduce_pct),
                    acres=None if acres is None else float(acres),
                    per_dwelling=None if each is None else float(each),
                    acres_per_dwelling=(
                        None if acres_each is None else float(acres_each)
                    ),
                    spaces_total=(
                        None if spaces_total is None else float(spaces_total)
                    ),
                    when=tuple(str(c) for c in when),
                    band=band,
                    prov=Provenance(**_prov_args(merged)),
                    status=Status(declared),
                    reviewer=body.get("reviewer"),
                    reviewed=body.get("reviewed"),
                )
            )
        except Exception as exc:
            problems.append(f"{at}: {_terse(exc)}")
    return tuple(out)


def _parse_sections(raw: object) -> tuple[str, ...]:
    """`section: "4.122"` or `section: ["4.122", "4.113"]`, both to a tuple."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw.strip(),) if raw.strip() else ()
    return tuple(str(item).strip() for item in raw if str(item).strip())


@dataclass(frozen=True)
class _StepBack:
    at_ft: float | None
    rise: float | None
    cite: str | None
    quote: str | None
    #: The angle, when that is what the code printed. Kept so the rule file
    #: holds the figure on the page and the rate stays computed.
    degrees: float | None = None


def _parse_step_back(raw: Any, where: str, problems: list[str]) -> _StepBack | None:
    """Parse a height limit near a lot line, and where the code prints it.

    Always a mapping. There is no shorthand because there is nothing short to
    say: the rule is a height, a rate and a section, and a bare number would be
    the half of it that decides nothing.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        problems.append(f"{where}.step_back: expected a mapping")
        return None

    body = dict(raw)
    at_ft = body.pop("height_ft", None)
    rise = body.pop("rise_per_ft", None)
    degrees = body.pop("slope_degrees", None)
    cite = body.pop("cite", None)
    quote = body.pop("quote", None)
    if body:
        problems.append(f"{where}.step_back: unknown key(s) {sorted(body)}")
    for label, number in (
        ("height_ft", at_ft),
        ("rise_per_ft", rise),
        ("slope_degrees", degrees),
    ):
        if number is not None and (
            not isinstance(number, (int, float)) or isinstance(number, bool)
        ):
            problems.append(f"{where}.step_back.{label}: expected a number")
            return None
    if at_ft is None:
        problems.append(
            f"{where}.step_back: state the height allowed at the setback line "
            f"under 'height_ft' — it is what the rule limits"
        )
        return None
    if rise is not None and degrees is not None:
        problems.append(
            f"{where}.step_back: states both a rate and an angle for the same "
            f"plane — write the one the code prints"
        )
        return None
    if degrees is not None:
        if not 0 < float(degrees) < 90:
            problems.append(
                f"{where}.step_back.slope_degrees: {degrees} is not a plane "
                f"rising from the setback line"
            )
            return None
        # Rounded because the right angles are the ones codes print, and
        # tan(45 degrees) coming back as 0.9999999999999999 would put a
        # setback at 11.000000000000002 and a slack figure just under
        # zero on a lot that exactly fits.
        rise = round(math.tan(math.radians(float(degrees))), 10)
    return _StepBack(
        float(at_ft),
        None if rise is None else float(rise),
        None if cite is None else str(cite),
        None if quote is None else str(quote),
        None if degrees is None else float(degrees),
    )


def _parse_measured_on(
    raw: Any,
    where: str,
    problems: list[str],
) -> tuple[str | None, str | None, str | None]:
    """Parse the quantity a rate is computed on, and where the code defines it.

    A bare string used to be the whole of it, and that was the bug: seven
    Oregon codes say "net acre" and subtract seven different lists to get
    there, so the name alone records nothing a reviewer can check. The mapping
    form names the fact and sends the reader to the sentence that says what
    this city takes out.

    The string form is still accepted and still incomplete — it parses, and
    :class:`~flats.rules.model.Value` refuses it, so the error names the
    missing citation rather than a YAML shape.
    """
    if raw is None:
        return None, None, None
    if isinstance(raw, str):
        return raw, None, None
    if not isinstance(raw, dict):
        problems.append(f"{where}.measured_on: expected a fact name or a mapping")
        return None, None, None

    body = dict(raw)
    fact = body.pop("fact", None)
    cite = body.pop("cite", None)
    quote = body.pop("quote", None)
    if body:
        problems.append(f"{where}.measured_on: unknown key(s) {sorted(body)}")
    if not fact:
        problems.append(
            f"{where}.measured_on: name the quantity under 'fact' — the rate is "
            f"computed on it"
        )
        return None, None, None
    return str(fact), None if cite is None else str(cite), None if quote is None else str(quote)


def _parse_qualified_by(
    raw: Any,
    where: str,
    problems: list[str],
) -> tuple[str | None, str | None, str | None]:
    """Parse a rule elsewhere that moves this standard on a fact nobody holds.

    Same shape as ``measured_on`` and the same reason for it: the fact is one
    name shared across the corpus, and the sentence that invokes it is local.
    Fairview's building height transition and Gresham's hillside release would
    both be "the height standard is not the whole rule here", and they are not
    the same rule, so each carries its own citation.

    The string form parses and :class:`~flats.rules.model.Value` refuses it, so
    a file that names a fact and cites nothing is told which half is missing
    rather than being told its YAML is the wrong shape.
    """
    if raw is None:
        return None, None, None
    if isinstance(raw, str):
        return raw, None, None
    if not isinstance(raw, dict):
        problems.append(f"{where}.qualified_by: expected a fact name or a mapping")
        return None, None, None

    body = dict(raw)
    fact = body.pop("fact", None)
    cite = body.pop("cite", None)
    quote = body.pop("quote", None)
    if body:
        problems.append(f"{where}.qualified_by: unknown key(s) {sorted(body)}")
    if not fact:
        problems.append(
            f"{where}.qualified_by: name the fact under 'fact' — the qualifying "
            f"rule turns on it"
        )
        return None, None, None
    return str(fact), None if cite is None else str(cite), None if quote is None else str(quote)


def _parse_like(
    raw: Any,
    cite_default: dict[str, Any] | None,
    where: str,
    problems: list[str],
) -> Incorporation | None:
    """Parse a zone's claim to adopt another zone's standards.

    Shorthand is a bare zone code, which inherits the zone's ``cite_default``
    and takes the common conflict rule (the zone's own statement wins). The
    full form is for when the incorporation is stated somewhere other than the
    zone's own section, or when the code's conflict clause runs the other way —
    both of which are things a reviewer has to be sent to the text for.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = {"zone": raw}
    if not isinstance(raw, dict):
        problems.append(f"{where}.like: expected a zone code or a mapping")
        return None

    body = dict(raw)
    zone = body.pop("zone", None)
    wins = body.pop("wins", "local")
    unknown = set(body) - set(_PROV_KEYS) - set(_REVIEW_KEYS) - {"preempts"}
    if unknown:
        problems.append(f"{where}.like: unknown key(s) {sorted(unknown)}")
    if not zone:
        problems.append(f"{where}.like: name the zone whose standards this one adopts")
        return None

    prov_src: dict[str, Any] = dict(cite_default or {})
    prov_src.update({k: body[k] for k in _PROV_KEYS if k in body})
    missing = [k for k in ("cite", "url", "retrieved") if not prov_src.get(k)]
    if missing:
        # Adopting another zone's standards is itself a rule somebody read.
        # Unsourced, it is a guess about which numbers govern a whole zone.
        problems.append(
            f"{where}.like: missing provenance {missing} — an incorporation is a rule too"
        )
        return None

    declared = str(body.get("status", "draft"))
    if declared in (Status.verified.value, Status.stale.value, Status.disputed.value):
        problems.append(
            f"{where}.like: a file may not declare status {declared!r} — "
            f"verify or dispute it with a signature, and leave stale to be derived"
        )
        return None

    try:
        return Incorporation(
            zone=str(zone),
            wins=str(wins),
            prov=Provenance(**_prov_args(prov_src)),
            status=Status(declared),
            reviewer=body.get("reviewer"),
            reviewed=body.get("reviewed"),
        )
    except Exception as exc:
        problems.append(f"{where}.like: {_terse(exc)}")
        return None


def _parse_code(raw: Any, where: str, problems: list[str]) -> tuple[CodeDocument, ...]:
    """Parse a layer's declaration of which documents hold its code."""
    if not raw:
        return ()
    if not isinstance(raw, list):
        problems.append(f"{where}.code: expected a list of documents")
        return ()

    out: list[CodeDocument] = []
    seen: set[str] = set()
    for i, node in enumerate(raw):
        at = f"{where}.code[{i}]"
        if not isinstance(node, dict):
            problems.append(f"{at}: expected a mapping with 'id' and 'url'")
            continue
        try:
            doc = CodeDocument(**node)
        except Exception as exc:
            problems.append(f"{at}: {_terse(exc)}")
            continue
        if doc.id in seen:
            # Two entries would fetch to the same file, and the second would
            # silently overwrite the first every run.
            problems.append(f"{at}: document {doc.id!r} declared twice")
            continue
        seen.add(doc.id)
        out.append(doc)
    return tuple(out)


def _adoptions(raw: object, *, where: str, problems: list[str]) -> list[str]:
    """Layer ids whose definitions this layer says it adopts.

    Deliberately dumb: a list of ids, in the order the code names them, and
    nothing is added that the YAML did not write down. The resolver never
    fills this in from the hierarchy, because "the county is above you" is a
    fact about our file layout and not about who wrote your definitions.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        problems.append(f"{where}.definitions_from: expected a list of layer ids")
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            problems.append(f"{where}.definitions_from: {item!r} is not a layer id")
            continue
        out.append(item.strip())
    return out


#: Short enough to be a shrug. A ruling that says "n/a" or "not relevant"
#: closes a queue row without telling the next reader anything, which is worse
#: than leaving the row open — the row at least still shows the sentence.
MIN_RULING = 40


def _parse_crossrefs(
    raw: object, *, where: str, problems: list[str]
) -> dict[str, Ruling]:
    """Sections this layer has read and ruled out of the cross-reference queue.

    Keyed by the number the ledger prints. Both halves are checked: a key
    nothing points at is a ruling on a reference that does not exist, and a
    one-word reason is a row closed rather than answered.

    Two authoring forms. A bare string is the original one and stays valid --
    the seventeen rulings written before the vocabulary existed are prose and
    load as ``read``. A mapping carries the shape of the decision beside the
    prose::

        crossrefs:
          "17.62.070": >-
            Setbacks for manufactured homes in a mobile home park ...
          "16.44.050":
            outcome: other_building
            note: >-
              Accessory dwelling unit standards ...

    The note is required in both forms and held to the same length, because
    the outcome is a filter and the note is the argument. A row closed with a
    tag and no reasoning tells the next reader less than an open row does: the
    open row at least still shows the sentence.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        problems.append(f"{where}.crossrefs: expected a mapping of section -> why")
        return {}
    out: dict[str, Ruling] = {}
    for ref, why in raw.items():
        ref = str(ref).strip()
        if not ref:
            problems.append(f"{where}.crossrefs: a ruling needs a section number")
            continue

        outcome = "read"
        if isinstance(why, dict):
            outcome = str(why.get("outcome", "read")).strip()
            if outcome not in CROSSREF_OUTCOMES:
                problems.append(
                    f"{where}.crossrefs.{ref}: unknown outcome {outcome!r}; "
                    f"one of {', '.join(sorted(CROSSREF_OUTCOMES))}"
                )
                continue
            extra = set(why) - {"outcome", "note"}
            if extra:
                problems.append(
                    f"{where}.crossrefs.{ref}: unexpected "
                    f"{', '.join(sorted(extra))}; a ruling is an outcome and a note"
                )
                continue
            why = why.get("note")

        if not isinstance(why, str) or len(why.strip()) < MIN_RULING:
            problems.append(
                f"{where}.crossrefs.{ref}: a ruling states why the chapter does "
                f"not reach this building, in at least {MIN_RULING} characters"
            )
            continue
        out[ref] = Ruling(" ".join(why.split()), outcome)
    return out


def _parse_readings(
    raw: object, *, where: str, problems: list[str]
) -> dict[str, Reading]:
    """Sections of this layer's own documents that have been read and ruled.

    The cross-reference block's twin, one step nearer home. ``crossrefs``
    records a chapter the store cannot open; this records a chapter it can,
    which somebody opened, and decided about::

        readings:
          "4.1100.downtown.txt#4.1152":
            queue: nofield
            outcome: design
            note: >-
              Facade articulation for the downtown design district ...
            fingerprint: 3f9a1c2b8e7d4560

    Always a mapping. There is no bare-string form and there will not be one:
    every ruling here was written by this queue, which knows its own outcome,
    and admitting a shape with no outcome would put untagged rows into a ledger
    whose whole purpose is to be counted by outcome.

    The fingerprint is optional and its absence is not an error -- a ruling can
    be written by hand -- but it is what lets a re-fetched document reopen the
    card instead of leaving it closed against words nobody has seen.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        problems.append(f"{where}.readings: expected a mapping of section -> ruling")
        return {}
    out: dict[str, Reading] = {}
    for key, body in raw.items():
        key = str(key).strip()
        if not key or "#" not in key:
            problems.append(
                f"{where}.readings: a key is '<document>#<section>'; got {key!r}"
            )
            continue
        if not isinstance(body, dict):
            problems.append(
                f"{where}.readings.{key}: a ruling is a queue, an outcome and a note"
            )
            continue
        extra = set(body) - {"queue", "outcome", "note", "fingerprint"}
        if extra:
            problems.append(
                f"{where}.readings.{key}: unexpected {', '.join(sorted(extra))}"
            )
            continue

        queue = str(body.get("queue", "")).strip()
        if queue not in READING_OUTCOMES:
            problems.append(
                f"{where}.readings.{key}: unknown queue {queue!r}; "
                f"one of {', '.join(sorted(READING_OUTCOMES))}"
            )
            continue
        outcome = str(body.get("outcome", "")).strip()
        # Checked against the queue that asked, not against every outcome the
        # vocabulary holds. "Different building" is a real answer to a section
        # we have no field for and a meaningless one to a chapter nobody has
        # opened, and a ruling that answers a question it was not asked is the
        # kind of row that reads fine and means nothing.
        if outcome not in READING_OUTCOMES[queue]:
            problems.append(
                f"{where}.readings.{key}: {outcome!r} is not an answer the "
                f"{queue} queue asks for; one of "
                f"{', '.join(sorted(READING_OUTCOMES[queue]))}"
            )
            continue
        note = body.get("note")
        if not isinstance(note, str) or len(note.strip()) < MIN_RULING:
            problems.append(
                f"{where}.readings.{key}: a ruling states what was read and why "
                f"it does or does not reach this building, in at least "
                f"{MIN_RULING} characters"
            )
            continue
        out[key] = Reading(
            queue=queue,
            outcome=outcome,
            note=" ".join(note.split()),
            fingerprint=str(body.get("fingerprint", "")).strip(),
        )
    return out


def _parse_words(
    raw: object, *, where: str, problems: list[str]
) -> dict[str, Reading]:
    """What the words this layer's standards are written in mean here::

        words:
          lot width:
            queue: defined
            outcome: differs
            note: >-
              Measured at the building line, not the frontage, so the 50 ft
              minimum is not the same 50 ft as Portland's ...
            fingerprint: 8c14be07a2f9

    Keyed by the word as :data:`flats.encode.words.GOVERNS` names it, in our
    vocabulary rather than the city's -- a code that files the entry "Lot,
    Width" and another that writes "lot width" are answering the same question,
    and keying on their spelling would make the ledger uncountable.

    ``queue`` is the standing the card had when it was answered. Checked
    against the outcome for the same reason a reading is: "means what we
    assumed" is not an answer anybody can give about a glossary nobody has
    opened, and a ruling that answers a question it was not asked reads fine
    and means nothing.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        problems.append(f"{where}.words: expected a mapping of word -> ruling")
        return {}
    out: dict[str, Reading] = {}
    for key, body in raw.items():
        term = str(key).strip().lower()
        if not term:
            problems.append(f"{where}.words: a key is the word being ruled on")
            continue
        if not isinstance(body, dict):
            problems.append(
                f"{where}.words.{term}: a ruling is a standing, an outcome and a note"
            )
            continue
        extra = set(body) - {"queue", "outcome", "note", "fingerprint"}
        if extra:
            problems.append(
                f"{where}.words.{term}: unexpected {', '.join(sorted(extra))}"
            )
            continue

        standing = str(body.get("queue", "")).strip()
        if standing not in WORD_OUTCOMES:
            problems.append(
                f"{where}.words.{term}: unknown standing {standing!r}; "
                f"one of {', '.join(sorted(WORD_OUTCOMES))}"
            )
            continue
        outcome = str(body.get("outcome", "")).strip()
        if outcome not in WORD_OUTCOMES[standing]:
            problems.append(
                f"{where}.words.{term}: {outcome!r} is not an answer asked of a "
                f"{standing} word; one of "
                f"{', '.join(sorted(WORD_OUTCOMES[standing]))}"
            )
            continue
        note = body.get("note")
        if not isinstance(note, str) or len(note.strip()) < MIN_RULING:
            problems.append(
                f"{where}.words.{term}: a ruling states what the code says and "
                f"how it differs from how we measure, in at least "
                f"{MIN_RULING} characters"
            )
            continue
        out[term] = Reading(
            queue=standing,
            outcome=outcome,
            note=" ".join(note.split()),
            fingerprint=str(body.get("fingerprint", "")).strip(),
        )
    return out


def _terse(exc: Exception) -> str:
    """Pydantic errors are verbose; keep the message a reviewer can scan."""
    msg = str(exc).replace("\n", " ")
    return msg[:300]


#: The *safe* loader, C-accelerated where PyYAML was built against libyaml and
#: the pure-Python one where it was not. Both are safe in the sense that
#: matters -- ``yaml.safe_load`` is exactly ``yaml.load(text, SafeLoader)``,
#: and ``CSafeLoader`` resolves the same closed tag set, so neither will
#: construct a Python object out of a rule file.
#:
#: Every review screen re-reads all nineteen jurisdiction files,
#: and the pure-Python scanner is most of what that costs -- two and a half
#: seconds a page, spent tokenising files that have not changed. Same grammar,
#: same safe tag set, same ``yaml.YAMLError`` on a file we cannot read; only
#: the speed differs, so there is nothing here to fall back *from* if a build
#: lacks the extension.
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def load_layer(path: Path, root: Path, problems: list[str]) -> Layer | None:
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_LOADER) or {}
    except yaml.YAMLError as exc:
        problems.append(f"{path}: unparseable YAML — {_terse(exc)}")
        return None
    if not isinstance(raw, dict):
        problems.append(f"{path}: expected a mapping at the top level")
        return None

    layer_id = _layer_id(path, root)
    where = layer_id or str(path)
    unknown = set(raw) - LAYER_META
    if unknown:
        problems.append(f"{where}: unknown top-level key(s) {sorted(unknown)}")

    layer_cite = raw.get("cite_default")
    wanted: list[Wanted] = []
    defaults = _parse_values(
        raw.get("defaults") or {},
        layer_cite,
        f"{where}.defaults",
        problems,
        wanted,
        # The same word every review command uses for a layer-wide standard, so
        # a queued default is addressable exactly like a read one.
        "defaults",
    )

    zones: dict[str, Zone] = {}
    for zname, zraw in (raw.get("zones") or {}).items():
        zraw = zraw or {}
        if not isinstance(zraw, dict):
            problems.append(f"{where}.zones.{zname}: expected a mapping")
            continue
        zone_cite = {**(layer_cite or {}), **(zraw.get("cite_default") or {})}
        value_keys = {k: v for k, v in zraw.items() if k not in ZONE_META}
        values = _parse_values(
            value_keys, zone_cite, f"{where}.zones.{zname}", problems, wanted, str(zname)
        )
        zones[str(zname)] = Zone(
            zone=str(zname),
            values=values,
            notes=zraw.get("notes"),
            clauses=tuple(zraw.get("clauses") or ()),
            section=_parse_sections(zraw.get("section")),
            like=_parse_like(zraw.get("like"), zone_cite, f"{where}.zones.{zname}", problems),
        )

    try:
        return Layer(
            layer=layer_id,
            kind=raw.get("kind") or _kind_for(layer_id, path.stem),
            label=raw.get("label") or layer_id,
            eligible=bool(raw.get("eligible", True)),
            defaults=defaults,
            zones=zones,
            notes=raw.get("notes"),
            wanted=tuple(wanted),
            ingest=raw.get("ingest") or {},
            code=_parse_code(raw.get("code"), where, problems),
            crossrefs=_parse_crossrefs(raw.get("crossrefs"), where=where, problems=problems),
            readings=_parse_readings(raw.get("readings"), where=where, problems=problems),
            words=_parse_words(raw.get("words"), where=where, problems=problems),
            definitions=parse_definitions(raw.get("definitions"), where=where, problems=problems),
            definitions_from=_adoptions(raw.get("definitions_from"), where=where, problems=problems),
        )
    except Exception as exc:
        problems.append(f"{where}: {_terse(exc)}")
        return None


def load_rules(root: Path | None = None, strict: bool = True) -> dict[str, Layer]:
    """Load every jurisdiction file under ``root`` keyed by layer id.

    ``strict`` raises :class:`RuleLoadError` on any problem. Pass ``False`` only
    from tooling that means to report problems rather than act on the rules —
    the pipeline itself must never run on a partially-valid rule set.
    """
    root = root or CONFIG_ROOT
    problems: list[str] = []
    layers: dict[str, Layer] = {}

    for path in sorted(root.rglob("*.yaml")):
        layer = load_layer(path, root, problems)
        if layer is None:
            continue
        if layer.layer in layers:
            problems.append(f"{layer.layer}: defined twice (second file {path})")
            continue
        layers[layer.layer] = layer

    if problems and strict:
        raise RuleLoadError(problems)
    # Always reassigned, including to empty — a stale list from an earlier
    # non-strict call would report problems the current rule set does not have.
    load_rules.last_problems = problems  # type: ignore[attr-defined]
    return layers
