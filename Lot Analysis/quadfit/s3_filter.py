"""s3 — STRUCTURAL eligibility filter: reduce all Multnomah lots to the set
worth running geometry on. Only exclusions that no plausible config change can
reverse are applied here; POLICY exclusions (jurisdiction on/off, z overlay,
minimum lot area, minimum frontage) are annotated as columns and applied at
report time in s7 — so toggling a jurisdiction or adjusting a threshold needs
only an s7 re-run (seconds), not a pipeline re-run.

Structural drops (first-hit counted, written to funnel.json; every dropped
TLID with its step to s3_dropped.csv, for the FLATS stage that owes each lot
in the county an answer):
  0. not a taxlot: the right-of-way and the water, which the taxlot file
     holds as polygons of their own (Multnomah `-STR` / `-RIV` / `-RR`,
     Clackamas `ROADS` / `WATER`; `common.NOT_A_TAXLOT_RE`). s4 looks
     through them, out of s1, when it measures an alley's width; nothing
     else downstream should ever see one. 2,636 reached lots_results.csv
     before 2026-09-13 (1,778 `-STR`, 756 `ROADS`, 49 `WATER`, 28 `-RIV`,
     25 `-RR`), 39 of them in review and one green.
  1a. condominium record (`condo_excluded`): s1's `condo_verdict` is
     `excluded` -- the assessor's property code names a condominium interest
     on a parcel too small to be the common-element land, or the parcel is
     below any fourplex's physical minimum. `flats.normalize.condo`'s test,
     the one FLATS's lot table applies, so the two universes agree; the
     reason (`CONDO_AIR_PARCEL`, `LOT_BELOW_PHYSICAL_MINIMUM`) rides in
     s3_dropped.csv's `reason` column. Before 2026-09-28 only 1b ran, and
     ~2,000 Multnomah unit records drawn as lots of their own were measured
     every run.
  1b. condo-stack representative (stacked platting is not a redevelopable lot)
  2. jurisdiction unmapped (JURIS_CITY not in rules)
     -- then POCKETS, which drop nothing: a lot whose map prints another
     jurisdiction's zone (FLATS's `zone_rulings` outcome `pocket`, e.g.
     Milwaukie's R-MD on four lots the roll still calls unincorporated
     Clackamas) is measured under that jurisdiction's rules when quadfit
     holds the zone there. Its `jurisdiction` / `zone_raw` become the
     rules' ones, so every later stage and the FLATS bridge read that
     layer's standards; the map's own say stays in `home_jurisdiction` /
     `home_zone_raw`, and `pocket_of` names the FLATS layer. See
     `pocket_rewrites`.
  3. jurisdiction ineligible AND no zone rules compiled (e.g. Maywood Park —
     can't come back without new research; ineligible jurisdictions WITH
     compiled zone rules, e.g. Lake Oswego, are kept and gated in s7)
  4. outside UGB where the jurisdiction requires it (statutory, stable)
  5. no zone assigned (zoning layer gap)
  6. zone not present in rules table
  7. zone present but quadplex not allowed (no setbacks to build an envelope)
  8. sliver / degenerate: lot smaller than sliver_min_lot_sqft, or nowhere
     20 ft wide (negative 10 ft buffer collapses to empty)

Lots surviving here may still be policy-excluded in s7 (z overlay, min lot
area, min frontage, ineligible-but-compiled jurisdiction).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import DATA_DIR, NOT_A_TAXLOT_RE, load_rules, read_stage, write_stage

NARROW_TEST_BUFFER_FT = -10.0  # lot must survive a 10 ft inward buffer somewhere


def pocket_rewrites(
    pairs: Iterable[tuple[str, str]], rules: Any, layers: dict[str, Any] | None = None
) -> dict[tuple[str, str], tuple[str, str, str]]:
    """``(jurisdiction, zone_raw) -> (rules jurisdiction, zone, FLATS layer id)``
    for every pair that is a pocket quadfit can measure.

    A pocket is FLATS's ruling, read here rather than restated: the home
    layer's ``zone_rulings`` names the code ``outcome: pocket`` and the layer
    whose zoning it is (``of``), and ``flats.ingest.normalize.pocket_zone``
    says which block of that layer answers -- the same calls the normalize
    stage makes, so the lot FLATS screens under the other layer is the lot
    quadfit measures under it. A pair is rewritten only when

    * quadfit's home jurisdiction holds no rule for the code (a pocket is a
      code that is NOT a zone here -- FLATS's loader forbids both at once);
    * the ruling names a block. ``zone: map`` pockets (Troutdale's NSA,
      Oregon City's ``County``) need the other layer's map read lot by lot
      and s2 reads one map per lot, so those stay ``zone_not_in_rules``;
    * quadfit's rules for the ``of`` jurisdiction hold that block. Where
      they do not, the lot stays at ``zone_not_in_rules`` and FLATS answers
      it at the use gate, as it has since run 33 (174 lots, all red on use).
    """
    from flats.encode.port_quadfit import layer_id_for
    from flats.ingest.normalize import pocket_of, pocket_zone, zone_for

    if layers is None:
        from flats.rules.loader import load_rules as load_layers

        layers = load_layers()
    layer_of: dict[str, str] = {}
    slug_of: dict[str, str] = {}
    for slug in rules.jurisdictions:
        try:
            lid = layer_id_for(slug)
        except KeyError:
            continue
        layer_of[slug] = lid
        slug_of[lid] = slug
    out: dict[tuple[str, str], tuple[str, str, str]] = {}
    for juris, zone_raw in pairs:
        home = rules.jurisdictions.get(juris)
        if home is None or zone_raw is None or home.rule_for(zone_raw) is not None:
            continue
        layer = layers.get(layer_of.get(juris, ""))
        if layer is None:
            continue
        code, held_here = zone_for(layer, zone_raw)
        ruling = pocket_of(layer, code) if held_here is None else None
        if ruling is None or ruling.pocket_code(code) is None:
            continue
        other, held = pocket_zone(ruling, code, layers)
        of_slug = slug_of.get(ruling.of or "")
        if other is None or held is None or of_slug is None:
            continue
        if rules.jurisdictions[of_slug].rule_for(held) is None:
            continue
        out[(juris, zone_raw)] = (of_slug, held, str(ruling.of))
    return out


def structural_filter(
    lots: Any, rules: Any, layers: dict[str, Any] | None = None, *, say: Any = print
) -> tuple[Any, list[dict], Any]:
    """The structural drops, in order: ``(kept lots, funnel, dropped)``.

    ``dropped`` is one row per dropped TLID: the ``step`` that took it and,
    where the step has one, the ``reason`` behind it (the condominium test's
    code). ``layers`` is the FLATS corpus the pocket rulings are read from
    (:func:`pocket_rewrites`); None loads it. A pocket drops nothing, so it
    is not a funnel row (s7 prints every row as a drop): the kept lot says
    it in ``pocket_of``, and the log names each ruling applied.
    """
    import numpy as np
    import pandas as pd
    import shapely

    lots = lots.copy()
    funnel: list[dict] = [{"step": "all_taxlots", "count": int(len(lots))}]

    # Every dropped lot by name, so a reader downstream (the FLATS assign
    # stage, which owes every lot in the county an answer) can say WHICH step
    # kept a lot from being measured instead of only how many.
    dropped: list[pd.DataFrame] = []

    def drop(mask, step: str, reason_column: str | None = None):
        nonlocal lots
        mask = np.asarray(mask, dtype=bool)
        n = int(mask.sum())
        if n:
            gone = lots[mask]
            reason = (gone[reason_column].astype(object).where(gone[reason_column].notna(), "").to_numpy()
                      if reason_column else "")
            dropped.append(pd.DataFrame({
                "TLID": gone["TLID"].astype(str).to_numpy(), "step": step, "reason": reason,
            }))
            lots = lots[~mask]
        funnel.append({"step": step, "dropped": n, "remaining": int(len(lots))})
        say(f"  -{n:>8,}  {step:<28} remaining {len(lots):,}")

    say(f"s3: starting from {len(lots):,} lots (structural filter only)")

    # The right-of-way and the water, first, so no later count includes a
    # street. s4 reads the street polygons back out of s1_lots to measure an
    # alley's width, which is the only use anything here has for them.
    drop(lots["TLID"].astype(str).str.contains(NOT_A_TAXLOT_RE, regex=True),
         "not_a_taxlot")
    # Condominium records by the roll's property code (s1's verdict), before
    # the stack test -- the order FLATS's normalize runs the two in.
    if "condo_verdict" in lots.columns:
        drop(lots["condo_verdict"] == "excluded", "condo_excluded", "condo_reason")
    else:
        say("s3: WARNING s2_lots carries no condo_verdict (s1 predates 2026-09-28); "
            "condominium unit records are NOT dropped -- re-run from s1")
    drop(lots["stacked"], "condo_stack")
    drop(lots["jurisdiction"].isna(), "jurisdiction_unmapped")

    # Pockets: another jurisdiction's zoning on this jurisdiction's map,
    # measured under that jurisdiction's rules. Before the jurisdiction
    # gates, so the eligibility and UGB tests are the rules layer's too --
    # FLATS gates a pocket lot under the other layer the same way.
    lots["home_jurisdiction"] = lots["jurisdiction"]
    lots["home_zone_raw"] = lots["zone_raw"]
    lots["pocket_of"] = pd.Series([None] * len(lots), index=lots.index, dtype=object)
    keys = [(str(j), str(z)) if isinstance(z, str) else None
            for j, z in zip(lots["jurisdiction"], lots["zone_raw"])]
    rewrites = pocket_rewrites(sorted({k for k in keys if k is not None}), rules, layers)
    hit = np.array([k in rewrites for k in keys], dtype=bool)
    if hit.any():
        to = [rewrites[k] for k, h in zip(keys, hit) if h]
        lots["jurisdiction"] = lots["jurisdiction"].astype(object)
        lots["zone_raw"] = lots["zone_raw"].astype(object)
        lots.loc[hit, "jurisdiction"] = [t[0] for t in to]
        lots.loc[hit, "zone_raw"] = [t[1] for t in to]
        lots.loc[hit, "pocket_of"] = [t[2] for t in to]
    for (j, z), (oj, oz, _lid) in sorted(rewrites.items()):
        n = sum(1 for k in keys if k == (j, z))
        say(f"  pocket: {n:,} {j} lots mapped {z!r} measured under {oj} {oz!r}")

    # Ineligible jurisdictions with NO compiled zone rules can never be
    # re-enabled by a config toggle — drop. Ineligible ones WITH rules
    # (Lake Oswego) keep their geometry and are gated in s7.
    dead_juris = {
        k for k, j in rules.jurisdictions.items() if not j.eligible and not j.zones
    }
    drop(lots["jurisdiction"].isin(dead_juris), "jurisdiction_ineligible_no_rules")

    needs_ugb = {
        k for k, j in rules.jurisdictions.items() if j.require_inside_ugb
    }
    drop(lots["jurisdiction"].isin(needs_ugb) & ~lots["inside_ugb"].astype(bool), "outside_ugb")

    drop(lots["zone_raw"].isna(), "no_zone_assigned")

    # Rules lookup: zone in table? quadplex allowed (i.e. setbacks exist)?
    def _lookup(juris, zone_raw):
        rule = rules.jurisdictions[juris].rule_for(zone_raw)
        if rule is None:
            return "absent"
        return "allowed" if rule.quadplex_allowed else "not_allowed"

    verdict = np.array([_lookup(j, z) for j, z in zip(lots["jurisdiction"], lots["zone_raw"])], dtype=object)
    drop(verdict == "absent", "zone_not_in_rules")
    verdict = verdict[verdict != "absent"]
    drop(verdict == "not_allowed", "zone_quadplex_not_allowed")

    drop(lots["area_sqft"] < rules.defaults.sliver_min_lot_sqft, "sliver_area")

    shrunk = shapely.buffer(
        np.array(list(lots["geom"]), dtype=object), NARROW_TEST_BUFFER_FT
    )
    drop(np.array([g.is_empty for g in shrunk], dtype=bool), "too_narrow_20ft")

    # Normalized zone code for grouping in reports.
    lots["zone"] = [
        rules.jurisdictions[j].normalize_zone(z)
        for j, z in zip(lots["jurisdiction"], lots["zone_raw"])
    ]
    gone = (pd.concat(dropped, ignore_index=True) if dropped
            else pd.DataFrame({"TLID": [], "step": [], "reason": []}))
    return lots, funnel, gone


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    rules = load_rules()
    lots, funnel, gone = structural_filter(read_stage("s2_lots"), rules)
    print(f"s3: geometry universe {len(lots):,} lots "
          "(policy gates applied later in s7)")
    write_stage(lots, "s3_lots")
    (DATA_DIR / "funnel.json").write_text(json.dumps(funnel, indent=2), encoding="utf-8")
    gone.to_csv(DATA_DIR / "s3_dropped.csv", index=False)
    print(f"s3: wrote {len(gone):,} dropped lots by step to s3_dropped.csv")
    print("s3 done.")


if __name__ == "__main__":
    main()


