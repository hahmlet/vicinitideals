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
from flats.rules.model import LAYER_META, ZONE_META, Layer, Provenance, Status, Value, Zone

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
) -> dict[str, Value]:
    """Turn a mapping of field name → (scalar | full object) into Values."""
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
            unknown = set(body) - set(_PROV_KEYS) - set(_REVIEW_KEYS)
            if unknown:
                problems.append(f"{where}.{key}: unknown key(s) {sorted(unknown)}")
        else:
            # Shorthand: the scalar is the value, everything else is inherited.
            body = {}
            value = node

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
            out[key] = Value(
                name=key,
                value=value,
                prov=prov,
                status=Status(declared),
                reviewer=body.get("reviewer"),
                reviewed=body.get("reviewed"),
                preempts=bool(body.get("preempts", False)),
            )
        except Exception as exc:  # pydantic ValidationError or ValueError
            problems.append(f"{where}.{key}: {_terse(exc)}")
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
    defaults = _parse_values(raw.get("defaults") or {}, layer_cite, f"{where}.defaults", problems)

    zones: dict[str, Zone] = {}
    for zname, zraw in (raw.get("zones") or {}).items():
        zraw = zraw or {}
        if not isinstance(zraw, dict):
            problems.append(f"{where}.zones.{zname}: expected a mapping")
            continue
        zone_cite = {**(layer_cite or {}), **(zraw.get("cite_default") or {})}
        value_keys = {k: v for k, v in zraw.items() if k not in ZONE_META}
        values = _parse_values(value_keys, zone_cite, f"{where}.zones.{zname}", problems)
        zones[str(zname)] = Zone(
            zone=str(zname),
            values=values,
            notes=zraw.get("notes"),
            clauses=tuple(zraw.get("clauses") or ()),
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
            ingest=raw.get("ingest") or {},
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
