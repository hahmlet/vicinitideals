"""
Quadfit — shared plumbing for the quadplex-buildability pipeline.

Standalone statistical analysis: for every Multnomah County tax lot whose zone
allows a quadplex by-right (HB 2001 / OAR 660-046), test whether candidate
footprint rectangles fit inside the lot's setback envelope. No app imports, no
DB — file-based stages under data/quadfit/. See README.md for the stage graph.

This module holds paths, CRS constants, config schemas/loaders, and Parquet+WKB
IO helpers shared by the s* stage scripts. Config-only consumers (tests, the
rules compiler) must be able to import it without the `gis` extra installed, so
shapely/pyproj/pyarrow imports are deferred into the functions that need them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parents[1]
CONFIG_DIR = TOOL_DIR / "config"
GIS_CACHE_DIR = REPO_ROOT / "data" / "gis_cache" / "oregon"
DATA_DIR = REPO_ROOT / "data" / "quadfit"

# RLIS native CRS: NAD83(HARN) / Oregon North, international feet. All pipeline
# geometry works in this CRS so setbacks/footprints are in feet with no
# reprojection of the 400K+ taxlot polygons. Only WGS84 zoning layers from
# cache_layers.py get reprojected on load.
CRS_WORKING = "EPSG:2913"
CRS_WGS84 = "EPSG:4326"


# ---------------------------------------------------------------------------
# Config schemas
# ---------------------------------------------------------------------------

Confidence = Literal["verified", "needs_verification"]

OrientationConstraint = Literal["none", "entrance_only", "axis_required"]


class ZoneRule(BaseModel):
    zone: str
    quadplex_allowed: bool
    setback_front_ft: float | None = None
    setback_side_ft: float | None = None
    setback_rear_ft: float | None = None
    # Corner-lot street-side setback when it exceeds the interior side setback
    # (e.g. Gresham MDR 20 ft vs 10 ft interior). Applied to ALL street edges of
    # tier-B lots via max(front, street_side) — conservative, since the true
    # front edge legally takes only the front setback.
    setback_street_side_ft: float | None = None
    # Minimum lot area for a quadplex where the code sets one (e.g. Portland
    # Table 110-7). Lots below this drop in the s3 funnel.
    min_lot_sqft: float | None = None
    # Minimum street frontage for residential use where the code sets one
    # (e.g. Gresham CMF 100 ft). Gates fits in s6 (frontage known after s4).
    min_frontage_ft: float | None = None
    max_coverage_pct: float | None = None  # building coverage cap, % of lot area
    # Piecewise coverage formula rows [lot_area_break_sqft, base_sqft,
    # marginal_pct_over_break] — e.g. Portland Table 110-5. Overrides
    # max_coverage_pct when present.
    coverage_curve: list[list[float]] | None = None
    accessory_allowance_sqft: float = 0  # reserved coverage for garage/shed assumption
    # Per-zone override of the jurisdiction orientation_constraint (e.g.
    # Gresham design districts force the long axis parallel to the street).
    orientation_constraint: OrientationConstraint | None = None
    source: str = ""
    source_url: str = ""
    confidence: Confidence = "needs_verification"
    notes: str = ""

    @model_validator(mode="after")
    def _validate(self) -> ZoneRule:
        if self.quadplex_allowed:
            missing = [
                n
                for n in ("setback_front_ft", "setback_side_ft", "setback_rear_ft")
                if getattr(self, n) is None
            ]
            if missing:
                raise ValueError(
                    f"zone {self.zone}: quadplex_allowed=true requires {missing}"
                )
        if self.coverage_curve:
            breaks = [row[0] for row in self.coverage_curve]
            if any(len(row) != 3 for row in self.coverage_curve):
                raise ValueError(f"zone {self.zone}: coverage_curve rows need 3 values")
            if breaks != sorted(breaks):
                raise ValueError(f"zone {self.zone}: coverage_curve breaks must ascend")
        return self

    def coverage_cap_sqft(self, lot_area_sqft: float) -> float | None:
        """Max combined building coverage for a lot, or None if uncapped."""
        if self.coverage_curve:
            cap: float | None = None
            for brk, base, marginal in self.coverage_curve:
                if lot_area_sqft >= brk:
                    cap = base + marginal / 100.0 * (lot_area_sqft - brk)
            return cap
        if self.max_coverage_pct is not None:
            return self.max_coverage_pct / 100.0 * lot_area_sqft
        return None


class JurisdictionRules(BaseModel):
    eligible: bool
    reason: str = ""
    # Literal values of the RLIS JURIS_CITY field that map to this jurisdiction.
    juris_city_codes: list[str] = Field(default_factory=list)
    # Slug of the cached zoning layer (data/gis_cache/oregon/<slug>.geojson).
    zoning_layer: str | None = None
    zone_field: str | None = None
    zone_aliases: dict[str, str] = Field(default_factory=dict)
    # Portland writes overlay letters into the zone code (R5a, R2.5h...):
    # strip trailing lowercase letters before rule lookup.
    strip_lowercase_suffix: bool = False
    require_inside_ugb: bool = False
    # Middle-housing orientation rules bind the entrance/facade, not the long
    # axis, everywhere verified so far; axis_required restricts fit testing to
    # width-facing placements only.
    orientation_constraint: OrientationConstraint = "entrance_only"
    zones: list[ZoneRule] = Field(default_factory=list)

    def normalize_zone(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        code = str(raw).strip()
        if not code:
            return None
        if code in self.zone_aliases:
            return self.zone_aliases[code]
        if self.strip_lowercase_suffix:
            stripped = code.rstrip("abcdefghijklmnopqrstuvwxyz")
            if stripped and stripped in {z.zone for z in self.zones}:
                return stripped
            if stripped in self.zone_aliases:
                return self.zone_aliases[stripped]
            if stripped:
                return stripped
        return code

    def rule_for(self, raw_zone: str | None) -> ZoneRule | None:
        code = self.normalize_zone(raw_zone)
        if code is None:
            return None
        for rule in self.zones:
            if rule.zone == code:
                return rule
        return None


class Defaults(BaseModel):
    # Max distance from a lot edge midpoint to a street centerline for the edge
    # to count as frontage (~ROW half-width + margin).
    street_threshold_ft: float = 50.0
    sliver_min_lot_sqft: float = 1000.0
    grid_resolution_ft: float = 0.5
    simplify_tolerance_ft: float = 1.5


class RulesConfig(BaseModel):
    meta: dict[str, Any] = Field(default_factory=dict)
    defaults: Defaults = Field(default_factory=Defaults)
    jurisdictions: dict[str, JurisdictionRules]

    def jurisdiction_for_juris_city(self, juris_city: str | None) -> str | None:
        """Map an RLIS JURIS_CITY literal to a jurisdiction key."""
        code = (juris_city or "").strip().upper()
        for key, j in self.jurisdictions.items():
            if code in {c.upper() for c in j.juris_city_codes}:
                return key
        return None


class Footprint(BaseModel):
    name: str
    width_ft: float  # dimension parallel to the front lot line (before flip)
    depth_ft: float

    @model_validator(mode="after")
    def _positive(self) -> Footprint:
        if self.width_ft <= 0 or self.depth_ft <= 0:
            raise ValueError(f"footprint {self.name}: dimensions must be positive")
        return self


class ConstantAreaSweep(BaseModel):
    """Sweep aspect ratios at fixed footprint area (identical floor plates)."""

    area_sqft: float
    width_min_ft: float
    width_max_ft: float
    step_ft: float = 0.5

    def widths(self) -> list[float]:
        out: list[float] = []
        w = self.width_min_ft
        # Float-safe inclusive range in step_ft increments.
        n = 0
        while True:
            w = self.width_min_ft + n * self.step_ft
            if w > self.width_max_ft + 1e-9:
                break
            out.append(round(w, 4))
            n += 1
        return out


class FrontierSpec(BaseModel):
    """Width grid for the per-lot max-depth frontier."""

    width_min_ft: float = 12.0
    width_max_ft: float = 60.0
    step_ft: float = 0.5

    def widths(self) -> list[float]:
        out: list[float] = []
        n = 0
        while True:
            w = self.width_min_ft + n * self.step_ft
            if w > self.width_max_ft + 1e-9:
                break
            out.append(round(w, 4))
            n += 1
        return out


class FootprintsConfig(BaseModel):
    orientations: list[Literal["width_facing", "depth_facing"]] = Field(
        default_factory=lambda: ["width_facing", "depth_facing"]
    )
    footprints: list[Footprint]
    constant_area_sweeps: list[ConstantAreaSweep] = Field(default_factory=list)
    frontier: FrontierSpec = Field(default_factory=FrontierSpec)


def load_rules(path: Path | None = None) -> RulesConfig:
    import yaml

    raw = yaml.safe_load((path or CONFIG_DIR / "rules.yaml").read_text(encoding="utf-8"))
    return RulesConfig.model_validate(raw)


def load_footprints(path: Path | None = None) -> FootprintsConfig:
    import yaml

    raw = yaml.safe_load(
        (path or CONFIG_DIR / "footprints.yaml").read_text(encoding="utf-8")
    )
    return FootprintsConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Geometry + IO helpers (require the `gis` extra)
# ---------------------------------------------------------------------------


def load_geojson_features(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("type") == "FeatureCollection":
        return doc.get("features", [])
    raise ValueError(f"{path}: not a FeatureCollection")


def features_to_geoms(features: list[dict[str, Any]]) -> list[Any]:
    """GeoJSON features → shapely geometries (None-safe)."""
    from shapely.geometry import shape

    geoms: list[Any] = []
    for feat in features:
        geom = feat.get("geometry")
        geoms.append(shape(geom) if geom else None)
    return geoms


def reproject_4326_to_2913(geoms: list[Any]) -> list[Any]:
    import shapely
    from pyproj import Transformer

    tr = Transformer.from_crs(CRS_WGS84, CRS_WORKING, always_xy=True)

    def _fn(coords):
        x, y = tr.transform(coords[:, 0], coords[:, 1])
        import numpy as np

        return np.column_stack([x, y])

    return [None if g is None else shapely.transform(g, _fn) for g in geoms]


def stage_path(name: str) -> Path:
    return DATA_DIR / f"{name}.parquet"


def write_stage(df: Any, name: str) -> Path:
    """Write a stage DataFrame (with optional shapely 'geom' column) to Parquet.

    A 'geom' column of shapely geometries is serialized to WKB bytes as 'wkb';
    all other columns pass through.
    """
    import shapely

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    if "geom" in out.columns:
        out["wkb"] = [None if g is None else shapely.to_wkb(g) for g in out["geom"]]
        out = out.drop(columns=["geom"])
    path = stage_path(name)
    out.to_parquet(path, index=False)
    return path


def read_stage(name: str) -> Any:
    """Read a stage Parquet; a 'wkb' column is rehydrated to shapely 'geom'."""
    import pandas as pd
    import shapely

    df = pd.read_parquet(stage_path(name))
    if "wkb" in df.columns:
        df["geom"] = [None if b is None else shapely.from_wkb(b) for b in df["wkb"]]
        df = df.drop(columns=["wkb"])
    return df
