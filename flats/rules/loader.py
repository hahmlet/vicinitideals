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

from pathlib import Path
from typing import Any

import yaml

from flats.rules.fields import DWELLINGS, SQFT_PER_ACRE, field
from flats.rules.definitions import parse as parse_definitions
from flats.rules.model import (
    LAYER_META,
    ZONE_META,
    CodeDocument,
    Incorporation,
    Layer,
    Preempt,
    Provenance,
    Status,
    Value,
    Band,
    Variant,
    Wanted,
    Zone,
)

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config" / "jurisdictions"

_PROV_KEYS = ("cite", "url", "retrieved", "quote", "clause")
_REVIEW_KEYS = ("status", "reviewer", "reviewed", "preempts")


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
    for key, node in raw.items():
        try:
            field(key)
        except KeyError as exc:
            problems.append(f"{where}: {exc.args[0]}")
            continue

        if isinstance(node, dict) and (
            {"value", "exempt", "per_dwelling", "sqft_per_unit", "acres"} & set(node)
        ):
            body = dict(node)
            value = body.pop("value", None)
            exempt = bool(body.pop("exempt", False))
            per_dwelling = body.pop("per_dwelling", None)
            sqft_per_unit = body.pop("sqft_per_unit", None)
            acres = body.pop("acres", None)
            measured_on, measured_on_cite, measured_on_quote = _parse_measured_on(
                body.pop("measured_on", None), f"{where}.{key}", problems
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
            if not exempt and value is None:
                problems.append(f"{where}.{key}: expected a 'value' or 'exempt: true'")
                continue
        else:
            # Shorthand: the scalar is the value, everything else is inherited.
            body = {}
            value = node
            exempt = False
            per_dwelling = None
            sqft_per_unit = None
            acres = None
            measured_on = measured_on_cite = measured_on_quote = None
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
        if declared in (Status.verified.value, Status.stale.value):
            # Trust is not typeable. `verified` is a signature over the value,
            # its cite and its quote (flats/config/verifications.jsonl), and
            # `stale` is derived at load. Accepting either here would let an
            # edit to a YAML file certify a number nobody read.
            problems.append(
                f"{where}.{key}: a file may not declare status {declared!r} — "
                f"verify it with a signature, and leave stale to be derived"
            )
            continue

        try:
            prov = Provenance(**{k: prov_src.get(k) for k in _PROV_KEYS})
            variants = _parse_variants(
                raw_variants, prov_src, f"{where}.{key}", problems, base=value
            )
            built = Value(
                name=key,
                value=value,
                exempt=exempt,
                per_dwelling=None if per_dwelling is None else float(per_dwelling),
                sqft_per_unit=None if sqft_per_unit is None else float(sqft_per_unit),
                acres=None if acres is None else float(acres),
                measured_on=None if measured_on is None else str(measured_on),
                measured_on_cite=measured_on_cite,
                measured_on_quote=measured_on_quote,
                unless=tuple(unless),
                prov=prov,
                status=Status(declared),
                reviewer=body.get("reviewer"),
                reviewed=body.get("reviewed"),
                preempts=Preempt.read(body.get("preempts")),
                variants=variants,
            )
            if not (built.prov.quote or "").strip():
                # Not an error in the file — encoding debt. The honest place for
                # it is a queue somebody can work, not a zone somebody screens.
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
        if not isinstance(node, dict) or not ({"value", "exempt", "reduce_pct"} & set(node)):
            problems.append(
                f"{at}: expected a mapping with a 'value', a 'reduce_pct', or 'exempt: true'"
            )
            continue
        body = dict(node)
        value = body.pop("value", None)
        exempt = bool(body.pop("exempt", False))
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
        if declared in (Status.verified.value, Status.stale.value):
            # Same rule as a base value: trust is a signature, not a keyword.
            # A variant is if anything easier to wave through, because it looks
            # like a detail of a value somebody already checked.
            problems.append(
                f"{at}: a file may not declare status {declared!r} — "
                f"verify it with a signature, and leave stale to be derived"
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
                    when=tuple(str(c) for c in when),
                    band=band,
                    prov=Provenance(**{k: merged.get(k) for k in _PROV_KEYS}),
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
    if declared in (Status.verified.value, Status.stale.value):
        problems.append(
            f"{where}.like: a file may not declare status {declared!r} — "
            f"verify it with a signature, and leave stale to be derived"
        )
        return None

    try:
        return Incorporation(
            zone=str(zone),
            wins=str(wins),
            prov=Provenance(**{k: prov_src.get(k) for k in _PROV_KEYS}),
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


def _terse(exc: Exception) -> str:
    """Pydantic errors are verbose; keep the message a reviewer can scan."""
    msg = str(exc).replace("\n", " ")
    return msg[:300]


def load_layer(path: Path, root: Path, problems: list[str]) -> Layer | None:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
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
