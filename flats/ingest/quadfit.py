"""The county map as quadfit measured it, read into the screen's inputs.

:func:`flats.score.screen.screen` had no production caller until 2026-09-17.
The gap was never code: ``flats.lots``, ``flats.runs`` and
``flats.lot_results`` were all empty, because the acquire / normalize /
assign ingest in ``flats/config/pipeline.yaml`` names its sources and
nothing downloads them. Asked which way to fill it, Steph ruled: *"bridge
from the county map for now, but we will need an authoritative offline
source."* This module is the bridge. The offline source is FOLLOWUPS item 2
and replaces this module when it is built; nothing here should be read as
the product's data layer.

**What it reads.** quadfit's stage files, where s4 and s5o leave them
(``data/quadfit/``): the lot's area, frontage, width and depth; its edges
with their classes and the clustered street directions; whether its front
is on a cul-de-sac bulb; the carved buildable envelope; the FEMA flood
columns; the sanitary-main distance and the Clackamas district flag. The
same files :mod:`flats.geom.alley` and :mod:`flats.geom.culdesac` already
read one fact each from. quadfit's own verdict (``lots_results.csv``) is
read only by :func:`compare`, to sit beside FLATS's, never to inform it.

**What it hands the screen.** One :class:`~flats.score.screen.LotFacts`
per lot; the site facts quadfit measured *with the registry's meaning* --
see :func:`observed_facts`, which names each one and refuses the rest; a
:class:`~flats.rules.resolver.ZoneResolution` from the corpus under
:func:`~flats.score.configure.configure`; and a
:class:`~flats.fit.rectangle.Fit` searched by :func:`~flats.score.screen.fit_for`
at the width the zone's parking asks. The envelope is FLATS's own
(:func:`envelope_for`): the taxlot cut at the setbacks the corpus resolved
for that lot and design -- the variant a commercial neighbour, an alley or
a corner fired -- less the ground s5o's carve overlays took. quadfit's
carved envelope is used only where FLATS cannot cut one (no taxlot, no
street, a yard with no number, an exempt rear on a lot whose rear line is
not all alley), and each row says which (``envelope_source``).

**What the verdict is today.** Every value in the corpus is ``draft`` --
no ``flats/config/verifications.jsonl`` exists -- so the screen answers
UNKNOWN / ``RULE_UNVERIFIED`` on every lot whose zone it holds. That is the
Phase 0 exit state the plan asked for ("everything in REVIEW pending
verification"), and it is reported as the verdict. Beside it,
:attr:`Screened.signed` is the same checks with the one ``unverified``
reason lifted and nothing else changed: what the lot would be once the
numbers are signed. Its colour is the ``if_signed`` column of every output
and the one the comparison against quadfit reads, because a table of
289,845 UNKNOWNs measures nothing.

**What it does not see.** Slope, held on the registry's assumption
(``steep_slope`` False) although quadfit carries a DEM percentile and
Gresham's hillside overlay: the condition is "steep enough to trigger a
hillside overlay", a per-city threshold nothing here holds, and the
assumption is named on every lot where a standard turns on it. Flag lots
the same way. The lots quadfit excluded before it fit anything (condos,
stacked parcels, non-residential zones) are screened here like any other;
the comparison shows them as quadfit RED against whatever FLATS found.
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flats.designs.model import Design
from flats.encode.port_quadfit import COUNTY, layer_id_for
from flats.fit.angles import DEFAULT_STEP_DEG, angles_for
from flats.fit.rectangle import Fit, Fitter
from flats.geom.alley import ALLEY_CLASS, ALLEY_FACTS, S4_LOTS, alley_lines, observed_alley
from flats.geom.culdesac import CUL_DE_SAC_FACTS, observed_cul_de_sac
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg
from flats.geom.envelope import Setbacks, buildable
from flats.geom.neighbour import NEIGHBOUR_FACTS, lines_from_quadfit, observed_neighbours
from flats.ingest.normalize import zone_for
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet, Verdict as RuleVerdict, ZoneResolution
from flats.score.configure import Configuration, configure
from flats.score.relief import ReliefPolicy
from flats.score.screen import LotFacts, Screening, fit_for, screen
from flats.score.slack import SlackPolicy, Verdict as CheckVerdict

#: quadfit's per-lot stage record after the envelope was cut and carved
#: (s5o): the same columns as s4 plus the envelope, the strips s5 cut it
#: with (``env_setbacks_json``), slope, sewer and the overlay flags. The
#: envelope is here and nowhere else.
S5O_LOTS = S4_LOTS.with_name("s5o_lots.parquet")

#: quadfit's own verdict per lot, for :func:`compare` only.
LOTS_RESULTS = S4_LOTS.with_name("lots_results.csv")

#: s4's tier letter -> the screen's geometry tier. Same four states, same
#: meaning: ``B`` is two or more street directions, ``C`` is concave or
#: many-sided or pole-shaped, ``D`` is no street within reach.
TIER: dict[str, Tier] = {
    "A": Tier.clean,
    "B": Tier.corner,
    "C": Tier.irregular,
    "D": Tier.landlocked,
}

#: How close a mapped sanitary main has to be for ``public_sewer`` to be
#: observed True. quadfit's figure (``s7_report.SEWER_REVIEW_FT``): a
#: four-plex ties into a main at the street, and a main farther off than
#: this is not confirmed to serve the lot. Copied rather than imported
#: because ``Lot Analysis/quadfit`` is not a package this product depends on.
SEWER_MAIN_REACH_FT = 50.0

#: Jurisdictions whose sewer *district* layer quadfit holds. Only here does
#: "outside every district and no main in reach" mean no public sewer; a
#: Multnomah lot with no main in reach is unconfirmed, not unserved.
CLACKAMAS: frozenset[str] = frozenset(j for j, c in COUNTY.items() if c == "clackamas")

#: The s4 columns the bridge reads, and the s5o ones. Columns a stage file
#: written before they existed lacks are read as absent (see
#: :func:`iter_rows`); the bridge then answers those facts the way the
#: registry does rather than inventing a False.
S4_COLUMNS: tuple[str, ...] = (
    "TLID",
    "jurisdiction",
    "zone",
    "tier",
    "area_sqft",
    "frontage_ft",
    "lot_width_ft",
    "lot_depth_ft",
    "edges_json",
    "front_bearings_json",
    "fronts_cul_de_sac",
    "split_zone",
    "neighbour_zones_json",
)
S5O_COLUMNS: tuple[str, ...] = (
    "TLID",
    "ovl_fema_sfha",
    "ovl_fema_floodway",
    "sewer_main_dist_ft",
    "in_sewer_district",
    "wkb",
    "env_setbacks_json",
    "carve_wkb",
)

#: The site facts this bridge can observe, in the order they are reported.
#: Anything not here is left to the registry -- assumed and named, or
#: unknown -- exactly as if no data layer had been consulted.
OBSERVABLE: tuple[str, ...] = (
    *ALLEY_FACTS,
    *CUL_DE_SAC_FACTS,
    *NEIGHBOUR_FACTS,
    "corner_lot",
    "split_zone",
    "in_floodplain",
    "public_sewer",
    "in_sewer_district",
)


def _is_true(value: object) -> bool:
    """A parquet boolean that may arrive as numpy.bool_, None or NaN."""
    if value is None or isinstance(value, float) and math.isnan(value):
        return False
    return bool(value)


def _answered(value: object) -> bool:
    """Whether a nullable boolean column holds an answer on this row."""
    if value is None:
        return False
    return not (isinstance(value, float) and math.isnan(value))


def _finite(value: object) -> float | None:
    """A float column's value, or None where it was null."""
    if value is None:
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def observed_facts(
    row: Mapping[str, Any], layers: Mapping[str, Layer] | None = None
) -> dict[str, bool]:
    """The site facts quadfit measured, in the registry's words.

    Each key is present only where quadfit took the measurement the
    condition's ``evidence`` line describes; a key absent here is a question
    nobody asked, which :func:`~flats.score.configure.configure` treats
    differently from an answer of False.

    * ``abuts_alley`` / ``alley_at_rear`` / ``alley_at_side`` -- s4's edge
      classes, through :func:`flats.geom.alley.observed_alley`. Only where the
      lot has edges: a lot s4 could not trace (tier ``D``) has no alley record
      and gets the registry's assumption, named, rather than a False that
      reads as a measurement.
    * ``fronts_cul_de_sac`` -- s4's bulb test; False is the conservative
      row and so is answered on every lot.
    * ``corner_lot`` -- two or more clustered street directions on the
      frontage, which is s4's tier ``B`` and the registry's "abuts a street
      on two or more sides". Same caveat as the alley: only with edges.
    * ``split_zone`` -- s2's majority rule: the winning zone covers under
      90 % of the lot. A sliver under that is read by quadfit as zoning-map
      noise against the taxlot fabric, and the bridge carries that reading
      both ways.
    * ``in_floodplain`` -- inside FEMA's special flood hazard area or its
      floodway, the registry's evidence line verbatim.
    * ``public_sewer`` -- True where a mapped main is within
      :data:`SEWER_MAIN_REACH_FT`; False only in Clackamas, outside every
      sanitary district, with no main in reach -- quadfit's ``no_public_sewer``.
      Everywhere else it is left unasked: a Multnomah lot with no main in
      reach is unconfirmed, and the registry refuses to guess sewer.
    * ``in_sewer_district`` -- the Clackamas district flag, where the layer
      answered.
    * ``abuts_residential_zone`` / ``abuts_lower_density_zone`` /
      ``abuts_nonresidential_zone`` -- s4's zone across each non-street
      line (``neighbour_zones_json``), through
      :func:`flats.geom.neighbour.observed_neighbours` against the lot's
      layer's own lists of which codes are which (``Layer.neighbours``).
      Only with ``layers`` in hand, only where the layer declares the
      condition, and only where the lines settle it: a line across a park,
      a split-zone neighbour or another city's lot leaves the permissive
      answer unstated, and the lot screens UNKNOWN on the fact as before.
    """
    out: dict[str, bool] = {}
    edges = json.loads(row.get("edges_json") or "[]")
    bearings = json.loads(row.get("front_bearings_json") or "[]")
    if edges:
        out.update(observed_alley(edges, bearings))
        out["corner_lot"] = len(bearings) >= 2
    if layers is not None and row.get("neighbour_zones_json"):
        out.update(_neighbour_facts(row, layers))
    out.update(observed_cul_de_sac(_is_true(row.get("fronts_cul_de_sac"))))
    if _answered(row.get("split_zone")):
        out["split_zone"] = _is_true(row.get("split_zone"))
    if _answered(row.get("ovl_fema_sfha")) or _answered(row.get("ovl_fema_floodway")):
        out["in_floodplain"] = _is_true(row.get("ovl_fema_sfha")) or _is_true(
            row.get("ovl_fema_floodway")
        )
    dist = _finite(row.get("sewer_main_dist_ft"))
    near_main = dist is not None and dist <= SEWER_MAIN_REACH_FT
    if near_main:
        out["public_sewer"] = True
    elif row.get("jurisdiction") in CLACKAMAS and _answered(row.get("in_sewer_district")):
        in_district = _is_true(row.get("in_sewer_district"))
        out["in_sewer_district"] = in_district
        if not in_district:
            out["public_sewer"] = False
    return out


def _neighbour_facts(row: Mapping[str, Any], layers: Mapping[str, Layer]) -> dict[str, bool]:
    """The three neighbour-zoning facts for one s4 row, or nothing.

    The lot's layer supplies the lists; each neighbour's code is spelled
    the way ITS layer screens it (`zone_for`: that layer's
    ``strip_lowercase_suffix``, then the block an alias ruling names), so
    a Portland ``R5a`` across the line is ``R5`` on Portland's list and
    Fairview's ``FLX`` is ``VC``. A code the layer holds no block for keeps
    its map spelling, so an ``OS`` that is only a zone ruling can still be
    listed. A neighbour in a jurisdiction the corpus has no layer for
    cannot be spelled and counts as unresolved.
    """
    juris = str(row.get("jurisdiction"))
    try:
        home = layers.get(layer_id_for(juris))
    except KeyError:
        home = None
    if home is None or not home.neighbours:
        return {}

    def normalise(neighbour_juris: str, raw: str) -> str | None:
        try:
            layer = layers.get(layer_id_for(neighbour_juris))
        except KeyError:
            return None
        if layer is None:
            return None
        code, held = zone_for(layer, raw)
        return held or code

    across = json.loads(row["neighbour_zones_json"])
    lines = lines_from_quadfit(across, normalise)
    # Traced, and every edge a street edge: a whole block. An empty list is
    # a lot s4 never traced and stays unanswered, and so does an irregular
    # lot, whose edge classes are the guesswork the uniform buffer exists
    # for -- a side line misread as a street there would be read as no line.
    all_street = (
        bool(across)
        and all(edge is None for edge in across)
        and TIER.get(str(row.get("tier"))) in (Tier.clean, Tier.corner)
    )
    return observed_neighbours(lines, home.neighbours, juris, all_street=all_street)


@dataclass(frozen=True, slots=True)
class QuadfitLot:
    """One lot as the bridge hands it to the screen."""

    tlid: str
    jurisdiction: str
    zone: str
    #: The corpus layer for the jurisdiction, or None where
    #: :func:`~flats.encode.port_quadfit.layer_id_for` knows no county for
    #: it -- resolved then as ``jurisdiction_not_encoded``.
    layer_id: str | None
    facts: LotFacts
    observed: Mapping[str, bool]
    #: s4's clustered street directions, the angles an ``axis_required``
    #: zone confines the search to.
    front_bearings: tuple[float, ...]
    #: quadfit's carved envelope; None where s5o left none. What the lot is
    #: fitted on only where FLATS cannot cut its own (:func:`envelope_for`).
    envelope: Any
    #: The taxlot polygon (s4's ``wkb``); None from a row that lacks it.
    lot_geom: Any = None
    #: s4's edges, classed the way :mod:`flats.geom.envelope` cuts them;
    #: None where s4 traced none.
    edges: LotEdges | None = None
    #: The ground s5o's carve overlays take off the lot (``carve_wkb``);
    #: None where none touches it.
    carve: Any = None


def carved_rear_ft(row: Mapping[str, Any], observed: Mapping[str, bool]) -> float | None:
    """The rear strip s5 cut off this lot's envelope, in feet.

    s5 records what it cut per edge class (``env_setbacks_json``: F, R, S
    and A, the alley). The court sits behind the building, against the
    rear line -- an alley where the lot has one at the rear (the alley edge
    is the rear lot line, and takes its own cut), the rear edge otherwise.
    ``None`` from a stage file written before s5 recorded its cuts, or a
    lot s5 never traced: the screen then charges the court as though the
    envelope was cut with the corpus's own number, as it did before
    2026-09-22.
    """
    raw = row.get("env_setbacks_json")
    if not raw:
        return None
    cuts = json.loads(raw)
    if not isinstance(cuts, dict):
        return None
    key = "A" if observed.get("alley_at_rear") else "R"
    return _finite(cuts.get(key))


#: s4's edge class letter -> the class :mod:`flats.geom.envelope` cuts by.
#: ``A`` is absent: an alley edge is rear or side by its bearing
#: (:func:`flats.geom.alley.alley_lines`), with the alley flag set.
_EDGE_CLASS: dict[str, EdgeClass] = {
    "F": EdgeClass.front,
    "R": EdgeClass.rear,
    "S": EdgeClass.side,
}


def lot_edges(row: Mapping[str, Any], geom: Any = None) -> LotEdges | None:
    """s4's edge record as the envelope reads it, or None where s4 traced none.

    The class letters map one to one, but for the alley: s4 records it as
    ``A`` whatever side of the lot it runs along, and the corpus holds the
    alley rules per line (``alley_at_rear`` on the rear setback,
    ``setback_alley_side_ft`` for the side), so the edge is named rear or
    side by the same bearing test the alley facts use and carries the flag.
    """
    raw = json.loads(row.get("edges_json") or "[]")
    if not raw:
        return None
    bearings = tuple(float(b) for b in json.loads(row.get("front_bearings_json") or "[]"))
    named = iter(alley_lines(raw, bearings))
    edges: list[Edge] = []
    for x1, y1, x2, y2, letter in raw:
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
        if letter == ALLEY_CLASS:
            cls = EdgeClass.rear if next(named) == "rear" else EdgeClass.side
        else:
            cls = _EDGE_CLASS[str(letter)]
        edges.append(
            Edge(
                x1,
                y1,
                x2,
                y2,
                length_ft=math.hypot(x2 - x1, y2 - y1),
                bearing_deg=bearing_deg(x1, y1, x2, y2),
                cls=cls,
                alley=letter == ALLEY_CLASS,
            )
        )
    hull = geom.convex_hull.area if geom is not None else 0.0
    return LotEdges(
        tier=TIER.get(str(row.get("tier")), Tier.irregular),
        edges=tuple(edges),
        front_bearings=bearings,
        frontage_ft=_finite(row.get("frontage_ft")) or 0.0,
        convexity=geom.area / hull if hull else 1.0,
    )


def setbacks_for(rules: ZoneResolution) -> Setbacks | None:
    """The yards these rules resolve, as the envelope cuts them.

    None where the front, side or rear is not a number: the screen reports
    that lot UNKNOWN on the missing yard anyway, and the envelope it is
    fitted on stays quadfit's rather than one cut with a guess. A yard the
    code EXEMPTS is a number -- zero: the standard does not exist here
    (Portland's rear setback where the rear line is an alley). A combined
    side-yard minimum wider than two single sides is split evenly between
    them -- the fit measures the width between the two, and that width is
    the same however the total is divided.

    A side line on an alley, where the code states no alley-side setback,
    takes the larger of the side and the rear: Gresham, Oregon City and
    Wilsonville define the alley line as a rear lot line, and s5 cuts it at
    the rear for that reason. A city that waives it says so in
    ``setback_alley_side_ft``.
    """
    exempted = set(rules.exempted)

    def number(name: str) -> float | None:
        if name in exempted:
            return 0.0
        got = rules.get(name)
        if isinstance(got, bool) or not isinstance(got, (int, float)):
            return None
        return float(got)

    front, side, rear = (number(f"setback_{c}_ft") for c in ("front", "side", "rear"))
    if front is None or side is None or rear is None:
        return None
    total = number("setback_side_total_ft")
    if total is not None:
        side = max(side, total / 2)
    alley_side = number("setback_alley_side_ft")
    return Setbacks(
        front_ft=front,
        side_ft=side,
        rear_ft=rear,
        street_side_ft=number("setback_street_side_ft"),
        alley_side_ft=max(side, rear) if alley_side is None else alley_side,
    )


@dataclass(frozen=True, slots=True)
class Envelope:
    """The ground one design is fitted on, and where it came from."""

    geom: Any
    #: The rear strip this envelope lost when that is not the resolved rear
    #: setback (:attr:`LotFacts.envelope_rear_ft`); None when it is.
    rear_cut_ft: float | None
    #: ``flats`` -- cut here from the corpus's resolved setbacks;
    #: ``quadfit`` -- s5o's, where FLATS could not cut its own.
    source: str
    setbacks: Setbacks | None = None

    @property
    def sqft(self) -> float:
        return 0.0 if self.geom is None or self.geom.is_empty else float(self.geom.area)


def envelope_for(lot: QuadfitLot, rules: ZoneResolution) -> Envelope:
    """The envelope this lot offers under these rules (FOLLOWUPS 12).

    Cut from the taxlot with :func:`flats.geom.envelope.buildable` at the
    setbacks the corpus RESOLVED for this lot and design -- the variant a
    commercial neighbour, an alley or a corner fired, not quadfit's one
    figure per zone, which is ported at its largest limb precisely because
    s5 cannot tell the limbs apart -- and then s5o's carve overlays taken
    off, the same ground s5o took off its own.

    Falls back to s5o's envelope, and says so, where there is nothing to
    cut from (a stage file without the taxlot polygon or the edges), where
    the lot is tier D (s5 keeps nothing on a lot no street reaches, and
    the screen names it ``NO_FRONTAGE``), and where the rules leave a yard
    without a number.

    Tier C is cut uniformly at the largest yard, the same conservative
    shape s5 cuts, so its rear strip is that largest yard and is reported
    as the cut the court is charged against.
    """
    quadfit = Envelope(lot.envelope, lot.facts.envelope_rear_ft, "quadfit")
    if lot.lot_geom is None or lot.edges is None or lot.edges.tier is Tier.landlocked:
        return quadfit
    setbacks = setbacks_for(rules)
    if setbacks is None:
        return quadfit
    strips = lot.edges.tier in (Tier.clean, Tier.corner)
    if strips and "setback_rear_ft" in rules.exempted and any(
        e.cls is EdgeClass.rear and not e.alley for e in lot.edges.edges
    ):
        # The exemption is about the rear line on the alley; a rear line that
        # is not on it has a setback this resolution does not carry.
        return quadfit
    geom = buildable(lot.lot_geom, lot.edges, setbacks, less=lot.carve)
    return Envelope(geom, None if strips else setbacks.largest_ft, "flats", setbacks)


def lot_from_row(row: Mapping[str, Any], layers: Mapping[str, Layer] | None = None) -> QuadfitLot:
    """Build the screen's inputs for one stage-file row.

    ``layers`` is the loaded corpus, for the neighbour-zoning facts; without
    it those facts are left unasked, as they were before 2026-09-21.
    """
    import shapely

    tier = TIER.get(str(row.get("tier")), Tier.irregular)
    frontage = _finite(row.get("frontage_ft"))
    observed = observed_facts(row, layers)
    facts = LotFacts(
        lot_sqft=_finite(row.get("area_sqft")) or 0.0,
        frontage_ft=frontage if frontage is not None else 0.0,
        lot_width_ft=_finite(row.get("lot_width_ft")),
        lot_depth_ft=_finite(row.get("lot_depth_ft")),
        geometry=tier,
        envelope_rear_ft=carved_rear_ft(row, observed),
    )
    juris = str(row.get("jurisdiction"))
    try:
        layer_id: str | None = layer_id_for(juris)
    except KeyError:
        layer_id = None
    wkb = row.get("wkb")
    envelope = shapely.from_wkb(wkb) if wkb else None
    lot_wkb = row.get("lot_wkb")
    lot_geom = shapely.from_wkb(lot_wkb) if lot_wkb else None
    carve_wkb = row.get("carve_wkb")
    return QuadfitLot(
        tlid=str(row["TLID"]),
        jurisdiction=juris,
        zone=str(row.get("zone")),
        layer_id=layer_id,
        facts=facts,
        observed=observed,
        front_bearings=tuple(float(b) for b in json.loads(row.get("front_bearings_json") or "[]")),
        envelope=envelope,
        lot_geom=lot_geom,
        edges=lot_edges(row, lot_geom),
        carve=shapely.from_wkb(carve_wkb) if carve_wkb else None,
    )


def iter_rows(
    s4: Path = S4_LOTS,
    s5o: Path = S5O_LOTS,
    *,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 0,
    jurisdictions: Iterable[str] = (),
) -> Iterator[dict[str, Any]]:
    """Every lot's bridge row, s4 facts joined to s5o's envelope on TLID.

    Read from two files rather than one because s4 is re-run alone (a width
    or alley refresh) and s5o then predates its newest columns -- s7 joins
    them the same way. A column either file lacks is simply absent from the
    row, and :func:`observed_facts` leaves that fact unasked.
    """
    import pandas as pd
    import pyarrow.parquet as pq

    have4 = set(pq.read_schema(s4).names)
    have5 = set(pq.read_schema(s5o).names)
    # s4's ``wkb`` is the taxlot, s5o's the envelope: the lot's is renamed.
    lot_wkb = ["wkb"] if "wkb" in have4 else []
    left = pd.read_parquet(s4, columns=[c for c in S4_COLUMNS if c in have4] + lot_wkb)
    left = left.rename(columns={"wkb": "lot_wkb"})
    right = pd.read_parquet(s5o, columns=[c for c in S5O_COLUMNS if c in have5])
    frame = left.merge(right, on="TLID", how="left")
    if jurisdictions:
        frame = frame[frame["jurisdiction"].isin(set(jurisdictions))]
    if sample is not None and sample < len(frame):
        frame = frame.sample(n=sample, random_state=seed)
    if limit is not None:
        frame = frame.head(limit)
    # Every null -- NaN, NaT, pandas' NA -- leaves as None, so the readers
    # above see one shape of "no answer" whatever dtype the column arrived in.
    frame = frame.astype(object).where(frame.notna(), None)
    yield from frame.to_dict("records")


@dataclass(frozen=True, slots=True)
class Screened:
    """One lot x design through the screen, with what it was screened under."""

    lot: QuadfitLot
    design: Design
    rules: ZoneResolution
    config: Configuration
    fit: Fit
    screening: Screening
    #: The same checks with ``RULE_UNVERIFIED`` lifted and nothing else
    #: changed -- what this lot becomes when the corpus is signed -- and
    #: ``screening`` itself for every other rule verdict. Its checks, head
    #: and ask are the verdict's own; only the colour and the reasons can
    #: differ. Named, never mistaken for the verdict.
    signed: Screening
    #: How many angles the envelope was searched at, and the sweep step.
    angles: int
    step_deg: float
    #: The ground this design was fitted on (:func:`envelope_for`).
    envelope: Envelope | None = None


def _if_signed(
    rules: ZoneResolution,
    lot: LotFacts,
    design: Design,
    fit: Fit,
    screening: Screening,
    *,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    config: Configuration,
) -> Screening:
    if rules.verdict is not RuleVerdict.unverified:
        return screening
    signed = dataclasses.replace(rules, verdict=RuleVerdict.trusted, untrusted=())
    return screen(signed, lot, design, fit, policy=policy, relief=relief, config=config)


def screen_lot(
    lot: QuadfitLot,
    designs: Sequence[Design],
    *,
    rules: RuleSet,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    step_deg: float = DEFAULT_STEP_DEG,
) -> list[Screened]:
    """Screen one lot against every design, one envelope search for all.

    The configuration and the resolution are per design (a design's own
    conditions ride in); the :class:`~flats.fit.rectangle.Fitter` is built
    once, at the angles the zone allows: a zone that makes the building face
    the street confines the search to s4's street directions, every other
    zone gets the sweep with those directions folded in. A lot with no
    street direction is swept either way -- not knowing the front is not a
    reason to search nothing, and ``NO_FRONTAGE`` already names the lot.
    """
    layer_id = lot.layer_id or f"or/?/{lot.jurisdiction}"
    resolved: list[tuple[Design, Configuration, ZoneResolution]] = []
    for design in designs:
        config = configure(lot.facts, design, observed=lot.observed)
        got = rules.resolve(layer_id, lot.zone, config.conditions, lot=config.measures)
        resolved.append((design, config, got))

    axis_required = any(
        got.get("orientation_constraint") == "axis_required" for _, _, got in resolved
    )
    angles = angles_for(
        lot.front_bearings,
        axis_required=axis_required and bool(lot.front_bearings),
        step_deg=step_deg,
    )
    # One search per distinct envelope: the designs usually resolve the
    # same yards, and a Fitter is the expensive part.
    fitters: dict[Any, Fitter] = {}

    out: list[Screened] = []
    for design, config, got in resolved:
        env = envelope_for(lot, got)
        key = (env.source, env.setbacks)
        if key not in fitters:
            fitters[key] = Fitter(env.geom, angles)
        facts = dataclasses.replace(lot.facts, envelope_rear_ft=env.rear_cut_ft)
        fit = fit_for(fitters[key], design, got, placement=False, carved_rear_ft=env.rear_cut_ft)
        result = screen(got, facts, design, fit, policy=policy, relief=relief, config=config)
        shadow = _if_signed(
            got, facts, design, fit, result, policy=policy, relief=relief, config=config
        )
        out.append(
            Screened(
                lot=lot,
                design=design,
                rules=got,
                config=config,
                fit=fit,
                screening=result,
                signed=shadow,
                angles=len(angles),
                step_deg=step_deg,
                envelope=env,
            )
        )
    return out


def row_for(s: Screened) -> dict[str, Any]:
    """One flat record per lot x design, what the batch writes."""
    leaning = s.config.leans_on(s.rules.levers)
    failing = tuple(c.check for c in s.screening.checks if c.verdict is CheckVerdict.fails)
    return {
        "TLID": s.lot.tlid,
        "jurisdiction": s.lot.jurisdiction,
        "zone": s.lot.zone,
        "layer_id": s.lot.layer_id,
        "tier": s.lot.facts.geometry.value,
        "design": s.design.key,
        "rule_verdict": s.rules.verdict.value,
        "triage": s.screening.triage.value,
        "if_signed": s.signed.triage.value,
        "reasons": ",".join(s.screening.reasons),
        "if_signed_reasons": ",".join(s.signed.reasons),
        "head": s.screening.head,
        "dominant": s.screening.dominant,
        "failing": ",".join(failing),
        "unchecked": ",".join(s.screening.unchecked),
        "ask": s.screening.ask.value,
        "fits": bool(s.fit.fits),
        "fit_slack_ft": s.screening.fit_slack_ft,
        "stalls_charged": s.screening.stalls_charged,
        "stalls_seated": s.screening.stalls_seated,
        "parking_band": s.screening.parking_band,
        "fit_best_depth_ft": s.fit.best_depth_ft,
        "fit_required_ft": s.fit.required_ft,
        "fit_across_ft": s.fit.across_ft,
        "fit_angle_deg": s.fit.angle_deg,
        "fit_orientation": s.fit.orientation.value if s.fit.orientation else None,
        "lot_sqft": s.lot.facts.lot_sqft,
        "frontage_ft": s.lot.facts.frontage_ft,
        "lot_width_ft": s.lot.facts.lot_width_ft,
        "lot_depth_ft": s.lot.facts.lot_depth_ft,
        "observed": json.dumps(dict(sorted(s.lot.observed.items()))),
        "assumed_leaning": ",".join(n for n in leaning if n in s.config.assumed),
        "unknown_leaning": ",".join(n for n in leaning if n in s.config.unknown),
        "angles": s.angles,
        "step_deg": s.step_deg,
        "envelope_sqft": s.envelope.sqft if s.envelope else None,
        "envelope_source": s.envelope.source if s.envelope else None,
    }


# --- the batch ---------------------------------------------------------------

_WORKER: dict[str, Any] = {}


def _init_worker(step_deg: float) -> None:
    """Load the corpus, catalog and policies once per process."""
    from flats.designs.model import load_catalog
    from flats.encode.load import load_trusted
    from flats.score import relief as relief_mod, slack as slack_mod

    _WORKER["rules"] = load_trusted(strict=False).rules
    _WORKER["designs"] = list(load_catalog())
    _WORKER["policy"] = slack_mod.load_policy()
    _WORKER["relief"] = relief_mod.load_policy()
    _WORKER["step_deg"] = step_deg


def _work_chunk(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        lot = lot_from_row(row, _WORKER["rules"].layers)
        for s in screen_lot(
            lot,
            _WORKER["designs"],
            rules=_WORKER["rules"],
            policy=_WORKER["policy"],
            relief=_WORKER["relief"],
            step_deg=_WORKER["step_deg"],
        ):
            out.append(row_for(s))
    return out


#: Best colour a lot's designs reached, for the one-line-per-lot view.
_RANK: dict[str, int] = {"green": 0, "yellow": 1, "unknown": 2, "red": 3}


def per_lot(frame: Any) -> Any:
    """Collapse lot x design rows to one per lot: the best design's colour.

    A lot is as good as the best pod that stands on it, so GREEN beats
    YELLOW beats UNKNOWN beats RED, and the head and reasons carried are the
    winning design's.
    """
    ranked = frame.assign(_rank=frame["if_signed"].map(_RANK))
    ranked = ranked.sort_values(["TLID", "_rank"], kind="stable")
    return ranked.drop_duplicates("TLID", keep="first").drop(columns="_rank")


def compare(frame: Any, results: Path = LOTS_RESULTS) -> str:
    """FLATS's ``if_signed`` beside quadfit's triage, as a markdown report.

    quadfit's colours are ``green`` / ``review`` / ``red``; FLATS's are
    GREEN / YELLOW / UNKNOWN / RED. The crosstab is per lot (the best
    design), then per jurisdiction, then the checks and reasons behind the
    two disagreements that matter: FLATS RED where quadfit is green (a
    standard one product enforces and the other does not, or a measurement
    that differs), and FLATS GREEN where quadfit is red (the same, the other
    way). Everything else is bookkeeping.
    """
    import pandas as pd

    lots = per_lot(frame)
    # The stall columns arrived in quadfit's s6s on 2026-07-28; a results
    # file from before them still compares on the colour, with the band
    # table reading "(none)" throughout rather than refusing the report.
    wanted = [
        "TLID",
        "triage",
        "binding_constraint",
        "policy_exclusion",
        "parking_tier",
        "stalls_provided",
        "layout_method",
    ]
    header = pd.read_csv(results, nrows=0).columns
    q = pd.read_csv(results, usecols=[c for c in wanted if c in header], dtype=str)
    for name in wanted:
        if name not in q.columns:
            q[name] = pd.Series(pd.NA, index=q.index, dtype="string")
    m = lots.merge(q, on="TLID", how="left", suffixes=("", "_quadfit"))
    m["quadfit"] = m["triage_quadfit"].fillna("absent")
    lines: list[str] = []
    lines.append("# FLATS screen from the county map -- against quadfit\n")
    lines.append(
        f"{len(frame):,} lot x design rows, {len(lots):,} lots, "
        f"{frame['design'].nunique()} designs; sweep step "
        f"{frame['step_deg'].iloc[0] if len(frame) else '?'} deg.\n"
    )
    lines.append("## The verdict as it stands\n")
    lines.append(_counts(frame["triage"]) + "\n")
    lines.append("Reasons on the verdict, lot x design rows:\n")
    lines.append(_counts(frame["reasons"].str.split(",").explode().replace("", "(none)")) + "\n")
    lines.append("## If signed -- per lot (best design) against quadfit's triage\n")
    ct = pd.crosstab(m["if_signed"], m["quadfit"], margins=True)
    lines.append(_table(ct) + "\n")
    lines.append("### By jurisdiction: FLATS if-signed GREEN / quadfit green\n")
    by = (
        m.assign(fg=m["if_signed"] == "green", qg=m["quadfit"] == "green")
        .groupby("jurisdiction")
        .agg(lots=("TLID", "size"), flats_green=("fg", "sum"), quadfit_green=("qg", "sum"))
        .sort_values("lots", ascending=False)
    )
    lines.append(_table(by) + "\n")
    red_where_green = m[(m["if_signed"] == "red") & (m["quadfit"] == "green")]
    lines.append(f"### FLATS RED where quadfit is green: {len(red_where_green):,} lots\n")
    lines.append("Tightest failing check (head):\n")
    lines.append(_counts(red_where_green["head"].fillna("(none)")) + "\n")
    green_where_red = m[(m["if_signed"] == "green") & (m["quadfit"] == "red")]
    lines.append(f"### FLATS GREEN where quadfit is red: {len(green_where_red):,} lots\n")
    lines.append("quadfit's binding constraint:\n")
    lines.append(_counts(green_where_red["binding_constraint"].fillna("(none)")) + "\n")
    lines.append("quadfit's policy exclusion:\n")
    lines.append(_counts(green_where_red["policy_exclusion"].fillna("(none)")) + "\n")
    # The stall count beside the colour, against the county map's own. Both
    # products charge the floor and report the band since 2026-09-18, so on
    # the lots both call green the bands should mostly agree; where the
    # screen seats fewer, the difference is the court's shape (one row
    # across here, the largest rectangle either way round there) or the
    # alley the county map parks on and the screen does not yet draw.
    both = m[(m["if_signed"] == "green") & (m["quadfit"] == "green")]
    lines.append(f"### Stalls seated, where both are green: {len(both):,} lots\n")
    lines.append("FLATS band (rows) against quadfit's parking_tier (columns):\n")
    lines.append(
        _table(
            pd.crosstab(
                both["parking_band"].fillna("(none)"),
                both["parking_tier"].fillna("(none)"),
                margins=True,
            )
        )
        + "\n"
    )
    seated = pd.to_numeric(both["stalls_seated"], errors="coerce")
    provided = pd.to_numeric(both["stalls_provided"], errors="coerce")
    diff = seated - provided
    lines.append("FLATS stalls seated less quadfit's stalls provided:\n")
    lines.append(_counts(diff.dropna().astype(int).astype(str)) + "\n")
    alley = both["layout_method"].fillna("").str.contains("alley")
    lines.append(
        f"Of those seating fewer, {int((alley & (diff < 0)).sum()):,} park on the "
        f"alley in quadfit.\n"
    )
    lines.append("FLATS band on every lot the screen calls green once signed:\n")
    green = m[m["if_signed"] == "green"]
    lines.append(_counts(green["parking_band"].fillna("(none)")) + "\n")
    unknown = m[m["if_signed"] == "unknown"]
    lines.append(f"### Still UNKNOWN once signed: {len(unknown):,} lots\n")
    lines.append(
        _counts(unknown["if_signed_reasons"].str.split(",").explode().replace("", "(none)"))
        + "\n"
    )
    lines.append("Assumed facts a standard turns on (lot x design rows):\n")
    lines.append(
        _counts(frame["assumed_leaning"].str.split(",").explode().replace("", "(none)")) + "\n"
    )
    lines.append("Unobserved facts a standard turns on (lot x design rows):\n")
    lines.append(
        _counts(frame["unknown_leaning"].str.split(",").explode().replace("", "(none)")) + "\n"
    )
    return "\n".join(lines)


def _table(frame: Any) -> str:
    """A DataFrame as a markdown table, index first, without tabulate."""
    cols = [str(c) for c in frame.columns]
    head = "| " + " | ".join([str(frame.index.name or ""), *cols]) + " |"
    rule = "|---|" + "---:|" * len(cols)
    body = [
        "| " + " | ".join([str(idx), *(_cell(v) for v in row)]) + " |"
        for idx, row in zip(frame.index, frame.itertuples(index=False))
    ]
    return "\n".join([head, rule, *body])


def _cell(value: Any) -> str:
    try:
        return f"{int(value):,}" if float(value) == int(value) else f"{float(value):,.1f}"
    except (TypeError, ValueError):
        return str(value)


def _counts(series: Any, top: int = 25) -> str:
    vc = series.value_counts()
    rows = [f"| {k} | {v:,} |" for k, v in vc.head(top).items()]
    if len(vc) > top:
        rows.append(f"| ... {len(vc) - top} more | |")
    return "\n".join(["| value | rows |", "|---|---:|", *rows])


def run(
    out: Path,
    *,
    s4: Path = S4_LOTS,
    s5o: Path = S5O_LOTS,
    results: Path | None = LOTS_RESULTS,
    processes: int = 1,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 0,
    jurisdictions: Iterable[str] = (),
    step_deg: float = DEFAULT_STEP_DEG,
    chunk_size: int = 500,
    log: Any = print,
) -> Path:
    """Screen every lot and write ``lots.parquet``, ``meta.json``, ``summary.md``.

    Parts are written as they finish (``parts/NNNNN.parquet``) and
    concatenated at the end, so a run that dies at hour three keeps its
    first three hours. Re-running with the same ``out`` starts over.
    """
    import time
    from multiprocessing import Pool

    import pandas as pd

    out.mkdir(parents=True, exist_ok=True)
    parts_dir = out / "parts"
    parts_dir.mkdir(exist_ok=True)
    for old in parts_dir.glob("*.parquet"):
        old.unlink()

    rows = list(
        iter_rows(s4, s5o, limit=limit, sample=sample, seed=seed, jurisdictions=jurisdictions)
    )
    chunks = [rows[i : i + chunk_size] for i in range(0, len(rows), chunk_size)]
    log(f"bridge: {len(rows):,} lots in {len(chunks)} chunks, {processes} processes, "
        f"{step_deg} deg step")
    t0 = time.time()
    done = 0

    def _write(i: int, records: list[dict[str, Any]]) -> None:
        pd.DataFrame.from_records(records).to_parquet(parts_dir / f"{i:05d}.parquet", index=False)

    if processes <= 1:
        _init_worker(step_deg)
        for i, chunk in enumerate(chunks):
            _write(i, _work_chunk(chunk))
            done += len(chunk)
            log(f"  {done:,}/{len(rows):,}  {time.time() - t0:,.0f}s")
    else:
        with Pool(processes, initializer=_init_worker, initargs=(step_deg,)) as pool:
            for i, records in enumerate(pool.imap(_work_chunk, chunks)):
                _write(i, records)
                done += len(chunks[i])
                if i % 10 == 0 or i == len(chunks) - 1:
                    log(f"  {done:,}/{len(rows):,}  {time.time() - t0:,.0f}s")

    parts = sorted(parts_dir.glob("*.parquet"))
    frame = (
        pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
        if parts
        else pd.DataFrame()
    )
    frame.to_parquet(out / "lots.parquet", index=False)
    meta = {
        "lots": len(rows),
        "rows": len(frame),
        "step_deg": step_deg,
        "processes": processes,
        "seconds": round(time.time() - t0, 1),
        "s4": str(s4),
        "s5o": str(s5o),
        "sample": sample,
        "limit": limit,
        "jurisdictions": sorted(jurisdictions),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if results is not None and results.exists() and len(frame):
        (out / "summary.md").write_text(compare(frame, results), encoding="utf-8")
    log(f"bridge: wrote {len(frame):,} rows to {out / 'lots.parquet'} in {meta['seconds']}s")
    return out / "lots.parquet"


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=S4_LOTS.parents[1] / "flats" / "bridge")
    ap.add_argument("--s4", type=Path, default=S4_LOTS)
    ap.add_argument("--s5o", type=Path, default=S5O_LOTS)
    ap.add_argument("--results", type=Path, default=LOTS_RESULTS)
    ap.add_argument("--processes", type=int, default=1)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sample", type=int)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--jurisdiction", action="append", default=[])
    ap.add_argument("--step-deg", type=float, default=DEFAULT_STEP_DEG)
    ap.add_argument("--chunk-size", type=int, default=500)
    args = ap.parse_args(argv)
    run(
        args.out,
        s4=args.s4,
        s5o=args.s5o,
        results=args.results,
        processes=args.processes,
        limit=args.limit,
        sample=args.sample,
        seed=args.seed,
        jurisdictions=args.jurisdiction,
        step_deg=args.step_deg,
        chunk_size=args.chunk_size,
    )
    return 0


__all__ = [
    "CLACKAMAS",
    "LOTS_RESULTS",
    "OBSERVABLE",
    "S4_COLUMNS",
    "S5O_COLUMNS",
    "S5O_LOTS",
    "SEWER_MAIN_REACH_FT",
    "TIER",
    "Envelope",
    "QuadfitLot",
    "Screened",
    "carved_rear_ft",
    "envelope_for",
    "compare",
    "iter_rows",
    "lot_edges",
    "lot_from_row",
    "observed_facts",
    "per_lot",
    "row_for",
    "run",
    "screen_lot",
    "setbacks_for",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
