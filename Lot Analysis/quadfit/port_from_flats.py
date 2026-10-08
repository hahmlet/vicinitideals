"""Write rules.yaml blocks for jurisdictions the FLATS corpus encoded first.

Multnomah and Clackamas went quadfit -> FLATS (`flats.encode.port_quadfit`).
Washington County went the other way: the corpus read six codes before this
pipeline had a row for any of them, and s3 drops a lot whose zone rules.yaml
does not list (`zone_not_in_rules`) before anything is measured. So the list
has to come from the corpus, and this is the one place it is derived.

What each row carries, and why it is the safe side:

* ``quadplex_allowed`` -- True when the base OR any variant allows the pod.
  s3 only decides whether a lot is MEASURED; FLATS resolves the permission
  per lot. A zone measured and then refused costs a few seconds; a zone not
  measured is a lot FLATS can never answer.
* setbacks and every ``min_*`` -- the LARGEST limb (the 0504ef84 precedent:
  s5 cuts quadfit's own envelope with this number and nothing downstream
  widens it, so the smaller limb is the one that could make a green).
* ``max_coverage_pct`` -- the SMALLEST limb, for the same reason.
* an exempt value, a band-only value, a non-number -- left out. quadfit reads
  an absent column as "no such standard", and FLATS holds the real answer.
* the three yards, which quadfit requires of any zone that allows the pod:
  an exempt yard is 0 (the code states none, FLATS cuts it at 0 too); a yard
  the corpus has not read is a PLACEHOLDER at the largest figure that layer
  states for the same yard anywhere, said so in the row's notes. FLATS
  answers such a lot UNKNOWN on the missing field whatever quadfit measured;
  the placeholder only decides how big a fallback envelope quadfit draws,
  and the largest yard in the city is the one that cannot draw it too big.

Every row is ``needs_verification``: the numbers are the corpus's drafts and
the mirror audit (`audit_zone_mirror.py`) holds the two files to each other
from here on. Map spellings travel as ``zone_aliases`` from the layer's
``alias`` rulings; pockets need nothing here, s3 reads them off the corpus.

Run::

    python "Lot Analysis/quadfit/port_from_flats.py"          # print
    python "Lot Analysis/quadfit/port_from_flats.py" --write  # splice into rules.yaml
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
REPO = TOOL_DIR.parents[1]
sys.path.insert(0, str(TOOL_DIR))
sys.path.insert(0, str(REPO))

from audit_zone_mirror import MIRRORED, _effective  # noqa: E402

RULES = TOOL_DIR / "config" / "rules.yaml"
BEGIN = "  # >>> ported from the FLATS corpus by port_from_flats.py -- edit the corpus, not these rows"
END = "  # <<< end of ported blocks"

#: Where the smaller number is the stricter one.
SMALLER_BINDS = frozenset({"max_coverage_pct"})
#: quadfit refuses a zone that allows the pod without these (common.ZoneRule).
YARDS = ("setback_front_ft", "setback_side_ft", "setback_rear_ft")


@dataclass(frozen=True)
class Target:
    slug: str
    layer_id: str
    juris_city_codes: tuple[str, ...]
    zoning_layer: str
    zone_field: str
    county_codes: tuple[str, ...] = ()
    require_inside_ugb: bool = False
    comment: str = ""


#: The jurisdictions this writes. JURIS_CITY literals read off Metro's
#: Taxlots (Public) service, COUNTY='W', 2026-09-30: no blank values in
#: Washington County, so the unincorporated block needs no "".
TARGETS: tuple[Target, ...] = (
    Target(
        "washington_unincorporated", "or/washington/_unincorporated", ("UNINCORPORATED",),
        "zoning_washington_county", "LUD", county_codes=("W",), require_inside_ugb=True,
        comment="Community Development Code; county Open_Data_AGOL layer 2, field LUD. "
        "Rural districts (EFU, EFC, AF-*, RR-5, R-COM, R-IND, MA-E) are ruled "
        "quadplex_allowed false in the corpus, and the UGB gate stands in front of them.",
    ),
    Target("hillsboro", "or/washington/hillsboro", ("HILLSBORO",), "zoning_hillsboro", "DESCRIPTIO"),
    Target("beaverton", "or/washington/beaverton", ("BEAVERTON",), "zoning_beaverton", "ZONE_NAME"),
    Target("sherwood", "or/washington/sherwood", ("SHERWOOD",), "zoning_sherwood", "CODE"),
    Target(
        "king_city", "or/washington/king-city", ("KING CITY",), "zoning_king_city", "ZONECLASS",
        comment="Two layers of one service merged at acquire: layer 1 (ZONECLASS) and the "
        "Kingston Terrace layer 4 (Zoning_Designations, copied into ZONECLASS).",
    ),
    Target(
        "durham", "or/washington/durham", ("DURHAM",), "zoning_metro", "ZONE",
        comment="No city zoning service; Metro's regional layer, as Fairview.",
    ),
    Target(
        "canby", "or/clackamas/canby", ("CANBY",), "zoning_canby", "ZONE",
        comment="Canby Municipal Code Title 16 (American Legal); the regional zoning "
        "fabric's CITY = 'Canby' polygons. Outside Metro: JURIS_CITY CANBY is read "
        "off the Clackamas roll.",
    ),
    Target(
        "sandy", "or/clackamas/sandy", ("SANDY",), "zoning_sandy", "ZONE",
        comment="Sandy Development Code, Title 17 (Municode); the regional zoning "
        "fabric's CITY = 'Sandy' polygons. Outside Metro: JURIS_CITY SANDY is read "
        "off the Clackamas roll.",
    ),
    Target(
        "estacada", "or/clackamas/estacada", ("ESTACADA",), "zoning_estacada", "ZONE",
        comment="Estacada Municipal Code Title 16 (Municipal Code Online); the regional "
        "zoning fabric's CITY = 'Estacada' polygons. Outside Metro: JURIS_CITY ESTACADA "
        "is read off the Clackamas roll.",
    ),
)


def _number(x: Any) -> float | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _limbs(value: Any) -> list[float]:
    out: list[float] = []
    if value is None:
        return out
    if not getattr(value, "exempt", False):
        n = _number(value.value)
        if n is not None:
            out.append(n)
    for v in getattr(value, "variants", ()) or ():
        if getattr(v, "exempt", False):
            continue
        n = _number(v.value)
        if n is not None:
            out.append(n)
    return out


def _allowed(value: Any) -> bool:
    if value is None:
        return False
    if value.value is True:
        return True
    return any(v.value is True for v in (getattr(value, "variants", ()) or ()))


def _num(x: float) -> int | float:
    return int(x) if float(x).is_integer() else x


def _getter(layer: Any, name: str):
    eff = _effective(layer, layer.zones[name])
    return lambda field: eff.get(field) or layer.defaults.get(field)


def largest_yards(layer: Any) -> dict[str, float]:
    """The largest figure the layer states for each yard, any zone, any limb."""
    out: dict[str, float] = {}
    for name in layer.zones:
        get = _getter(layer, name)
        for yard in YARDS:
            limbs = _limbs(get(yard))
            if limbs:
                out[yard] = max(out.get(yard, 0.0), *limbs)
    return out


def zone_row(layer: Any, name: str, layer_id: str, placeholders: dict[str, float]) -> dict[str, Any]:
    get = _getter(layer, name)
    row: dict[str, Any] = {"zone": name, "quadplex_allowed": _allowed(get("quadplex_allowed"))}
    held: list[str] = []
    if row["quadplex_allowed"]:
        for mine, theirs in MIRRORED.items():
            limbs = _limbs(get(theirs))
            if not limbs:
                continue
            row[mine] = _num(min(limbs) if mine in SMALLER_BINDS else max(limbs))
        for yard in YARDS:
            if yard in row:
                continue
            v = get(yard)
            if v is not None and v.exempt and not _limbs(v):
                row[yard] = 0
            else:
                row[yard] = _num(placeholders[yard])
                held.append(yard)
    prov = None
    for field in ("quadplex_allowed", "setback_front_ft", "min_lot_sqft"):
        v = get(field)
        if v is not None:
            prov = v.prov
            break
    if prov is not None:
        row["source"] = prov.cite
        row["source_url"] = prov.url
    row["confidence"] = "needs_verification"
    row["notes"] = (
        f"Ported from the FLATS corpus ({layer_id} {name}) by port_from_flats.py: "
        "larger limb of every setback and minimum, smaller of coverage."
    )
    if held:
        row["notes"] += (
            f" PLACEHOLDER {', '.join(held)}: the corpus has not read this yard; held at the "
            "largest the layer states anywhere, and FLATS answers the lot UNKNOWN on it."
        )
    return row


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return _q(str(v))


def block(t: Target, layers: dict[str, Any]) -> str:
    layer = layers[t.layer_id]
    lines = [f"  {t.slug}:", "    eligible: true"]
    if t.comment:
        lines.insert(1, f"    # {t.comment}")
    lines.append(f"    juris_city_codes: [{', '.join(t.juris_city_codes)}]")
    if t.county_codes:
        lines.append(f"    county_codes: [{', '.join(t.county_codes)}]")
    lines.append(f"    zoning_layer: {t.zoning_layer}")
    lines.append(f"    zone_field: {t.zone_field}")
    if t.require_inside_ugb:
        lines.append("    require_inside_ugb: true")
    lines.append("    orientation_constraint: entrance_only")
    aliases = {
        code: r.of
        for code, r in sorted(layer.zone_rulings.items())
        if r.outcome == "alias" and r.of in layer.zones
    }
    if aliases:
        lines.append("    zone_aliases:")
        for code, of in aliases.items():
            lines.append(f"      {_q(code)}: {_q(of)}")
    lines.append("    zones:")
    placeholders = largest_yards(layer)
    for name in layer.zones:
        row = zone_row(layer, name, t.layer_id, placeholders)
        first = True
        for k, v in row.items():
            lines.append(f"      {'- ' if first else '  '}{k}: {_scalar(v)}")
            first = False
    return "\n".join(lines)


def render(layers: dict[str, Any] | None = None) -> str:
    if layers is None:
        from flats.rules.loader import load_rules

        layers = load_rules()
    body = "\n\n".join(block(t, layers) for t in TARGETS)
    return f"{BEGIN}\n\n{body}\n\n{END}\n"


def splice(text: str, ported: str) -> str:
    """rules.yaml with the ported region replaced, or appended at the end."""
    if BEGIN in text:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        return head + ported.rstrip("\n") + tail
    return text.rstrip("\n") + "\n\n" + ported


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    ported = render()
    if not args.write:
        print(ported)
        return
    raw = RULES.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    out = splice(text, ported)
    if crlf:
        out = out.replace("\n", "\r\n")
    RULES.write_bytes(out.encode("utf-8"))
    print(f"wrote {len(TARGETS)} blocks into {RULES}")


if __name__ == "__main__":
    main()
