"""Flat rows for storage: one row per lot, plus per-wall-line and per-door child rows.

Shaped to be written to Parquet (or a table) later; this slice writes nothing.

* **Measured** (:func:`measured_rows` / :func:`from_measured_rows`): the MEASURE
  layer's record, enough to re-price without the ground. A wall line's station
  drops are one list column (``drops_in``), so every per-foot wall height can be
  re-derived. ``geometry`` is the JSON of the geometric settings measured under.
* **Assessed** (:func:`assessed_rows`): the PRICE layer's output for reading and
  cutting -- per method floor levels, walls, quantities before and after their
  factors, doors, cost low and high, flags, style, challenges and easy parts.
  Always re-derivable from the measured rows and a settings file.
"""

from __future__ import annotations

import json
from typing import Any

from flats.foundation.lot import LotResult
from flats.foundation.measure import GEOMETRIC, DoorMeasure, LineMeasure, Measured
from flats.foundation.model import MethodResult

_ORDER = {name: i for i, name in enumerate(GEOMETRIC)}
READING_COLUMNS = ("z_front_left", "z_front_mid", "z_front_right", "z_back_left", "z_back_mid", "z_back_right")
METHOD_KEYS = {"B": "b", "B+P": "bp", "A dry": "a_dry", "A wet": "a_wet"}


def _band_col(band: float) -> str:
    return f"fill_area_over_{band:g}in_sf"


def _geometry(m: Measured) -> dict[str, Any]:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in m.geometry}


# ---------------------------------------------------------------- measured


def measured_rows(m: Measured) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    geometry = _geometry(m)
    lot: dict[str, Any] = {
        "tlid": m.tlid,
        "county": m.county,
        "ground_source": m.ground_source,
        "cell_m": m.cell_m,
    }
    for col, i in zip(READING_COLUMNS, range(6)):
        lot[col] = m.readings[i] if m.readings is not None else None
    lot.update(
        relief_input_ft=m.relief_input_ft,
        relief_sampled_ft=m.relief_sampled_ft,
        lump_ft=m.lump_ft,
        fall_along_ft=m.fall_along_ft,
        fall_across_ft=m.fall_across_ft,
        high_z=m.high_z,
        low_z=m.low_z,
        low_drop_in=m.low_drop_in,
        fill_volume_ft3=m.fill_volume_ft3,
        fill_max_in=m.fill_max_in,
    )
    for band, area in zip(geometry["fill_bands_in"], m.fill_area_over_sf, strict=True):
        lot[_band_col(band)] = area
    lot.update(
        ground_class=m.ground_class,
        alt_ground_class=m.alt_ground_class,
        frost_register_in=m.frost_register_in,
        bldg_overlap_share=m.bldg_overlap_share,
        front_face_turn_deg=m.front_face_turn_deg,
        geometry=json.dumps(geometry, sort_keys=True),
    )
    lines = [
        {
            "tlid": m.tlid,
            "line": ln.name,
            "kind": ln.kind,
            "length_ft": ln.length_ft,
            "drop_max_in": ln.drop_max_in,
            "drop_min_in": ln.drop_min_in,
            "drop_mean_in": ln.drop_mean_in,
            "drop_area_ftin": ln.drop_area_ftin,
            "drops_in": list(ln.drops_in),
        }
        for ln in m.lines
    ]
    doors = [{"tlid": m.tlid, "face": d.face, "x_ft": d.x_ft, "drop_in": d.drop_in} for d in m.doors]
    return lot, lines, doors


def from_measured_rows(lot: dict[str, Any], lines: list[dict[str, Any]], doors: list[dict[str, Any]]) -> Measured:
    """The record back from its rows (nothing else is read)."""
    geometry = json.loads(lot["geometry"])
    readings = tuple(lot[c] for c in READING_COLUMNS)
    return Measured(
        tlid=lot["tlid"],
        county=lot["county"],
        ground_source=lot["ground_source"],
        cell_m=lot["cell_m"],
        readings=None if any(v is None for v in readings) else readings,
        relief_input_ft=lot["relief_input_ft"],
        relief_sampled_ft=lot["relief_sampled_ft"],
        lump_ft=lot["lump_ft"],
        fall_along_ft=lot["fall_along_ft"],
        fall_across_ft=lot["fall_across_ft"],
        high_z=lot["high_z"],
        low_z=lot["low_z"],
        low_drop_in=lot["low_drop_in"],
        lines=tuple(
            LineMeasure(
                name=r["line"],
                kind=r["kind"],
                length_ft=r["length_ft"],
                drops_in=tuple(r["drops_in"]),
                drop_max_in=r["drop_max_in"],
                drop_min_in=r["drop_min_in"],
                drop_mean_in=r["drop_mean_in"],
                drop_area_ftin=r["drop_area_ftin"],
            )
            for r in lines
        ),
        doors=tuple(DoorMeasure(r["face"], r["x_ft"], r["drop_in"]) for r in doors),
        fill_volume_ft3=lot["fill_volume_ft3"],
        fill_max_in=lot["fill_max_in"],
        fill_area_over_sf=tuple(lot[_band_col(b)] for b in geometry["fill_bands_in"]),
        ground_class=lot["ground_class"],
        alt_ground_class=lot["alt_ground_class"],
        frost_register_in=lot["frost_register_in"],
        bldg_overlap_share=lot["bldg_overlap_share"],
        front_face_turn_deg=lot["front_face_turn_deg"],
        geometry=tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in sorted(geometry.items(), key=lambda kv: _ORDER[kv[0]])),
    )


# ---------------------------------------------------------------- assessed


def _method_cols(key: str, r: MethodResult) -> dict[str, Any]:
    return {
        f"{key}_floor_above_high_in": r.floor_above_high_in,
        f"{key}_floor_above_low_in": r.floor_above_low_in,
        f"{key}_tallest_wall_in": r.tallest_wall_in,
        f"{key}_average_wall_in": r.average_wall_in,
        f"{key}_showing_max_in": r.showing_max_in,
        f"{key}_concrete_net_yd3": r.concrete_net_yd3,
        f"{key}_concrete_waste": r.concrete_waste,
        f"{key}_concrete_yd3": r.concrete_yd3,
        f"{key}_level_bar_ft_net": r.level_bar_ft_net,
        f"{key}_lap": r.lap,
        f"{key}_upright_bar_ft": r.upright_bar_ft,
        f"{key}_bar_lb_per_ft": r.bar_lb_per_ft,
        f"{key}_bars_lb": r.bars_lb,
        f"{key}_form_sf": r.form_sf,
        f"{key}_fill_ton": r.fill_ton,
        f"{key}_fill_max_in": r.fill_max_in,
        f"{key}_piles": r.piles,
        f"{key}_risers_total": r.risers_total,
        f"{key}_risers_least": r.risers_least,
        f"{key}_risers_most": r.risers_most,
        f"{key}_longest_stair_in": r.longest_stair_in,
        f"{key}_guards": r.guards,
        f"{key}_rail_ft": r.rail_ft,
        f"{key}_cost_low": str(r.cost.low),
        f"{key}_cost_high": str(r.cost.high),
        f"{key}_flags": ";".join(r.flags),
    }


def assessed_rows(res: LotResult) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    lot: dict[str, Any] = {
        "tlid": res.tlid,
        "group": res.group,
        "applicable": ";".join(res.applicable),
        "embed_in_used": res.embed_in_used,
        "flags": ";".join(res.flags),
        "style_standard": ";".join(res.style.standard),
        "style_cheaper_low": res.style.cheaper_low,
        "style_cheaper_high": res.style.cheaper_high,
        "style_words": res.style.words,
        "challenges": ";".join(f"{i.code}:{i.method}" if i.method else i.code for i in res.challenges),
        "easy": ";".join(f"{i.code}:{i.method}" if i.method else i.code for i in res.easy),
    }
    for c in res.cheaper:
        key = f"cheaper_vs_{METHOD_KEYS[c.against]}_{c.prices}"
        lot[key] = c.cheaper
        lot[f"{key}_by"] = str(c.by)
    lines, doors = [], []
    for name, r in res.methods.items():
        key = METHOD_KEYS[name]
        lot.update(_method_cols(key, r))
        for ln in r.lines:
            row = {
                "tlid": res.tlid,
                "method": name,
                "line": ln.name,
                "kind": ln.kind,
                "length_ft": ln.length_ft,
                "tallest_in": ln.tallest_in,
                "shortest_in": ln.shortest_in,
                "average_in": ln.average_in,
                "showing_max_in": ln.showing_max_in,
                "showing_avg_in": ln.showing_avg_in,
                "thickness_in": ln.thickness_in,
                "level_bars": ln.level_bars,
                "over_standard": ln.over_standard,
                "steepest_slope": ln.steepest_slope,
                "footing_steps": ln.footing_steps,
            }
            for i, length in enumerate(ln.band_length_ft):
                row[f"band_{i}_ft"] = length
            lines.append(row)
        for d in r.doors:
            doors.append(
                {
                    "tlid": res.tlid,
                    "method": name,
                    "face": d.face,
                    "x_ft": d.x_ft,
                    "height_in": d.height_in,
                    "risers": d.risers,
                    "stair_run_in": d.stair_run_in,
                    "guard": d.guard,
                    "handrail": d.handrail,
                    "rail_ft": d.rail_ft,
                }
            )
    return lot, lines, doors
