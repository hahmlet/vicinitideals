"""Two Portland map overlays the zoning letters on a lot do not carry
(FOLLOWUPS 78, found by the 2026-10-14 sample).

**The Centers Main Street overlay ("m", PCC 33.415).** 33.415.310 sets a
minimum floor area ratio on "all new development": 0.5 to 1 in the Inner
Pattern Area, 0.25 to 1 in the Eastern and Western Pattern Areas (Map 415-1).
The pod's floor area is fixed (4,032 sf for the 56 x 36 pod, two storeys), so
past 8,064 sf of lot in the Inner area, or 16,128 sf in the Eastern and
Western, the pod is too little building and the lot is RED. The code names no
minimum for the River and Central City pattern areas, and states none: silence
is none. A lot no pattern area answers takes the Inner 0.5, the worst case.

**Protected historic resources (PCC 33.445).** Steph ruled 2026-10-14: a lot
carrying a protected historic building is RED -- a Historic, Conservation or
National Register Landmark, or a contributing resource in a Historic or
Conservation District. Demolishing any of them needs demolition review
(33.445.100.E, 110.E, 120.E, 200.E, 210.E), a hearing nobody can count on.
Every other existing building stays green (a separate ruling). A contributing
resource in a National Register District (Eastmoreland) is held to the same
demolition review by 33.445.220.E, but the ruling named Historic and
Conservation Districts only: it is recorded on the row and NOT read as red
until Steph rules (``NR_DISTRICT_RED``).

What is read per lot, off the acquire snapshot (``flats/config/pipeline.yaml``):

* :data:`MAIN_STREET_KEY` -- the zoning polygons whose ``OVRLY`` letters hold
  an ``m`` token. The lot is in the overlay where at least
  :data:`MAIN_STREET_SHARE` of it is: a thinner edge is the city's zoning
  polygons and the county's taxlots disagreeing, the same 10 % the split-zone
  reading takes as map noise.
* :data:`PATTERN_KEY` -- Map 415-1's pattern areas, every one holding at least
  :data:`PATTERN_SHARE` of the lot; the strictest minimum among them governs.
* :data:`RESOURCE_KEY` -- the city's district status layer, one polygon per
  resource drawn on the city's taxlots, and :data:`LANDMARK_KEY` -- the
  landmark building footprints. A resource is on the lot where their overlap
  is at least :data:`RESOURCE_SHARE` of the smaller of the two: a footprint
  standing on the lot, or a resource polygon that is the lot, but never a
  neighbour's edge.

The reading rides on the bridge row as :data:`ROW_KEY` (JSON) and on the lot
as ``QuadfitLot.pdx_overlays``; :func:`checked` turns it into binds.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flats.score import flags as flag_plan

MAIN_STREET_KEY = "overlay_pdx_main_street"
PATTERN_KEY = "pdx_pattern_areas"
RESOURCE_KEY = "pdx_historic_resources"
LANDMARK_KEY = "pdx_landmark_footprints"
KEYS: tuple[str, ...] = (MAIN_STREET_KEY, PATTERN_KEY, RESOURCE_KEY, LANDMARK_KEY)

#: The bridge jurisdictions Portland's zoning map answers: the city and the
#: unincorporated pockets it administers under Title 33 (as ``Z_ANSWERS``).
ANSWERS: frozenset[str] = frozenset({"portland", "multnomah_unincorporated"})

#: The row key the reading rides on.
ROW_KEY = "pdx_overlays_json"

MAIN_STREET_SHARE = 0.10
PATTERN_SHARE = 0.01
RESOURCE_SHARE = 0.5

#: 33.415.310, by Map 415-1's label. River and Central City are absent: the
#: section names no minimum there.
MIN_FAR: Mapping[str, float] = {"Inner": 0.5, "Eastern": 0.25, "Western": 0.25}
#: Where no pattern area answers the lot: the strictest stated.
MIN_FAR_UNMEASURED = 0.5

#: Status values (``Status``, the overriding one) of a protected resource.
PROTECTED_STATUS: frozenset[str] = frozenset(
    {"contributing", "historic landmark", "conservation landmark", "national register landmark"}
)
_LANDMARKS = frozenset({"historic landmark", "conservation landmark", "national register landmark"})

#: Whether a contributing resource in a National Register District reds the
#: lot. 33.445.220.E puts it under demolition review like the others; Steph's
#: 2026-10-14 ruling named Historic and Conservation Districts only.
NR_DISTRICT_RED = False

#: Screen reasons (said in words in ``app/api/routers/ui_flats.py``).
MIN_FAR_REASON = "PDX_MAIN_STREET_MIN_FAR"
PROTECTED_RESOURCE_REASON = "PDX_PROTECTED_RESOURCE"
REASONS: tuple[str, ...] = (MIN_FAR_REASON, PROTECTED_RESOURCE_REASON)
#: The binds' check names.
MIN_FAR_CHECK = "pdx_min_far"
PROTECTED_RESOURCE_CHECK = "pdx_protected_resource"

#: Where the code says so, each with the stored lines that say it
#: (``flats/provenance/docs``; ``flats/tests/test_pdx_overlays.py`` holds the
#: quotes to them).
CITES: Mapping[str, tuple[str, str, str]] = {
    "min_far_inner": (
        "PCC 33.415.310.A",
        "or/multnomah/portland/33.415.txt#L79-L81",
        "In the Inner Pattern Area the minimum floor area ratio (FAR) for all new development is 0.5",
    ),
    "min_far_outer": (
        "PCC 33.415.310.B",
        "or/multnomah/portland/33.415.txt#L82-L83",
        "In the Eastern and Western Pattern Area the minimum floor area ratio (FAR) for all new",
    ),
    "historic_district": (
        "PCC 33.445.200.E.1",
        "or/multnomah/portland/33.445.txt#L1184-L1185",
        "of a contributing resource in a Historic District is subject to demolition review",
    ),
    "conservation_district": (
        "PCC 33.445.210.E.1",
        "or/multnomah/portland/33.445.txt#L1593-L1594",
        "of a contributing resource in a Conservation District is subject to demolition review",
    ),
    "nr_district": (
        "PCC 33.445.220.E.1",
        "or/multnomah/portland/33.445.txt#L1697-L1699",
        "of a contributing resource in a National Register District is subject to demolition",
    ),
    "historic landmark": (
        "PCC 33.445.100.E.1",
        "or/multnomah/portland/33.445.txt#L360-L362",
        "of a Historic Landmark and demolition of a contributing resource is subject to",
    ),
    "conservation landmark": (
        "PCC 33.445.110.E.1",
        "or/multnomah/portland/33.445.txt#L654-L656",
        "of a Conservation Landmark and demolition of a contributing resource is subject to",
    ),
    "national register landmark": (
        "PCC 33.445.120.E.1",
        "or/multnomah/portland/33.445.txt#L754-L756",
        "of a National Register Landmark and demolition of a contributing resource is subject",
    ),
}


@dataclass(frozen=True, slots=True)
class Reading:
    """What the Portland overlays say about one lot."""

    #: At least :data:`MAIN_STREET_SHARE` of the lot is in the "m" overlay.
    main_street: bool = False
    #: Map 415-1's labels holding the lot, largest share first.
    pattern_areas: tuple[str, ...] = ()
    #: Protected resources on the lot, each said in a line.
    protected: tuple[str, ...] = ()
    #: Contributing resources in a National Register District (held, not red).
    nr_district: tuple[str, ...] = ()

    @property
    def min_far(self) -> float | None:
        """33.415.310's minimum FAR for the lot, or None where none applies."""
        if not self.main_street:
            return None
        if not self.pattern_areas:
            return MIN_FAR_UNMEASURED
        stated = [MIN_FAR[p] for p in self.pattern_areas if p in MIN_FAR]
        return max(stated) if stated else None

    @property
    def red_resources(self) -> tuple[str, ...]:
        return self.protected + (self.nr_district if NR_DISTRICT_RED else ())


def encode(r: Reading) -> str:
    return json.dumps(
        {
            "pdx_main_street_overlay": r.main_street,
            "pdx_pattern_area": list(r.pattern_areas),
            "pdx_protected_resource": list(r.protected),
            "pdx_nr_district_resource": list(r.nr_district),
        },
        separators=(",", ":"),
    )


def decode(raw: str | None) -> Reading | None:
    """The reading a row carries; None where nothing read the lot."""
    if not raw:
        return None
    doc = json.loads(raw)
    return Reading(
        main_street=bool(doc.get("pdx_main_street_overlay")),
        pattern_areas=tuple(doc.get("pdx_pattern_area") or ()),
        protected=tuple(doc.get("pdx_protected_resource") or ()),
        nr_district=tuple(doc.get("pdx_nr_district_resource") or ()),
    )


# --- the maps ----------------------------------------------------------------


@dataclass(frozen=True)
class Maps:
    """The four layers, each with its spatial index."""

    main_street: tuple[Any, ...]
    patterns: tuple[tuple[Any, str], ...]
    #: (geometry, words, kind) -- kind ``protected``, ``nr`` or ``none``.
    resources: tuple[tuple[Any, str, str], ...]
    trees: dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def build(
        cls,
        main_street: Sequence[Any],
        patterns: Sequence[tuple[Any, str]],
        resources: Sequence[tuple[Any, str, str]],
    ) -> Maps:
        from shapely.strtree import STRtree

        out = cls(tuple(main_street), tuple(patterns), tuple(resources))
        out.trees["m"] = STRtree(list(out.main_street))
        out.trees["p"] = STRtree([g for g, _ in out.patterns])
        out.trees["r"] = STRtree([g for g, _, _ in out.resources])
        return out


def _manifest(sources: Path) -> dict[str, Any]:
    path = sources / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _dataset_path(sources: Path, manifest: Mapping[str, Any], key: str) -> Path:
    entry = (manifest.get("datasets") or {}).get(key) or {}
    return sources / str(entry.get("file") or f"{key}.geojson")


def missing(sources: Path | None) -> tuple[str, ...]:
    """The layers an acquire snapshot lacks -- every one where there is no
    snapshot. Without them a lot in the overlay or holding a landmark would
    pass GREEN unread, so the bridge refuses a run missing one."""
    if sources is None:
        return KEYS
    manifest = _manifest(sources)
    return tuple(k for k in KEYS if not _dataset_path(sources, manifest, k).is_file())


def has_m(ovrly: object) -> bool:
    """Whether a zoning polygon's overlay letters (``"d,m"``) hold ``m``."""
    return "m" in {t.strip() for t in str(ovrly or "").split(",")}


def _district_kind(name: str) -> str:
    """A district's kind from its name: ``nr``, else ``protected``. The
    layer spells some names short ("...HISTORI*", "...DISTRICTC"); any name
    that is not a National Register District is read as protected."""
    return "nr" if "NATIONAL REGISTER" in name.upper() else "protected"


def resource_words(props: Mapping[str, Any]) -> tuple[str, str]:
    """A district status record said in a line, and its kind: ``protected``,
    ``nr`` (a contributing resource in a National Register District) or
    ``none`` (non-contributing, removed, or no status)."""
    status = str(props.get("Status") or "").strip()
    low = status.lower()
    district = str(props.get("DistName") or "").strip().rstrip("*")
    where = f" in {district.title()}" if district else ""
    built = f", built {props['YearBuilt']}" if props.get("YearBuilt") else ""
    address = str(props.get("Address") or "").strip()
    said = "contributing resource" if low == "contributing" else low
    words = f"{said}{where} ({address}{built})" if address else f"{said}{where}"
    if low not in PROTECTED_STATUS:
        return words, "none"
    if low in _LANDMARKS:
        return words, "protected"
    return words, _district_kind(district)


def landmark_words(props: Mapping[str, Any]) -> str:
    kind = str(props.get("designation_new") or props.get("TYPE") or "landmark").strip().lower()
    name = str(props.get("HISTNAME") or "").strip()
    address = str(props.get("ADDRESS") or "").strip()
    bits = ", ".join(b for b in (name, address) if b)
    return f"{kind} ({bits})" if bits else kind


def load(sources: Path) -> Maps | None:
    """The four layers an acquire snapshot holds; None where it lacks any."""
    from shapely.geometry import shape

    from flats.ingest.delta import iter_features

    if missing(sources):
        return None
    manifest = _manifest(sources)

    def feats(key: str) -> Iterable[tuple[Any, Mapping[str, Any]]]:
        for f in iter_features(_dataset_path(sources, manifest, key)):
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            yield (g if g.is_valid else g.buffer(0)), (f.get("properties") or {})

    main = [g for g, p in feats(MAIN_STREET_KEY) if has_m(p.get("OVRLY"))]
    patterns = [(g, str(p.get("MapLabel") or "").strip()) for g, p in feats(PATTERN_KEY)]
    resources: list[tuple[Any, str, str]] = []
    for g, p in feats(RESOURCE_KEY):
        words, kind = resource_words(p)
        if kind != "none":
            resources.append((g, words, kind))
    resources.extend((g, landmark_words(p), "protected") for g, p in feats(LANDMARK_KEY))
    return Maps.build(main, patterns, resources)


def read(lot: Any, maps: Maps) -> Reading | None:
    """The reading for one taxlot polygon (EPSG:2913); None without a shape."""
    if lot is None or lot.is_empty or lot.area <= 0:
        return None
    lot = lot if lot.is_valid else lot.buffer(0)
    area = lot.area

    inside = sum(lot.intersection(maps.main_street[i]).area for i in maps.trees["m"].query(lot))
    shares: dict[str, float] = {}
    for i in maps.trees["p"].query(lot):
        g, label = maps.patterns[int(i)]
        shares[label] = shares.get(label, 0.0) + lot.intersection(g).area / area
    patterns = tuple(k for k, v in sorted(shares.items(), key=lambda kv: -kv[1]) if v >= PATTERN_SHARE)

    protected: list[str] = []
    nr: list[str] = []
    for i in maps.trees["r"].query(lot):
        g, words, kind = maps.resources[int(i)]
        if g.area <= 0:
            continue
        if lot.intersection(g).area < RESOURCE_SHARE * min(area, g.area):
            continue
        target = protected if kind == "protected" else nr
        if words not in target:
            target.append(words)
    return Reading(
        main_street=inside / area >= MAIN_STREET_SHARE,
        pattern_areas=patterns,
        protected=tuple(protected),
        nr_district=tuple(nr),
    )


def with_overlays(rows: Iterable[dict[str, Any]], sources: Path | None) -> int:
    """Join :data:`ROW_KEY` onto every Portland row (:data:`ANSWERS`) with a
    shape, in place; say how many carry something (the overlay or a
    resource). Nothing without a snapshot holding the layers."""
    import shapely

    if sources is None:
        return 0
    maps = load(sources)
    if maps is None:
        return 0
    marked = 0
    for row in rows:
        if row.get("jurisdiction") not in ANSWERS or not row.get("lot_wkb"):
            continue
        got = read(shapely.from_wkb(row["lot_wkb"]), maps)
        if got is None:
            continue
        row[ROW_KEY] = encode(got)
        marked += bool(got.main_street or got.protected or got.nr_district)
    return marked


# --- the check ---------------------------------------------------------------


def binds_for(reading: Reading | None, floor_sqft: float, lot_sqft: float) -> tuple[flag_plan.Bind, ...]:
    """The binds the reading puts on one design: a protected resource, and a
    floor area under the overlay's minimum."""
    if reading is None:
        return ()
    out: list[flag_plan.Bind] = []
    for words in reading.red_resources:
        kind = next((k for k in _LANDMARKS if words.startswith(k)), None)
        if kind is not None:
            cite = CITES[kind][0]
        elif "conservation district" in words.lower():
            cite = CITES["conservation_district"][0]
        elif "national register district" in words.lower():
            cite = CITES["nr_district"][0]
        else:
            cite = CITES["historic_district"][0]
        out.append(
            flag_plan.Bind(
                PROTECTED_RESOURCE_CHECK,
                None,
                None,
                None,
                source=f"{cite}: demolition review -- {words} (Steph 2026-10-14: a protected building is red)",
            )
        )
    need = reading.min_far
    if need is not None and lot_sqft > 0:
        far = floor_sqft / lot_sqft
        if far < need - 1e-9:
            inner = need >= MIN_FAR["Inner"]
            cite = CITES["min_far_inner" if inner else "min_far_outer"][0]
            area = ", ".join(reading.pattern_areas) or "no pattern area mapped, taken as Inner"
            out.append(
                flag_plan.Bind(
                    MIN_FAR_CHECK,
                    round(far, 4),
                    need,
                    round(need - far, 4),
                    source=f"{cite}: Centers Main Street overlay ({area} pattern area), "
                    f"{floor_sqft:,.0f} sf of floor on {lot_sqft:,.0f} sf of lot",
                )
            )
    return tuple(out)


def checked(s: Any, reading: Reading | None) -> Any:
    """``s`` (a bridge ``Screened``) RED where the reading binds its design:
    a bind each, the reason beside it, as screened and as signed. Adds
    nothing twice, so a screen that runs again over its own answer is
    unchanged."""
    if reading is None:
        return s
    binds = binds_for(reading, s.design.ground_sqft * s.design.stories, s.lot.facts.lot_sqft)
    if not binds:
        return s
    from flats.score.screen import Triage

    def red(x: Any) -> Any:
        have = {(b.check, b.source) for b in x.binds}
        new = tuple(b for b in binds if (b.check, b.source) not in have)
        if not new:
            return x
        reasons = list(x.reasons)
        for b in new:
            why = MIN_FAR_REASON if b.check == MIN_FAR_CHECK else PROTECTED_RESOURCE_REASON
            if why not in reasons:
                reasons.append(why)
        return dataclasses.replace(x, triage=Triage.red, binds=(*x.binds, *new), reasons=tuple(reasons))

    return dataclasses.replace(s, screening=red(s.screening), signed=red(s.signed))


__all__ = [
    "ANSWERS",
    "CITES",
    "KEYS",
    "MIN_FAR_CHECK",
    "MIN_FAR_REASON",
    "PROTECTED_RESOURCE_CHECK",
    "PROTECTED_RESOURCE_REASON",
    "REASONS",
    "ROW_KEY",
    "Maps",
    "Reading",
    "binds_for",
    "checked",
    "decode",
    "encode",
    "has_m",
    "load",
    "missing",
    "read",
    "with_overlays",
]
