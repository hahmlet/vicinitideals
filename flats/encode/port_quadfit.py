"""One-shot port of quadfit's flat rules table into the FLATS hierarchy.

Quadfit stored one ``(jurisdiction, zone)`` table with a single citation per zone
row covering every number in it. FLATS wants a state → county → city tree with
provenance on each value. The two are close enough that the port is mechanical,
with three deliberate differences:

**Everything lands as ``draft``.** Quadfit marked 73 of 96 rows ``verified``, but
that verification was against a coarser standard — one citation for eight numbers
drawn from four different tables. None of it inherits trust here. The original
confidence is preserved in the zone notes so the review queue can be ordered
sensibly: rows quadfit called verified are quick confirmations, rows it flagged
``needs_verification`` are real work.

**Zone-level ``cite_default`` carries the citation.** Each quadfit row had one
source for all its values, which is exactly what ``cite_default`` inheritance
expresses. Values that turn out to come from a different table get their own
citation during verification.

**Jurisdiction-level ``orientation_constraint`` is not ported.** Quadfit set it
per jurisdiction and justified it only in a YAML comment, so there is no citation
to attach and inventing one would defeat the point. It is recorded in the layer
notes as unported work. Zone-level overrides do port — those sit inside a zone
row and inherit its citation.

Run::

    python -m flats.encode.port_quadfit --write
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
QUADFIT_RULES = REPO_ROOT / "Lot Analysis" / "quadfit" / "config" / "rules.yaml"
OUT_ROOT = REPO_ROOT / "flats" / "config" / "jurisdictions"

#: Which county each quadfit jurisdiction sits in. Cities that straddle county
#: lines (Tualatin, Wilsonville, Lake Oswego) are filed under the county holding
#: the bulk of their residential land.
COUNTY: dict[str, str] = {
    "portland": "multnomah",
    "gresham": "multnomah",
    "troutdale": "multnomah",
    "fairview": "multnomah",
    "wood_village": "multnomah",
    "maywood_park": "multnomah",
    "multnomah_unincorporated": "multnomah",
    "lake_oswego": "clackamas",
    "happy_valley": "clackamas",
    "milwaukie": "clackamas",
    "oregon_city": "clackamas",
    "gladstone": "clackamas",
    "west_linn": "clackamas",
    "tualatin": "clackamas",
    "wilsonville": "clackamas",
    "rivergrove": "clackamas",
    "johnson_city": "clackamas",
    "clackamas_unincorporated": "clackamas",
}

#: quadfit column -> FLATS field. Anything not listed is carried into notes.
FIELD_MAP: dict[str, str] = {
    "quadplex_allowed": "quadplex_allowed",
    "setback_front_ft": "setback_front_ft",
    "setback_side_ft": "setback_side_ft",
    "setback_rear_ft": "setback_rear_ft",
    "setback_street_side_ft": "setback_street_side_ft",
    "min_lot_sqft": "min_lot_sqft",
    "coverage_curve": "coverage_curve",
    "coverage_pct": "max_coverage_pct",
    "max_coverage_pct": "max_coverage_pct",
    "max_far": "max_far",
    "max_height_ft": "max_height_ft",
    "min_frontage_ft": "min_frontage_ft",
    # Added 2026-09-02 with the column itself. Mirrored rather than backported:
    # the corpus read the figure and rules.yaml now carries the same number, so
    # the port maps it 1:1 and the mirror audit can check the two agree.
    "min_density_du_per_acre": "min_density_du_per_acre",
    # Zone-level orientation carries the zone's own citation, so it ports. Only
    # the jurisdiction-level default is unciteable — see the layer notes.
    "orientation_constraint": "orientation_constraint",
}

#: Keys that travel the OTHER WAY and so are not data loss when this port
#: ignores them. Everything else in quadfit's table is an original number that
#: has to reach a FLATS field or it is silently dropped -- which is what
#: `unported` counts. The step-back planes are the exception: the corpus read
#: them off the page first, and rules.yaml grew a `step_back_rear` /
#: `step_back_side` key on 2026-09-02 only so the pipeline could DERIVE the
#: setback a 26-foot building owes from the plane the code states, instead of
#: standing at a printed figure that assumes a shorter house. Porting them back
#: would be a round trip: the corpus already holds them, with the citation they
#: came from.
#:
#: `lot_size_bands` is the second, and it arrived the same way. Wilsonville
#: 4.113(.02) prints its setbacks as two lists -- "For lots over 10,000 square
#: feet" and "For lots not exceeding 10,000 square feet" -- and Milwaukie's
#: Table 19.302-1 and Gresham's MDR-24 density floor band the same way. The
#: corpus reads those bands off the page as `variants` carrying a `band:`, one
#: quote apiece; rules.yaml grew a flat `{field: [[threshold, value]]}` mirror
#: of them so the pipeline could apply the right column to a lot whose area it
#: knows. All 24 rows of that mirror are held here, which
#: `test_a_backported_band_has_to_already_be_here` walks and asserts.
#:
#: One difference is deliberate and runs the safe way: quadfit takes the
#: larger-lot column at exactly the threshold, where the code -- and so the
#: corpus -- puts a 10,000 sq ft lot in the "not exceeding" list. At that one
#: lot size quadfit asks for the bigger setback and the smaller coverage, which
#: is conservative. It is a rounding convention, not a reading, and the corpus
#: is the one that matches the sentence.
BACKPORTED: frozenset[str] = frozenset(
    {"step_back_rear", "step_back_side", "lot_size_bands"}
)

#: Retrieval dates from the quadfit header. Clackamas was compiled later.
RETRIEVED = {"multnomah": "2026-07-24", "clackamas": "2026-07-28"}

STATE_LAYER = """\
# Oregon statewide preemption layer.
#
# Values here apply to every jurisdiction below unless a more specific layer
# overrides them — except where marked `preempts: true`, which a local standard
# may not exceed. Everything is `draft` until confirmed against the adopted rule
# text; nothing in this file has been verified.
label: Oregon
kind: state
notes: >-
  HB 2001 / OAR 660-046 middle-housing mandate. ORS 197A.400 (renumbered from
  ORS 197.307(4), operative 2025-07-01) requires local governments to apply only
  clear and objective standards to housing development, which is what makes this
  screen tractable at all.
defaults:
  parking_min_per_unit:
    value: 1.0
    preempts: true
    cite: "OAR 660-046-0220"
    url: "https://oregon.public.law/rules/oar_660-046-0220"
    retrieved: 2026-08-12
    status: draft
"""


def layer_id_for(jurisdiction: str) -> str:
    """quadfit jurisdiction name -> FLATS layer id.

    The bridge between the old flat namespace and the hierarchy, used by the
    port itself and by anything joining legacy pipeline output to the new rules.
    """
    county = COUNTY.get(jurisdiction)
    if county is None:
        raise KeyError(f"no county mapping for jurisdiction {jurisdiction!r}")
    stem = "_unincorporated" if jurisdiction.endswith("_unincorporated") else jurisdiction.replace("_", "-")
    return f"or/{county}/{stem}"


def load_quadfit() -> dict[str, Any]:
    return yaml.safe_load(QUADFIT_RULES.read_text(encoding="utf-8"))


def port_zone(row: dict[str, Any], retrieved: str) -> tuple[dict[str, Any], list[str]]:
    """One quadfit zone row -> one FLATS zone block."""
    out: dict[str, Any] = {}
    unported: list[str] = []

    src, url = row.get("source"), row.get("source_url")
    if src and url:
        out["cite_default"] = {"cite": src, "url": url, "retrieved": retrieved}

    for key, value in row.items():
        if key in ("zone", "source", "source_url", "confidence", "notes"):
            continue
        if key in BACKPORTED:
            continue
        mapped = FIELD_MAP.get(key)
        if mapped is None:
            unported.append(f"{key}={value!r}")
            continue
        out[mapped] = value

    # Preserve quadfit's own confidence so the review queue can be ordered:
    # `verified` rows are confirmations, `needs_verification` rows are real work.
    note_parts = [f"quadfit confidence: {row.get('confidence', 'unknown')}"]
    if row.get("notes"):
        note_parts.append(str(row["notes"]))
    if unported:
        note_parts.append("UNPORTED from quadfit: " + "; ".join(unported))
    out["notes"] = " | ".join(note_parts)
    return out, unported


def port(write: bool) -> dict[str, Any]:
    cfg = load_quadfit()
    stats: Counter[str] = Counter()
    unported_all: list[str] = []
    files: dict[Path, str] = {}

    files[OUT_ROOT / "or" / "_state.yaml"] = STATE_LAYER

    for jname, jdata in (cfg.get("jurisdictions") or {}).items():
        county = COUNTY.get(jname)
        if county is None:
            raise SystemExit(f"no county mapping for jurisdiction {jname!r} — add it to COUNTY")
        retrieved = RETRIEVED[county]

        is_uninc = jname.endswith("_unincorporated")
        path = OUT_ROOT / Path(layer_id_for(jname) + ".yaml")

        zones: dict[str, Any] = {}
        for row in jdata.get("zones") or []:
            block, unported = port_zone(row, retrieved)
            zones[str(row["zone"])] = block
            stats["zones"] += 1
            stats[f"confidence_{row.get('confidence', 'unknown')}"] += 1
            unported_all.extend(f"{jname}:{row['zone']}: {u}" for u in unported)

        notes = [
            f"Ported from quadfit rules.yaml. Every value is `draft` — quadfit's "
            f"verification was against a coarser standard (one citation per row) "
            f"and does not carry over."
        ]
        if jdata.get("orientation_constraint"):
            notes.append(
                f"UNPORTED: orientation_constraint={jdata['orientation_constraint']!r}. "
                f"quadfit justified this in a YAML comment with no citation; it needs "
                f"its own encoding rather than invented provenance."
            )

        layer: dict[str, Any] = {
            "label": jname.replace("_", " ").title(),
            "kind": "unincorporated" if is_uninc else "city",
            "eligible": bool(jdata.get("eligible", True)),
            "notes": " ".join(notes),
            "ingest": {
                # GEOID is joined from the TIGER places layer at ingest and never
                # hand-typed; the slug is what humans navigate by.
                "geoid": None,
                "juris_city_codes": jdata.get("juris_city_codes") or [],
                "zoning_layer": jdata.get("zoning_layer"),
                "zone_field": jdata.get("zone_field"),
                "strip_lowercase_suffix": bool(jdata.get("strip_lowercase_suffix", False)),
            },
            "zones": zones,
        }
        files[path] = yaml.safe_dump(layer, sort_keys=False, allow_unicode=True, width=100)
        stats["layers"] += 1
        stats[f"county_{county}"] += 1
        if not layer["eligible"]:
            stats["ineligible"] += 1

    if write:
        for path, body in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

    return {"stats": dict(stats), "unported": unported_all, "files": sorted(map(str, files))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="Write files (otherwise dry run).")
    args = ap.parse_args()

    result = port(args.write)
    stats = result["stats"]
    print(f"{'WROTE' if args.write else 'DRY RUN'} — {stats.get('layers')} layers, {stats.get('zones')} zones")
    for key in sorted(stats):
        if key.startswith(("confidence_", "county_")) or key == "ineligible":
            print(f"  {key}: {stats[key]}")
    if result["unported"]:
        print(f"\n{len(result['unported'])} unported field(s):")
        for u in result["unported"][:20]:
            print(f"  {u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
