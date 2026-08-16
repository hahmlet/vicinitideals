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

from flats.rules.fields import field
from flats.rules.model import (
    LAYER_META,
    ZONE_META,
    CodeDocument,
    Incorporation,
    Layer,
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

        if isinstance(node, dict) and "value" in node:
            body = dict(node)
            value = body.pop("value")
            raw_variants = body.pop("variants", None) or ()
            unknown = set(body) - set(_PROV_KEYS) - set(_REVIEW_KEYS)
            if unknown:
                problems.append(f"{where}.{key}: unknown key(s) {sorted(unknown)}")
        else:
            # Shorthand: the scalar is the value, everything else is inherited.
            body = {}
            value = node
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
            variants = _parse_variants(raw_variants, prov_src, f"{where}.{key}", problems)
            built = Value(
                name=key,
                value=value,
                prov=prov,
                status=Status(declared),
                reviewer=body.get("reviewer"),
                reviewed=body.get("reviewed"),
                preempts=bool(body.get("preempts", False)),
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


def _parse_variants(
    raw: Any,
    prov_src: dict[str, Any],
    where: str,
    problems: list[str],
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
        if not isinstance(node, dict) or not ({"value", "exempt"} & set(node)):
            problems.append(f"{at}: expected a mapping with a 'value', or 'exempt: true'")
            continue
        body = dict(node)
        value = body.pop("value", None)
        exempt = bool(body.pop("exempt", False))
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
