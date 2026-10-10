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
street, a yard with no number), and each row says which
(``envelope_source``). A lot with a rear line on the alley and another off
it is cut with both rear numbers, the alley's on the one and the ordinary
on the other (:func:`rear_off_alley`).

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
import itertools
import json
import math
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flats.designs.model import Design
from flats.encode.port_quadfit import COUNTY, layer_id_for
from flats.fit import easement
from flats.fit.angles import DEFAULT_STEP_DEG, angles_for, normalize
from flats.fit.draw import draw
from flats.fit.outdoor import largest_square, open_ground
from flats.fit.rectangle import Fit, Fitter
from flats.fit.slope import ONE_M, TEN_M, load_rules as slope_rules
from flats.geom.alley import (
    ALLEY_CLASS,
    ALLEY_FACTS,
    S4_LOTS,
    alley_lines,
    cover_stretches,
    decode_cover,
    observed_alley,
    rear_cover_runs,
    registry_alley,
    side_alley_along,
    usable_run_ft,
)
from flats.geom.corridor import (
    CORRIDOR_FACTS,
    FRONT_REACH_FT,
    STREET_CLASS,
    CorridorMap,
    observed_corridors,
    off_corridor_lines,
)
from flats.geom.corridor import load_maps as load_corridor_maps
from flats.geom.corner import (
    front_bearings as corner_fronts,
    is_corner,
    name_front,
    through_lot,
    through_plans,
    two_streets,
)
from flats.geom.culdesac import CUL_DE_SAC_FACTS, observed_cul_de_sac
from flats.geom.drawn import load_area, observed_drawn
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg
from flats.geom.envelope import Setbacks, buildable
from flats.geom.frontage_curve import BAND_DEG, angle_of, is_unbroken, makes_corner
from flats.geom.neighbour import (
    NEIGHBOUR_FACTS,
    lines_from_quadfit,
    observed_neighbours,
    street_lines_clear,
)
from flats.geom.park import PARK_FACTS, observed_parks
from flats.geom.sidewalk import (
    depth_for,
    easement_depth_ft,
    easement_shifted,
    load_streets,
    observed_sidewalk_easement,
)
from flats.geom.street_class import (
    LOCAL_STREET,
    load_class_maps,
    access_record,
    measured_access,
    observed_local_street,
    street_ranks,
    unknown_access,
)
from flats.geom.named_street import (
    NAMED_STREET_FACT,
    beyond_reach_column,
    named_street_column,
    observed_named_street,
)
from flats.geom.one_street import one_street_column
from flats.geom.street_end import STREET_END_FACT, observed_street_end, street_end_column
from flats.ingest.flatter import flatter_checked
from flats.ingest.normalize import zone_for
from flats.rules.conditions import ACROSS_STREET_CONDITIONS
from flats.rules.definitions import Abuts, Definition, Side, decide
from flats.rules.model import TRANSIT_MEASURES, Layer
from flats.rules.net_area import MEASURED as NET_MEASURED, SLOPES as NET_SLOPES, measured_deductions
from flats.rules.resolver import RuleSet, Verdict as RuleVerdict, ZoneResolution
from flats.rules.resource_overlays import COLUMNS as PERMIT_COLUMNS, permits_on
from flats.score.configure import Configuration, configure
from flats.score import flags as flag_plan
from flats.score import margins as margin_record
from flats.score.relief import ReliefPolicy
from flats.score.room import Room, room_for
from flats.score.paper import (
    _yard,
    court_across,
    court_depth,
    front_lot_line_rule,
    front_lot_line_through_rule,
    lot_line_buffer_ft,
    side_column,
    side_court,
    side_street_fed,
)
from flats.score.screen import (
    COURT_SHAPED,
    STEEP_GROUND,
    STREET_RANK_UNKNOWN,
    STREET_UNCONFIRMED,
    STRIP_FIELD,
    LotFacts,
    Screening,
    Triage,
    _beside_beyond,
    _court_beyond_rear,
    _fix,
    fit_for,
    screen,
)
from flats.score.slack import SlackPolicy, Verdict as CheckVerdict
from flats.score.turns import Fix

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

#: Where the district flag is the fact itself, not a stand-in for a main.
#: ORS 197A.015(12)(c) makes "within the boundaries of a sanitary district"
#: part of what urban unincorporated land IS, so a Portland main next door
#: does not answer it. The district layer (Clackamas County's, which draws
#: every district whole, Dunthorpe-Riverdale and Clean Water Services
#: included) covers unincorporated Multnomah: the county assessor's own tax
#: districts list those two as the only sewer districts in the county
#: (checked 2026-10-01). Outside one is False here and says nothing about
#: sewer service -- a city may serve the lot by contract -- so it never
#: answers ``public_sewer``.
DISTRICT_ONLY: frozenset[str] = frozenset({"multnomah_unincorporated"})

#: Where the city's own adopted natural-resource map answers
#: ``protected_water_feature``. Oregon City's NROD is drawn 10 ft beyond the
#: 17.49.110 vegetated corridor (17.49.030(1) makes the map the regulatory
#: boundary), so a lot it does not touch holds no corridor the 17.49.110
#: footnotes could widen, and a lot it touches keeps the question open --
#: the corridor is measured from a water feature nothing here locates, and
#: the map may be re-delineated either way. The NROD itself is carved from
#: the envelope already (quadfit overlays.yaml). Only Oregon City: no other
#: layer turns on the fact, and another city's water map is not this one.
NROD_ANSWERS: frozenset[str] = frozenset({"oregon_city"})
NROD_SQFT = "ovl_oregon_city_nrod_sqft"

#: Where Portland's zoning map answers ``constrained_sites_overlay``: the city
#: and the unincorporated pockets it administers, which its map covers with the
#: same letters (quadfit s2 ``has_z_overlay``). Nowhere else does a "z" mean
#: anything, and s2's False there is only "outside Portland's map".
Z_ANSWERS: frozenset[str] = frozenset({"portland", "multnomah_unincorporated"})

#: Where the Willamette Greenway map answers ``willamette_greenway_zone``:
#: Milwaukie's WG zone off the city's own Zoning Map service (quadfit
#: ``milwaukie_greenway``, which s5o measures for Milwaukie lots only).
GREENWAY_ANSWERS: frozenset[str] = frozenset({"milwaukie"})
GREENWAY_COLUMN = "ovl_milwaukie_greenway"

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
    "has_z_overlay",
    "neighbour_zones_json",
    "park_across_json",
    "alley_width_ft",
    "alley_cover_json",
    "street_across_json",
    "street_kind_json",
    "sans_drive_json",
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
    GREENWAY_COLUMN,
    # The mapped areas a house goes up in only with a permit
    # (:mod:`flats.rules.resource_overlays`); the FEMA fringe is already
    # above, and pandas refuses a column named twice.
    *(c for c in PERMIT_COLUMNS if c != "ovl_fema_sfha"),
    # Each deduction a city's net area may take off the lot, in square feet
    # (:data:`flats.rules.net_area.MEASURED`).
    *sorted({c for cols in NET_MEASURED.values() for c in cols}),
)

#: The site facts this bridge can observe, in the order they are reported.
#: Anything not here is left to the registry -- assumed and named, or
#: unknown -- exactly as if no data layer had been consulted.
OBSERVABLE: tuple[str, ...] = (
    *ALLEY_FACTS,
    *CUL_DE_SAC_FACTS,
    # Only ever False, and only where no street ends near the lot.
    STREET_END_FACT,
    # True within 200 ft of a street the code names, False beyond.
    NAMED_STREET_FACT,
    # Only where a city's TSP map serves the lot (flats.geom.street_class).
    LOCAL_STREET,
    *NEIGHBOUR_FACTS,
    *PARK_FACTS,
    *CORRIDOR_FACTS,
    "corner_lot",
    "through_lot",
    "split_zone",
    "in_floodplain",
    "protected_water_feature",
    "constrained_sites_overlay",
    "willamette_greenway_zone",
    # Only where a map code settles it (an alias ruling's ``observes``) or a
    # layer's ``drawn_areas`` traces it.
    "inside_mapped_use_area",
    "north_of_marine_drive",
    "willamette_historic_district",
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
    row: Mapping[str, Any],
    layers: Mapping[str, Layer] | None = None,
    corridors: Sequence[CorridorMap] = (),
) -> dict[str, bool]:
    """The site facts quadfit measured, in the registry's words.

    Each key is present only where quadfit took the measurement the
    condition's ``evidence`` line describes; a key absent here is a question
    nobody asked, which :func:`~flats.score.configure.configure` treats
    differently from an answer of False.

    * ``abuts_alley`` / ``alley_at_rear`` / ``alley_at_side`` -- s4's edge
      classes, through :func:`flats.geom.alley.registry_alley`: ``alley_at_rear``
      only where s4's ``alley_cover_json`` says the alley runs the whole rear
      line (FOLLOWUPS 3(e)) -- the rear setback's alley variant is one number
      for the line, and a stub along part of it leaves the rest across from
      the neighbour; no cover on record is no rear alley line. Only where the
      lot has edges: a lot s4 could not trace (tier ``D``) has no alley record
      and gets the registry's assumption, named, rather than a False that
      reads as a measurement.
    * ``fronts_cul_de_sac`` -- s4's bulb test; False is the conservative
      row and so is answered on every lot.
    * ``at_street_end`` -- False only where no street ends within
      :data:`~flats.geom.street_end.REACH_FT` of the taxlot (``street_end_ft``,
      measured by :func:`iter_rows`); never True, so near an end, or where
      nothing measured, Gresham's Minor Access Street note keeps its cap.
    * ``near_named_street_200ft`` -- True where the taxlot lies within 200 ft of
      Eagle Creek Rd or Hinman Rd (``named_street_ft``, measured by
      :func:`iter_rows`), False beyond; Estacada's NCR fourplex path. The code's
      "major collector" half is not held, so a lot near an unlisted collector
      is False (RED, never a false GREEN). The code asks for the DWELLING
      within 200 ft, so in NCR the lot ground beyond the band is also taken
      off the placement area (``reach_off_wkb``).
    * ``local_street`` -- from ``local_street_obs``, which
      :func:`with_local_street` reads off a city's TSP map: True only where
      every street line is local by the map AND by Metro's street type,
      False where every one is a collector or an arterial, else unasked.
    * ``corner_lot`` -- True where the frontage runs in two directions at
      least :data:`~flats.geom.corner.CORNER_MIN_DEG` apart, the test that
      names a corner lot's front (:func:`flats.geom.corner.two_streets`);
      False on a lot with one street direction. Two directions closer than
      that (s4 splits a street at 20 degrees) are a street that bends OR two
      streets meeting at a shallow angle, and the fact is left UNASKED there:
      a corner variant tightens some standards (Gresham's corner lot width,
      Wood Village's corner side and rear yard) and relaxes others (Gresham's
      unit-lot corner frontage, Multnomah LR-5's conditional use), so
      neither answer is the safe one, and the registry's assumption is named
      wherever a standard turns on it. Where the lot's own code counts
      streets rather than asking them to meet (Gresham 3.0100: "a lot that
      has frontage on two or more streets"; :func:`_counts_streets`), a
      through lot -- street along two opposite lines,
      :func:`flats.geom.corner.through_lot` -- is True as well: s4 clusters
      the two ends into one direction, and the 45-degree test alone read
      them False. Same caveat as the alley: only with edges.
    * ``through_lot`` -- street along two opposite lines
      (:func:`flats.geom.corner.through_lot`, alley edges are not street
      edges); only with edges. Gresham's Table 4.0131 note 2 is the reader:
      every street frontage of a double-frontage lot is a front yard. A
      True keeps that note an open question (``held_open`` in the screen),
      because no setback value here says what the second front becomes.
    * ``protected_water_feature`` -- Oregon City only, off the city's NROD
      map (:data:`NROD_ANSWERS`): False where the lot does not touch it.
    * ``constrained_sites_overlay`` -- Portland and its pockets only
      (:data:`Z_ANSWERS`), off the "z" letters on Portland's zoning map: True
      where any part of the lot is inside one (PCC 33.418.040 is "any portion").
    * ``willamette_greenway_zone`` -- Milwaukie only (:data:`GREENWAY_ANSWERS`),
      off the city's WG zone: True where any part of the lot is inside it.
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
      answered; on unincorporated Multnomah (:data:`DISTRICT_ONLY`) always,
      main or no main, because there it is the state's test, not a sewer
      signal.
    * ``abuts_residential_zone`` / ``abuts_lower_density_zone`` /
      ``abuts_nonresidential_zone`` -- s4's zone across each non-street
      line (``neighbour_zones_json``), through
      :func:`flats.geom.neighbour.observed_neighbours` against the lot's
      layer's own lists of which codes are which (``Layer.neighbours``).
      Only with ``layers`` in hand, only where the layer declares the
      condition, and only where the lines settle it: a line across a park,
      a split-zone neighbour or another city's lot leaves the permissive
      answer unstated, and the lot screens UNKNOWN on the fact as before.
    * ``abuts_park`` -- s4's ORCA unit types across each non-street line
      (``park_across_json``), through :func:`flats.geom.park.observed_parks`
      against the lot's layer's own list of which types its code calls a
      park (``Layer.parks``). Only with ``layers`` in hand and only where
      the layer declares it; ANY line in a park settles True, False needs
      every line read. A whole block (every edge a street edge, a clean or
      corner lot) abuts no park and is answered False with or without the
      column; otherwise a stage file s4 wrote without the ORCA layer leaves
      it unasked.
    * ``civic_corridor`` / ``civic_corridor_setback`` -- a street line
      running along a line of Portland's corridor maps, through
      :func:`flats.geom.corridor.observed_corridors`. Only with the maps in
      hand (the bridge's ``--sources``), only on lots of the layers a map
      serves, and only with edges. ``civic_corridor_setback_all_streets``
      beside it -- EVERY street line on a Map 130-1 stretch by the street it
      abuts -- only where the snapshot also holds the street network.
    * a fact the lot's own map code settles -- an alias ruling's
      ``observes`` (Fairview's ``FLX`` is the VC flex area, so
      ``inside_mapped_use_area``). True only, and only with ``layers``.
    * a fact an area the layer traced settles (``drawn_areas``: Tualatin's
      Residential Sub-District, West Linn's Willamette Historic District,
      Gresham's land north of Marine Drive) -- the lot's share inside it,
      through :func:`flats.geom.drawn.observed_drawn`. Only with ``layers``,
      only on lots of the zones the area names, and only from the lot's own
      shape (``lot_wkb``); a lot the boundary cuts through is unanswered.
    """
    out: dict[str, bool] = {}
    edges = json.loads(row.get("edges_json") or "[]")
    bearings = json.loads(row.get("front_bearings_json") or "[]")
    if edges:
        out.update(registry_alley(edges, bearings, _cover(row, edges)))
        through = through_lot(edges, bearings)
        out["through_lot"] = through
        if _counts_streets(row, layers) and through:
            out["corner_lot"] = True
        elif len(bearings) < 2 or two_streets(bearings):
            out["corner_lot"] = len(bearings) >= 2
        if corridors:
            out.update(observed_corridors(edges, _layer_id(row), corridors))
    if layers is not None and row.get("neighbour_zones_json"):
        out.update(_neighbour_facts(row, layers))
    if layers is not None and edges:
        out.update(_park_facts(row, edges, layers))
    if layers is not None:
        out.update(_map_code_facts(row, layers))
        for name, inside in _drawn_facts(row, layers).items():
            out[name] = out.get(name) or inside
    out.update(observed_cul_de_sac(_is_true(row.get("fronts_cul_de_sac"))))
    out.update(observed_street_end(_finite(row.get("street_end_ft"))))
    out.update(observed_named_street(_finite(row.get("named_street_ft"))))
    if isinstance(row.get("local_street_obs"), bool):
        out[LOCAL_STREET] = row["local_street_obs"]
    out.update(observed_sidewalk_easement(_finite(row.get("sidewalk_easement_ft"))))
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
    if row.get("jurisdiction") in DISTRICT_ONLY and _answered(row.get("in_sewer_district")):
        out["in_sewer_district"] = _is_true(row.get("in_sewer_district"))
    nrod = _finite(row.get(NROD_SQFT))
    if row.get("jurisdiction") in NROD_ANSWERS and nrod is not None:
        out["protected_water_feature"] = nrod > 0
    if row.get("jurisdiction") in Z_ANSWERS and _answered(row.get("has_z_overlay")):
        out["constrained_sites_overlay"] = _is_true(row.get("has_z_overlay"))
    if row.get("jurisdiction") in GREENWAY_ANSWERS and _answered(row.get(GREENWAY_COLUMN)):
        out["willamette_greenway_zone"] = _is_true(row.get(GREENWAY_COLUMN))
    return out


def _layer_id(row: Mapping[str, Any]) -> str | None:
    try:
        return layer_id_for(str(row.get("jurisdiction")))
    except KeyError:
        return None


def _home_layer(row: Mapping[str, Any], layers: Mapping[str, Layer]) -> Layer | None:
    layer_id = _layer_id(row)
    return layers.get(layer_id) if layer_id is not None else None


def _counts_streets(row: Mapping[str, Any], layers: Mapping[str, Layer] | None) -> bool:
    """Whether the lot's own code makes a corner of ANY two street frontages.

    True where the jurisdiction's ``corner_lot`` definition is the
    ``frontage_count`` test (:mod:`flats.rules.definitions`) -- Gresham's
    "a lot that has frontage on two or more streets", which asks nothing
    about the streets meeting, so a through lot is a corner there. Every
    other code read asks for intersecting or adjacent frontages, which a
    through lot does not have. Definitions are the layer's own or adopted by
    ``definitions_from``, as :meth:`~flats.rules.resolver.RuleSet.definitions_for`
    walks them; without ``layers`` the question is not asked.
    """
    if layers is None:
        return False
    queue = [_layer_id(row)]
    seen: set[str] = set()
    while queue:
        current = queue.pop(0)
        if current is None or current in seen or current not in layers:
            continue
        seen.add(current)
        defn = layers[current].definitions.get("corner_lot")
        if defn is not None:
            return getattr(defn, "test", None) == "frontage_count"
        queue.extend(layers[current].definitions_from)
    return False


def _boundary_of_one_street(edges: Sequence[Sequence[Any]]) -> list[Side]:
    """The lot's ring as a definition reads it, every street edge on the one
    street (``one_street``): length, direction and what each line abuts."""
    out: list[Side] = []
    for e in edges:
        x1, y1, x2, y2 = (float(v) for v in e[:4])
        cls = e[4] if len(e) >= 5 else ""
        abuts = Abuts.street if cls == STREET_CLASS else Abuts.alley if cls == ALLEY_CLASS else Abuts.none
        out.append(
            Side(
                length_ft=math.hypot(x2 - x1, y2 - y1),
                bearing_deg=math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0,
                abuts=abuts,
                street_id="street" if abuts is Abuts.street else "",
            )
        )
    return out


def _corner_lot_definition(row: Mapping[str, Any], layers: Mapping[str, Layer] | None) -> Definition | None:
    """The ``corner_lot`` test the lot's code writes: its own layer's, or the
    first adopted through ``definitions_from`` (as :func:`_counts_streets`
    walks them). None where the code writes none, or without ``layers``."""
    if layers is None:
        return None
    queue = [_layer_id(row)]
    seen: set[str] = set()
    while queue:
        current = queue.pop(0)
        if current is None or current in seen or current not in layers:
            continue
        seen.add(current)
        defn = layers[current].definitions.get("corner_lot")
        if defn is not None:
            return defn
        queue.extend(layers[current].definitions_from)
    return None


def _bend_is_no_corner(row: Mapping[str, Any], layers: Mapping[str, Layer] | None) -> bool:
    """Whether the lot's own code leaves a bend in ONE street unmade a corner.

    A code that writes a ``corner_lot`` test (Portland, Gresham, Oregon City,
    Beaverton, Clackamas County) is asked through
    :func:`flats.rules.definitions.decide` on the lot's ring with every street
    edge one street: False means the code reads the bend as one street. A code
    that answers True (Portland's curve of 120 degrees or less, Gresham's
    delta of 60) governs its own lot, and so does one that cannot answer
    (``None``). A curve clause measured as ONE angle across the frontage is
    pulled in by :data:`~flats.geom.frontage_curve.BAND_DEG`, the digitising
    error: a curve within a degree of the ceiling is a bend. A jurisdiction
    that writes no test is silent, and Steph's 2026-10-09 ruling takes the
    more conservative reading with a flag: one street name on one run is a
    bend. Without ``layers`` the question is not asked.
    """
    if layers is None:
        return False
    defn = _corner_lot_definition(row, layers)
    if defn is None:
        return True
    ring = _boundary_of_one_street(json.loads(row.get("edges_json") or "[]"))
    if defn.curve_by == "vertex":
        return decide({"corner_lot": defn}, "corner_lot", ring) is False
    # A curve clause written as ONE angle across the whole curve is
    # measured on the lot's frontage, not bend by bend.
    plain = dataclasses.replace(defn, curve_at_or_below_deg=None, curve_by="vertex")
    return decide({"corner_lot": plain}, "corner_lot", ring) is False and not makes_corner(
        defn.curve_by,
        defn.curve_at_or_below_deg or 0.0,
        inclusive=defn.curve_inclusive,
        inside_only=defn.curve_inside_only,
        edges_json=row.get("edges_json"),
        margin_deg=BAND_DEG,
    )


def curve_on_the_line(row: Mapping[str, Any], layers: Mapping[str, Layer] | None) -> tuple[float, float] | None:
    """``(measured angle, the clause's ceiling)`` when the lot's code writes a
    curve clause measured as one angle and the lot lies within
    :data:`~flats.geom.frontage_curve.BAND_DEG` of its ceiling, else None.
    Called on a lot already read as a bend: the flag says which way the
    reading would have gone without the margin (CURVE-ON-THE-LINE)."""
    defn = _corner_lot_definition(row, layers)
    if defn is None or defn.curve_by == "vertex" or defn.curve_at_or_below_deg is None:
        return None
    angle = angle_of(defn.curve_by, inside_only=defn.curve_inside_only, edges_json=row.get("edges_json"))
    if angle is None or abs(angle - defn.curve_at_or_below_deg) > BAND_DEG:
        return None
    return round(angle, 2), float(defn.curve_at_or_below_deg)


def read_as_bend(row: Mapping[str, Any], layers: Mapping[str, Layer] | None) -> bool:
    """Whether a lot s4 read as a corner is ONE street that bends, and is
    screened as one front (:data:`~flats.score.screen.CORNER_READ_AS_BEND`).

    All of: the street directions pass the corner test
    (:func:`~flats.geom.corner.two_streets`), every street edge lies on one
    street (``one_street``, :mod:`flats.geom.one_street`), and the lot's code
    states no corner test that would make the bend a corner
    (:func:`_bend_is_no_corner`), and the street edges are ONE unbroken run
    of the ring (:func:`~flats.geom.frontage_curve.is_unbroken`) -- one name
    on two fronts parted by a rear or side line is two fronts, not a bend.
    Steph, 2026-10-09: where the code is silent, take the more conservative
    reading, with a flag.
    """
    bearings = json.loads(row.get("front_bearings_json") or "[]")
    return (
        len(bearings) >= 2
        and row.get("one_street") is True
        and two_streets(bearings)
        and is_unbroken(row.get("edges_json"))
        and _bend_is_no_corner(row, layers)
    )


def _map_code_facts(row: Mapping[str, Any], layers: Mapping[str, Layer]) -> dict[str, bool]:
    """The site facts the lot's own map code settles (an alias ruling's
    ``observes``): Fairview's ``FLX`` IS the VC flex area, so a lot mapped
    with it holds ``inside_mapped_use_area``. True only -- the aliased
    block's own code says nothing about where the area stops."""
    home = _home_layer(row, layers)
    if home is None or row.get("zone") is None:
        return {}
    return {name: True for name in home.observed_by_code(str(row.get("zone")))}


def _drawn_facts(row: Mapping[str, Any], layers: Mapping[str, Layer]) -> dict[str, bool]:
    """The site facts an area the lot's layer traced settles (see
    :class:`~flats.rules.model.DrawnArea`), for a lot of a zone the area
    names. :func:`observed_facts` keeps a True a map code already holds."""
    home = _home_layer(row, layers)
    if home is None or not home.drawn_areas or row.get("zone") is None:
        return {}
    zone = screened_zone(row, layers)
    areas = [a for a in home.drawn_areas.values() if zone in a.zones]
    lot_wkb = row.get("lot_wkb")
    if not areas or not lot_wkb:
        return {}
    import shapely

    lot_geom = shapely.from_wkb(lot_wkb)
    out: dict[str, bool] = {}
    for area in areas:
        got = observed_drawn(lot_geom, load_area(area.file))
        if got is not None:
            out[area.condition] = got
    return out


def screened_zone(row: Mapping[str, Any], layers: Mapping[str, Layer] | None) -> str:
    """The zone block the lot screens under: its map code, or the block an
    alias ruling names (``FLX`` -> ``VC``), as normalize assigns it."""
    code = str(row.get("zone"))
    home = _home_layer(row, layers) if layers is not None else None
    return (home.holds(code) or code) if home is not None else code


def _normaliser(layers: Mapping[str, Layer]) -> Callable[[str, str], str | None]:
    """A neighbour's map code spelled the way ITS layer screens it, or None
    where the corpus has no layer for its jurisdiction (see
    :func:`_neighbour_facts`)."""

    def normalise(neighbour_juris: str, raw: str) -> str | None:
        try:
            layer = layers.get(layer_id_for(neighbour_juris))
        except KeyError:
            return None
        if layer is None:
            return None
        code, held = zone_for(layer, raw)
        return held or code

    return normalise


def _across_clear(
    row: Mapping[str, Any], n_edges: int, layers: Mapping[str, Layer] | None
) -> tuple[bool, ...]:
    """Per s4 edge: a street line surely facing none of the zones the lot's
    layer names for its across-the-street setback
    (:func:`flats.geom.neighbour.street_lines_clear`, Portland
    33.130.215.B.1.b). All False without the corpus, without s4's
    ``street_across_json`` (a stage file older than the column: nothing
    read across the street), where the record does not match the edges,
    and where the lot's layer declares no across-the-street list."""
    none = (False,) * n_edges
    raw = row.get("street_across_json")
    if layers is None or not raw:
        return none
    home = _home_layer(row, layers)
    if home is None:
        return none
    rule = next((home.neighbours[c] for c in ACROSS_STREET_CONDITIONS if c in home.neighbours), None)
    if rule is None:
        return none
    across = json.loads(raw)
    if not isinstance(across, list) or len(across) != n_edges:
        return none
    return street_lines_clear(across, rule, str(row.get("jurisdiction")), _normaliser(layers))


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
    across = json.loads(row["neighbour_zones_json"])
    lines = lines_from_quadfit(across, _normaliser(layers))
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


def _park_facts(row: Mapping[str, Any], edges: Sequence[Any], layers: Mapping[str, Layer]) -> dict[str, bool]:
    """``abuts_park`` for one s4 row, or nothing.

    The lot's layer supplies which ORCA unit types are a park; a layer that
    declares no ``parks:`` block answers nothing. A whole block is read off
    the edge classes rather than off the ORCA column -- no lot line, no park
    across one -- on the same trust (a clean or corner lot) the neighbour
    facts put in s4's street classes.
    """
    home = _home_layer(row, layers)
    if home is None or not home.parks:
        return {}
    all_street = (
        all(str(e[4]) == "F" for e in edges)
        and TIER.get(str(row.get("tier"))) in (Tier.clean, Tier.corner)
    )
    raw = row.get("park_across_json")
    across = json.loads(raw) if raw else None
    return observed_parks(across, home.parks, all_street=all_street)


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
    #: The lot ground beyond 200 ft of the named streets, where the code
    #: asks for the dwelling within that reach (``reach_off_wkb``,
    #: :mod:`flats.geom.named_street`); taken off like the carve. None
    #: elsewhere.
    reach_off: Any = None
    #: The ground too steep to build or park on (:func:`with_steep`, Steph
    #: 2026-10-04): taken off the envelope and the court's ground like the
    #: carve, but not off the yard an outdoor area may use -- a code's open
    #: space may slope. None where nothing measured it or none is steep.
    steep: Any = None
    #: Where a rear alley that runs only PART of the rear line runs, per rear
    #: line (:func:`flats.geom.alley.rear_cover_runs`); empty where the alley
    #: runs the whole line, is not at the rear, or nothing measured it.
    #: :func:`screen_lot` measures the run behind each envelope from it.
    rear_runs: tuple[Any, ...] = ()
    #: The same lot read without the street lines only a private drive
    #: makes (:func:`drive_reading`): :func:`screen_lot` screens both and
    #: keeps the worse answer -- the better where ``second_better``. None
    #: where no drive's standing is in doubt.
    second: "QuadfitLot | None" = None
    #: The applicant chooses between the two readings (``private_drives.
    #: access_choice``), so :func:`screen_lot` keeps the better.
    second_better: bool = False
    #: Lines the car may come in from that are not front lot lines: a
    #: private road the code does not count as a street for the yards
    #: (Steph, 2026-09-30), as ``(x1, y1, x2, y2)``; and their directions,
    #: which the court beside the building is searched at. Empty on every
    #: other lot.
    access: tuple[tuple[float, float, float, float], ...] = ()
    access_bearings: tuple[float, ...] = ()
    #: How far inside the street lot lines a sidewalk easement is taken to
    #: reach, at its worst (:func:`with_sidewalk_easement`): every street
    #: setback is measured from there. None where the code asks nothing of
    #: one, or nothing was read.
    sidewalk_easement_ft: float | None = None


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


def lot_edges(
    row: Mapping[str, Any],
    geom: Any = None,
    corridors: Sequence[CorridorMap] = (),
    layers: Mapping[str, Layer] | None = None,
) -> LotEdges | None:
    """s4's edge record as the envelope reads it, or None where s4 traced none.

    The class letters map one to one, but for the alley: s4 records it as
    ``A`` whatever side of the lot it runs along, and the corpus holds the
    alley rules per line (``alley_at_rear`` on the rear setback,
    ``setback_alley_side_ft`` for the side), so the edge is named rear or
    side by the same bearing test the alley facts use and carries the flag.

    With the corridor maps in hand, a street edge read surely off every Map
    130-1 stretch serving the lot carries ``off_corridor``
    (:func:`flats.geom.corridor.off_corridor_lines`), for
    ``setback_street_off_corridor_ft``. Without them no edge does.

    With the corpus in hand and s4's ``street_across_json`` on the row, a
    street edge whose every ray across the street found a zone the lot's
    layer does not name for its across-the-street setback carries
    ``across_clear`` (:func:`_across_clear`), for
    ``setback_street_across_nonresidential_ft``. Without either, no edge does.
    """
    raw = json.loads(row.get("edges_json") or "[]")
    if not raw:
        return None
    bearings = tuple(float(b) for b in json.loads(row.get("front_bearings_json") or "[]"))
    named = iter(alley_lines(raw, bearings))
    # Where along each alley edge the alley runs (FOLLOWUPS 3(e)); "" on an
    # alley edge with none on record, so the envelope vouches for no stretch.
    cover = _cover(row, raw) or [None] * len(raw)
    off = off_corridor_lines(raw, _layer_id(row), corridors) if corridors else (False,) * len(raw)
    clear = _across_clear(row, len(raw), layers)
    # Each street line's class rank off the city's TSP map
    # (:func:`with_local_street`); none where no map serves the lot.
    ranks = json.loads(row.get("street_ranks_json") or "[]")
    if len(ranks) != len(raw):
        ranks = [None] * len(raw)
    edges: list[Edge] = []
    for (x1, y1, x2, y2, letter), stretch, off_line, clear_line, rank in zip(
        raw, cover, off, clear, ranks, strict=True
    ):
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
                cover=(stretch or "") if letter == ALLEY_CLASS else None,
                off_corridor=bool(off_line),
                across_clear=bool(clear_line) and letter == STREET_CLASS,
                street_rank=int(rank) if rank is not None and letter == STREET_CLASS else None,
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


def _yard(rules: ZoneResolution, name: str) -> float | None:
    """One yard as the envelope cuts it: zero where the code exempts it, the
    number where it states one, None where it states none."""
    if name in set(rules.exempted):
        return 0.0
    got = rules.get(name)
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return None
    return float(got)


def setbacks_for(
    rules: ZoneResolution,
    plain: ZoneResolution | None = None,
    alleyed: ZoneResolution | None = None,
) -> Setbacks | None:
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

    ``plain`` is the same lot and design resolved with ``alley_at_rear``
    False, handed over where ``rules`` hold it True and the lot has a rear
    line off the alley (:func:`envelope_for`). Its rear setback is the
    ordinary one, for that line; ``rules``' rear -- the alley's variant,
    exempt or a number -- goes to :attr:`Setbacks.alley_rear_ft`, for the
    rear edges on the alley. Where the two agree nothing is split. Where
    ``plain`` states no rear number the line off the alley has none, and the
    answer is None like any other yard without one.

    ``alleyed`` is the other way round: the same lot and design resolved
    with ``alley_at_rear`` True, handed over where ``rules`` hold it False
    because the alley runs only PART of the rear line (:func:`envelope_for`).
    ``rules``' rear stays the ordinary one; ``alleyed``'s goes to
    :attr:`Setbacks.alley_rear_ft`, which the envelope cuts along the
    stretches s4's cover found the alley on and nowhere else
    (:func:`flats.geom.envelope._pieces`). Where ``alleyed`` states no rear
    number, or the same one, nothing is split: every rear line keeps the
    ordinary rear, the answer before 2026-09-29.
    """

    def number(name: str) -> float | None:
        return _yard(rules, name)

    front, side, rear = (number(f"setback_{c}_ft") for c in ("front", "side", "rear"))
    if front is None or side is None or rear is None:
        return None
    total = number("setback_side_total_ft")
    if total is not None:
        side = max(side, total / 2)
    alley_side = number("setback_alley_side_ft")
    street_side = number("setback_street_side_ft")
    # The street line off a mapped corridor (Portland Map 130-1): the zone's
    # one number for a street lot line off the stretch. Passed only where the
    # zone states no street-side setback -- then it stands in for the front
    # number on any street line, which is what it is; beside a street-side
    # number it would have to say which of the two it replaces, and it is
    # dropped rather than guessed (every street line keeps its class's).
    off_corridor = number("setback_street_off_corridor_ft") if street_side is None else None
    # The side alley line's default is the rear as ``rules`` read it, the
    # same whether or not a rear line off the alley splits the rear below.
    alley_side_ft = max(side, rear) if alley_side is None else alley_side
    alley_rear: float | None = None
    if plain is not None:
        ordinary = _yard(plain, "setback_rear_ft")
        if ordinary is None:
            return None
        if ordinary != rear:
            alley_rear, rear = rear, ordinary
    elif alleyed is not None:
        on_alley = _yard(alleyed, "setback_rear_ft")
        if on_alley is not None and on_alley != rear:
            alley_rear = on_alley
    # The street line across from no residential zone (Portland
    # 33.130.215.B.1.b): the zone's plain street row, on a line off the
    # corridor whose every ray across the street was read clear. Passed on
    # the same terms as the off-corridor number, which it refines.
    clear = (
        number("setback_street_across_nonresidential_ft")
        if street_side is None and off_corridor is not None
        else None
    )
    return Setbacks(
        front_ft=front,
        side_ft=side,
        rear_ft=rear,
        street_side_ft=street_side,
        alley_side_ft=alley_side_ft,
        street_off_corridor_ft=off_corridor,
        alley_rear_ft=alley_rear,
        street_clear_ft=clear,
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
    #: Where the parking court may stand (FOLLOWUPS 33): the lot cut by
    #: every yard but the rear, the carve taken off too -- the envelope plus
    #: the rear strip the screen credits the court with
    #: (:func:`flats.score.screen._court_beyond_rear`). Where the envelope
    #: is s5o's, no yard is known and the lot less the carve stands in: the
    #: court at least stays on the lot. None without a lot polygon.
    ground: Any = None

    @property
    def sqft(self) -> float:
        return 0.0 if self.geom is None or self.geom.is_empty else float(self.geom.area)


def rear_off_alley(edges: LotEdges | None) -> bool:
    """Whether this lot has a rear edge on the alley AND a rear edge off it
    -- two rear lines the rules' one rear setback cannot both describe
    (FOLLOWUPS 12(b)): a corner lot's line opposite the side street, the
    second leg of a jogged rear. Read on the edges as the envelope is cut,
    after a named front has turned the line opposite the side street into a
    side (:func:`flats.geom.corner.name_front`)."""
    if edges is None:
        return False
    rear = [e for e in edges.edges if e.cls is EdgeClass.rear]
    return any(e.alley for e in rear) and any(not e.alley for e in rear)


def part_rear_alley(lot: QuadfitLot) -> bool:
    """Whether this lot's rear alley runs only PART of its rear line and the
    envelope can cut that line stretch by stretch (FOLLOWUPS 3, Steph's
    careful reading of 2026-09-28): s4 names a rear line an alley line, the
    registry's ``alley_at_rear`` is off because the cover does not vouch for
    the whole line, the lot is cut with per-edge strips, and the cover
    vouches for at least one stretch of a rear alley edge. A tier C lot is
    shrunk uniformly by its largest yard, and there is no stretch to cut; a
    lot with no cover on record has no stretch either, and keeps the
    ordinary rear on the whole line, the court charged against it."""
    if not lot.facts.alley_at_rear or lot.facts.alley_rear_whole or lot.edges is None:
        return False
    if lot.edges.tier not in (Tier.clean, Tier.corner):
        return False
    return any(
        e.alley and e.cls is EdgeClass.rear and e.cover and cover_stretches(e.length_ft, e.cover)
        for e in lot.edges.edges
    )


def envelope_for(
    lot: QuadfitLot,
    rules: ZoneResolution,
    plain: ZoneResolution | None = None,
    alleyed: ZoneResolution | None = None,
) -> Envelope:
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

    ``plain`` is the same lot and design resolved with ``alley_at_rear``
    False (:func:`screen_lot` resolves it where ``rules`` hold the fact
    True). Read only on a lot with a rear line on the alley and another off
    it (:func:`rear_off_alley`): the alley's rear setback -- Portland's
    waiver, Gresham's rear-with-alley number -- goes to the rear edges on
    the alley and the ordinary one to the rest (:func:`setbacks_for`). A
    caller that hands no ``plain`` for such a lot gets quadfit's envelope
    where the alley's rear is an exemption, as before 2026-09-29.

    ``alleyed`` is the same lot and design resolved with ``alley_at_rear``
    True, read only on a lot whose alley runs PART of its rear line
    (:func:`part_rear_alley`): the covered stretches take its rear, the rest
    of the line the larger of it and the ordinary rear (:func:`setbacks_for`).
    The court is then charged against the smaller strip: where the alley's
    rear is the smaller the envelope reports it as its rear cut
    (:attr:`Envelope.rear_cut_ft`), since behind the covered stretch that is
    all the envelope lost -- charging the ordinary rear there would credit
    the court with ground the envelope still holds.
    """
    strip = lot_line_buffer_ft(rules)
    in_yards = slope_rules().steep_in_setbacks
    steep = lot.steep if in_yards else _within(lot.steep, lot.envelope)
    taken = _taken(lot, steep)
    on_lot = None if lot.lot_geom is None else _less_carve(lot.lot_geom, taken)
    if on_lot is not None and strip > 0:
        # No line named: keep the strip off every line (conservative).
        on_lot = on_lot.buffer(-strip)
    fallback = None if lot.envelope is None else _less_carve(_less_carve(lot.envelope, lot.steep), lot.reach_off)
    quadfit = Envelope(fallback, lot.facts.envelope_rear_ft, "quadfit", ground=on_lot)
    if lot.lot_geom is None or lot.edges is None or lot.edges.tier is Tier.landlocked:
        return quadfit
    split = rear_off_alley(lot.edges)
    part = alleyed is not None and part_rear_alley(lot)
    setbacks = setbacks_for(rules, plain if split else None, alleyed if part else None)
    if setbacks is None:
        return quadfit
    # A utility easement the code forbids building on, assumed along every
    # street line where Steph's ruling reaches the lot (FOLLOWUPS 43).
    setbacks = easement.floored(setbacks, lot.facts.easement_street_ft)
    strips = lot.edges.tier in (Tier.clean, Tier.corner)
    if split and plain is None and strips and "setback_rear_ft" in rules.exempted:
        # The exemption is about the rear line on the alley; a rear line that
        # is not on it has a setback this resolution does not carry, and the
        # caller did not resolve it (``plain``).
        return quadfit
    if strip > 0:
        # A side yard narrower than the planted strip: the court and the
        # lane are searched inside the envelope, so the envelope's sides
        # stand the strip off (conservative -- the building alone could go
        # nearer).
        setbacks = dataclasses.replace(
            setbacks,
            side_ft=max(setbacks.side_ft, strip),
            alley_side_ft=None
            if setbacks.alley_side_ft is None
            else max(setbacks.alley_side_ft, strip),
        )
    if not in_yards and lot.steep is not None and not lot.steep.is_empty:
        # Steep ground in the setbacks is left to the grader (Steph
        # 2026-10-04): only what lies where the building may stand comes
        # off, the court's ground included.
        taken = _taken(lot, _within(lot.steep, buildable(lot.lot_geom, lot.edges, setbacks)))
    geom = buildable(lot.lot_geom, lot.edges, setbacks, less=taken)
    cut = None if strips else setbacks.largest_ft
    if part and setbacks.alley_rear_ft is not None and setbacks.alley_rear_ft < setbacks.rear_ft:
        cut = setbacks.alley_rear_ft
    # The court may use the rear yard, less any planted strip the code keeps
    # between parking and the line (``parking_lot_line_buffer_ft``).
    open_rear = dataclasses.replace(
        setbacks,
        rear_ft=strip,
        alley_rear_ft=None if setbacks.alley_rear_ft is None else strip,
    )
    ground = buildable(lot.lot_geom, lot.edges, open_rear, less=taken)
    return Envelope(geom, cut, "flats", setbacks, ground)


def _taken(lot: QuadfitLot, steep: Any = None) -> Any:
    """What nothing is built or parked on: the carve, and the steep ground
    (``steep``, or the lot's own where the caller hands none)."""
    steep = lot.steep if steep is None else steep
    carve = lot.carve
    if lot.reach_off is not None:
        carve = lot.reach_off if carve is None or carve.is_empty else carve.union(lot.reach_off)
    if steep is None or steep.is_empty:
        return carve
    if carve is None or carve.is_empty:
        return steep
    return carve.union(steep)


def _within(steep: Any, where: Any) -> Any:
    """The steep ground inside ``where``; all of it where ``where`` is
    unknown (conservative)."""
    if steep is None or steep.is_empty or where is None:
        return steep
    return steep.intersection(where)


def _less_carve(geom: Any, carve: Any) -> Any:
    """The lot less the carve: the ground nothing is built or parked on."""
    if carve is None or carve.is_empty:
        return geom
    return geom.difference(carve)


def _cover(row: Mapping[str, Any], edges: Sequence[Any]) -> list[str | None] | None:
    """s4's ``alley_cover_json`` on one stage-file row, parallel to ``edges``
    (:func:`flats.geom.alley.decode_cover`); None where s4 predates the
    column or the record does not match the edges."""
    return decode_cover(row.get("alley_cover_json"), len(edges))


def _side_alley_along(row: Mapping[str, Any]) -> bool:
    """:func:`flats.geom.alley.side_alley_along` on one stage-file row; False
    where s4 predates ``alley_cover_json`` (nothing measured the stretch)."""
    edges = json.loads(row.get("edges_json") or "[]")
    return side_alley_along(
        edges,
        json.loads(row.get("front_bearings_json") or "[]"),
        _cover(row, edges),
    )


#: s4's ``street_kind_json`` values for a street edge that is a street by no
#: code: the only centreline within 50 ft is a private road or an unnamed
#: drive (RLIS TYPE 1700 / 1800) that runs through the lot itself, or across
#: someone else's built parcel beyond the line -- a school's bus loop, a park's
#: service road, a mobile-home park's aisle behind the rear fence. Wilsonville
#: 4.001(157) and Wood Village 720.030 count a private drive the lot ABUTS;
#: neither counts one the lot only sits near.
DOUBTFUL_STREET_KINDS: frozenset[str] = frozenset({"drive_on_lot", "drive_off_lot"})
#: ... and every street edge only a private road or drive makes, the lot's
#: own or not.
DRIVE_STREET_KINDS: frozenset[str] = DOUBTFUL_STREET_KINDS | {"drive"}


def _street_kinds(row: Mapping[str, Any]) -> list[Any] | None:
    raw = row.get("street_kind_json")
    if not raw:
        return None
    try:
        kinds = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return kinds if isinstance(kinds, list) else None


def drive_reading(
    row: Mapping[str, Any], layers: Mapping[str, Layer] | None
) -> tuple[str | None, str | None]:
    """Which of s4's second readings (``sans_drive_json``) this lot is
    screened on, and how it stands to the first: ``worse`` (both screened,
    the worse kept), ``replace`` (the only reading) or ``better`` (both
    screened, the better kept).

    * A street line only a drive on other land makes (``drive_on_lot`` /
      ``drive_off_lot``) is a street by no code, but the reading could be
      s4's error either way: the lot is screened as s4 read it AND without
      those lines, and the worse answer kept.
    * A private drive the lot abuts (``drive``): where the lot's code counts
      it (``private_drives.street: true``) the line is a street and nothing
      more is asked; where the code says a street is a public way
      (``street: false``) the line is an ordinary lot line, and the lot is
      screened on that reading alone; where the code is silent (no
      ``private_drives``), both ways, the worse kept. Where the line is a
      front only if the car comes in from it (``access_choice``), both
      ways, the better kept.

    ``(None, None)``: one reading, s4's own. The key is ``drives`` where
    the drives go too and s4 wrote a separate reading for that, else
    ``doubtful``.
    """
    kinds = _street_kinds(row)
    if not kinds:
        return None, None
    doubtful = any(k in DOUBTFUL_STREET_KINDS for k in kinds)
    drives = any(k == "drive" for k in kinds)
    if not (doubtful or drives):
        return None, None
    home = _home_layer(row, layers) if layers is not None else None
    ruling = home.private_drives if home is not None else None
    if doubtful:
        counted = ruling is not None and ruling.street
        return ("doubtful" if not drives or counted else "drives"), "worse"
    if ruling is None:
        return "drives", "worse"
    if not ruling.street:
        return "drives", "replace"
    if getattr(ruling, "access_choice", False):
        return "drives", "better"
    return None, None


def _sans_row(row: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    """The stage-file row as s4 would have written it without the street
    lines ``key`` names (``sans_drive_json``), or None where s4 wrote no
    such reading."""
    raw = row.get("sans_drive_json")
    if not raw:
        return None
    try:
        got = json.loads(raw)
    except (TypeError, ValueError):
        return None
    alt = got.get(key) if isinstance(got, dict) else None
    if not isinstance(alt, dict) or "tier" not in alt:
        return None

    def dumped(v: Any) -> str | None:
        return None if v is None else json.dumps(v)

    return {
        **row,
        "tier": alt["tier"],
        "edges_json": json.dumps(alt.get("edges") or []),
        "front_bearings_json": json.dumps(alt.get("front_bearings") or []),
        "frontage_ft": alt.get("frontage_ft"),
        "lot_width_ft": alt.get("lot_width_ft"),
        "lot_depth_ft": alt.get("lot_depth_ft"),
        "fronts_cul_de_sac": bool(alt.get("fronts_cul_de_sac")),
        "alley_cover_json": dumped(alt.get("alley_cover")),
        "alley_width_ft": alt.get("alley_width_ft"),
        "neighbour_zones_json": dumped(alt.get("neighbour_zones")),
        "park_across_json": dumped(alt.get("park_across")),
        "street_kind_json": None,
        "street_ranks_json": None,
        "sans_drive_json": None,
    }


def lot_from_row(
    row: Mapping[str, Any],
    layers: Mapping[str, Layer] | None = None,
    corridors: Sequence[CorridorMap] = (),
) -> QuadfitLot:
    """Build the screen's inputs for one stage-file row.

    ``layers`` is the loaded corpus, for the neighbour-zoning facts; without
    it those facts are left unasked, as they were before 2026-09-21.
    ``corridors`` likewise for the corridor facts (before 2026-09-27).
    """
    import shapely

    bend = read_as_bend(row, layers)
    if bend:
        row = {**row, "front_bearings_json": json.dumps(json.loads(row["front_bearings_json"])[:1])}
    key, how = drive_reading(row, layers)
    second: QuadfitLot | None = None
    unconfirmed = False
    if key is not None:
        alt = _sans_row(row, key)
        if how == "replace" and alt is not None:
            # The code says a private drive is not a street: that reading
            # is the lot's only one, and the car may still come in off it.
            return _with_access(lot_from_row(alt, layers, corridors), row)
        if how == "better":
            # The drive line is a front only where the car comes in from
            # it: the lot as s4 read it, and -- where a street is left --
            # the lot without it, the better kept. With none left the drive
            # is the lot's only way in, and so its front.
            if alt is not None and alt["tier"] != "D":
                second = lot_from_row(alt, layers, corridors)
        elif alt is None or alt["tier"] == "D":
            # No second reading to screen, or no street left without the
            # drive: nobody can say this lot fronts a street.
            unconfirmed = True
        else:
            second = lot_from_row(alt, layers, corridors)
            if key == "drives":
                second = _with_access(second, row)

    tier = TIER.get(str(row.get("tier")), Tier.irregular)
    frontage = _finite(row.get("frontage_ft"))
    observed = observed_facts(row, layers, corridors)
    lot_wkb = row.get("lot_wkb")
    lot_geom = shapely.from_wkb(lot_wkb) if lot_wkb else None
    edges = lot_edges(row, lot_geom, corridors, layers)
    raw_edges = json.loads(row.get("edges_json") or "[]")
    s4_alley = (
        observed_alley(raw_edges, json.loads(row.get("front_bearings_json") or "[]"))
        if raw_edges
        else {}
    )
    facts = LotFacts(
        lot_sqft=_finite(row.get("area_sqft")) or 0.0,
        frontage_ft=frontage if frontage is not None else 0.0,
        lot_width_ft=_finite(row.get("lot_width_ft")),
        lot_depth_ft=_finite(row.get("lot_depth_ft")),
        geometry=tier,
        # s5 recorded its cut under s4's own class letter, so the key is s4's
        # reading of the rear line, not the registry's stricter one.
        envelope_rear_ft=carved_rear_ft(row, s4_alley),
        # The alley behind or beside the lot and how wide s4 measured it: the
        # court it feeds (FOLLOWUPS 4(b), :func:`flats.score.paper.court_depth`,
        # :func:`flats.score.paper.side_column`). A rear alley on s4's three
        # rays of five is enough to reach the court from (the court's own
        # aisle meets it wherever it runs); the row of stalls backs out into
        # it only where it runs the whole rear line (FOLLOWUPS 3(d)) -- the
        # registry's ``alley_at_rear``, :func:`flats.geom.alley.registry_alley`.
        alley_at_rear=bool(s4_alley.get("alley_at_rear")),
        alley_rear_whole=bool(observed.get("alley_at_rear")),
        # A side alley feeds the court only where it runs the whole side
        # line (FOLLOWUPS 3(c)): s4 names a line an alley line on three rays
        # of five, and a stub along half of it would park the court against
        # a fence. The registry's ``alley_at_side`` -- the line abuts an
        # alley, for its setback -- is left as s4 read it.
        alley_at_side=bool(observed.get("alley_at_side")) and _side_alley_along(row),
        alley_width_ft=_finite(row.get("alley_width_ft")),
        # Two streets that really are two: the side street may take the
        # driveway (:func:`flats.score.paper.side_street_fed`).
        corner=is_corner(edges),
        # A street line only a drive makes, with no reading of the lot
        # without it to screen, or none with a street left (FOLLOWUPS 4).
        street_unconfirmed=unconfirmed,
        transit_ft=transit_from_row(row),
        # What a city's net area may take off the lot (option A, Steph
        # 2026-10-02): an existing lot dedicates nothing, so only what s5o
        # measured comes off it.
        net_deductions=measured_deductions(row) or None,
        # A permit to build on mapped stream, wetland, habitat or flood
        # ground: a closer look (FOLLOWUPS 42(b)/(c)).
        resource_permits=permits_on(row),
        corner_read_as_bend=bend,
        curve_on_the_line=curve_on_the_line(row, layers) if bend else None,
    )
    juris = str(row.get("jurisdiction"))
    try:
        layer_id: str | None = layer_id_for(juris)
    except KeyError:
        layer_id = None
    wkb = row.get("wkb")
    envelope = shapely.from_wkb(wkb) if wkb else None
    carve_wkb = row.get("carve_wkb")
    return QuadfitLot(
        tlid=str(row["TLID"]),
        jurisdiction=juris,
        zone=screened_zone(row, layers),
        layer_id=layer_id,
        facts=facts,
        observed=observed,
        front_bearings=tuple(float(b) for b in json.loads(row.get("front_bearings_json") or "[]")),
        envelope=envelope,
        lot_geom=lot_geom,
        edges=edges,
        carve=shapely.from_wkb(carve_wkb) if carve_wkb else None,
        reach_off=shapely.from_wkb(row["reach_off_wkb"]) if row.get("reach_off_wkb") else None,
        rear_runs=(
            rear_cover_runs(
                raw_edges,
                json.loads(row.get("front_bearings_json") or "[]"),
                _cover(row, raw_edges),
            )
            if facts.alley_at_rear and not facts.alley_rear_whole
            else ()
        ),
        second=second,
        second_better=how == "better" and second is not None,
        sidewalk_easement_ft=_finite(row.get("sidewalk_easement_ft")),
    )


def _with_access(lot: QuadfitLot, row: Mapping[str, Any]) -> QuadfitLot:
    """``lot`` -- read with a private road as an ordinary lot line -- with
    the road given back as a way in (:attr:`QuadfitLot.access`): every
    street line and direction s4 read on ``row``, the drive's among them.
    The yards stay as ``lot`` cuts them; only where the court's drive may
    come from changes (Steph, 2026-09-30)."""
    raw = json.loads(row.get("edges_json") or "[]")
    kinds = _street_kinds(row) or []
    # A line only a drive on other land (or across the lot itself) makes is
    # no road the lot abuts, and no way in.
    doubtful = [i < len(kinds) and kinds[i] in DOUBTFUL_STREET_KINDS for i in range(len(raw))]
    lines = tuple(
        (float(e[0]), float(e[1]), float(e[2]), float(e[3]))
        for e, bad in zip(raw, doubtful)
        if len(e) >= 5 and e[4] == "F" and not bad
    )
    bearings = ()
    if not any(doubtful):
        bearings = tuple(float(b) for b in json.loads(row.get("front_bearings_json") or "[]"))
    return dataclasses.replace(lot, access=lines, access_bearings=bearings)


def _street_lines(lot: QuadfitLot) -> tuple[tuple[float, float, float, float], ...]:
    """The lines the car may come in from: the front lot lines, and a
    private road the yards do not count (:attr:`QuadfitLot.access`)."""
    fronts: tuple[tuple[float, float, float, float], ...] = ()
    if lot.edges is not None:
        fronts = tuple((e.x1, e.y1, e.x2, e.y2) for e in lot.edges.of_class(EdgeClass.front))
    return fronts + tuple(a for a in lot.access if a not in fronts)


def transit_from_row(row: Mapping[str, Any]) -> tuple[tuple[str, float], ...]:
    """The lot's distances to transit, where the row carries them.

    Joined from the per-release distance file (:mod:`flats.ingest.transit`,
    ``--transit``). A measure the row lacks is left out, so a band on it
    stays unplaceable rather than reading the lot as far from transit.
    """
    out = []
    for name in TRANSIT_MEASURES:
        got = _finite(row.get(name))
        if got is not None and got >= 0:
            out.append((name, got))
    return tuple(out)


def iter_rows(
    s4: Path = S4_LOTS,
    s5o: Path = S5O_LOTS,
    *,
    transit: Path | None = None,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 0,
    jurisdictions: Iterable[str] = (),
    zones: Iterable[str] = (),
    tlids: Iterable[str] = (),
    streets: Path | None = None,
) -> Iterator[dict[str, Any]]:
    """Every lot's bridge row, s4 facts joined to s5o's envelope on TLID.

    Read from two files rather than one because s4 is re-run alone (a width
    or alley refresh) and s5o then predates its newest columns -- s7 joins
    them the same way. A column either file lacks is simply absent from the
    row, and :func:`observed_facts` leaves that fact unasked.

    ``jurisdictions``, ``zones`` (``"<jurisdiction>:<zone>"``) and ``tlids``
    select the lots a partial re-screen covers (:mod:`flats.ingest.splice`);
    a lot matching ANY of them is kept, and none given keeps every lot.

    ``streets`` is quadfit s1's street centrelines; with it each row gains
    ``street_end_ft``, the taxlot's distance to the nearest place a street
    ends (:func:`flats.geom.street_end.street_end_column`). Measured after
    the scope is cut, so a partial measures only its own lots.
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
    if transit is not None:
        # Measured once per transit release, keyed by TLID; a lot the file
        # does not hold simply has no distance (:func:`transit_from_row`).
        near = pd.read_parquet(transit, columns=["TLID", *TRANSIT_MEASURES])
        frame = frame.merge(near.drop_duplicates("TLID"), on="TLID", how="left")
    keep = scope_mask(frame, jurisdictions, zones, tlids)
    if keep is not None:
        frame = frame[keep]
    if sample is not None and sample < len(frame):
        frame = frame.sample(n=sample, random_state=seed)
    if limit is not None:
        frame = frame.head(limit)
    if streets is not None:
        frame = frame.assign(
            street_end_ft=street_end_column(frame, streets),
            named_street_ft=named_street_column(frame, streets),
            one_street=one_street_column(frame, streets),
            reach_off_wkb=beyond_reach_column(frame, streets),
        )
    # Every null -- NaN, NaT, pandas' NA -- leaves as None, so the readers
    # above see one shape of "no answer" whatever dtype the column arrived in.
    frame = frame.astype(object).where(frame.notna(), None)
    yield from frame.to_dict("records")


def with_local_street(rows: list[dict[str, Any]], sources: Path | None) -> int:
    """Answer ``local_street`` on every row a city's TSP map serves, in place
    (``local_street_obs``: True, False, or absent), and say how many. The
    same rows carry each street line's class rank (``street_ranks_json``,
    :func:`flats.geom.street_class.street_ranks`) for the lowest-class
    driveway rule.

    Read off the row's own s4 edges, so a lot screened a second way without
    its private drive (:func:`_sans_row`) carries the first reading -- where
    the drive was a street line it has no TSP class, and the fact is absent.
    """
    if sources is None:
        return 0
    maps = load_class_maps(sources)
    if not maps:
        return 0
    answered = 0
    for row in rows:
        layer_id = _layer_id(row)
        if not any(m.covers(layer_id) for m in maps):
            continue
        edges = json.loads(row.get("edges_json") or "[]")
        row["street_ranks_json"] = json.dumps(street_ranks(edges, layer_id, maps))
        got = observed_local_street(edges, layer_id, maps)
        if LOCAL_STREET in got:
            row["local_street_obs"] = got[LOCAL_STREET]
            answered += 1
    return answered


def with_sidewalk_easement(rows: list[dict[str, Any]], sources: Path | None) -> int:
    """Take the worst-case sidewalk easement on every row whose code measures
    a setback from one (:mod:`flats.geom.sidewalk`), in place
    (``sidewalk_easement_ft``), and say how many.

    Only with the snapshot's street centrelines in hand: a line is read as on
    a local street off Metro's TYPE, and without them the run leaves the
    fact unasked rather than take every line at the deepest.
    """
    if sources is None:
        return 0
    asked = [(row, depth_for(_layer_id(row))) for row in rows]
    asked = [(row, d) for row, d in asked if d is not None]
    edges = {id(row): json.loads(row.get("edges_json") or "[]") for row, _ in asked}
    xs = [float(v) for e in edges.values() for line in e for v in (line[0], line[2])]
    ys = [float(v) for e in edges.values() for line in e for v in (line[1], line[3])]
    if not xs:
        return 0
    reach = 2 * FRONT_REACH_FT
    streets = load_streets(sources, (min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach))
    if streets is None:
        return 0
    taken = 0
    for row, depth in asked:
        got = easement_depth_ft(edges[id(row)], depth, streets)
        if got is not None:
            row["sidewalk_easement_ft"] = got
            taken += 1
    return taken


def scope_mask(frame: Any, jurisdictions: Iterable[str] = (), zones: Iterable[str] = (), tlids: Iterable[str] = ()) -> Any:
    """The rows of ``frame`` inside a declared scope, or None for no scope.

    A zone is named with its jurisdiction (``"Wood Village:TC"``) because the
    same code means different districts in different cities.
    """
    juris, pairs, ids = set(jurisdictions), set(zones), set(tlids)
    for z in pairs:
        if ":" not in z:
            raise ValueError(f"zone {z!r}: name it as <jurisdiction>:<zone>")
    if not (juris or pairs or ids):
        return None
    keep = frame["jurisdiction"].isin(juris) | frame["TLID"].isin(ids)
    if pairs:
        keep |= (frame["jurisdiction"].astype(str) + ":" + frame["zone"].astype(str)).isin(pairs)
    return keep


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
    #: The street this corner lot was screened as fronting, where the code
    #: named one (:func:`flats.geom.corner.front_bearings`); None where no
    #: front was named and every street edge is a front.
    front_deg: float | None = None
    #: Where the fit stood the building and its parking, as the lot page
    #: draws it (:func:`drawing_for`); None where the search found no room
    #: at the parking's width at all.
    drawing: dict[str, Any] | None = None
    #: The measurements ``screening`` was made on -- the lot's own, with the
    #: envelope's rear cut and the outdoor square this plan measured -- so a
    #: fact measured after the drawing (:func:`fire_checked`) re-screens on
    #: the same ground. None from a caller that built one by hand.
    facts: LotFacts | None = None
    #: How much bigger the pod could be on this lot, each way
    #: (:func:`flats.score.room.room_for`, FOLLOWUPS 37(ii)): for the pod
    #: report, never read by the colour. None where the fit did not pass,
    #: the lot is red (it stays red whatever the pod's size) or nobody asked.
    room: Room | None = None
    #: Which street each plan of a corner lot took its driveway from and why
    #: (:func:`flats.geom.street_class.access_record`, FOLLOWUPS 49(c)); the
    #: plan this row stands on carries ``won``. None off the named-front path.
    access: tuple[dict[str, Any], ...] | None = None
    #: Why :func:`fire_checked` found no hose route for this plan
    #: (:func:`_fire_why`); a diagnostic column, never read by the colour.
    fire_why: str | None = None


def _room(s: Screened, fitter: Fitter) -> Room | None:
    """:func:`flats.score.room.room_for` for the plan ``s`` took on
    ``fitter``, with the arguments :func:`_screen_on` gave the fit."""
    facts = s.facts if s.facts is not None else s.lot.facts
    return room_for(
        fitter,
        s.design,
        s.rules,
        s.fit,
        carved_rear_ft=s.envelope.rear_cut_ft if s.envelope is not None else None,
        alley=facts.alley,
        corner=facts.corner,
        frontage_ft=facts.frontage_ft,
        street_deg=_access_deg(s.lot, s.front_deg),
    )


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


def _rear_ft(env: Envelope, rules: ZoneResolution) -> float:
    """How deep the strip this envelope lost at the rear is: the recorded
    cut, else the rear setback it was cut with, else the rules' number (0
    where they waive it or state none) -- where :func:`usable_run_ft`
    probes for the envelope behind the alley."""
    if env.rear_cut_ft is not None:
        return float(env.rear_cut_ft)
    if env.setbacks is not None:
        return float(env.setbacks.rear_ft)
    held = rules.get("setback_rear_ft")
    return float(held) if isinstance(held, (int, float)) else 0.0


def _access_deg(here: QuadfitLot, front: float | None) -> tuple[float, ...]:
    """The street directions the court beside the building is searched at:
    the named front, or every street direction and a private road's."""
    if front is not None:
        return (front,)
    return here.front_bearings + tuple(
        b for b in here.access_bearings if b not in here.front_bearings
    )


def _screen_on(
    here: QuadfitLot,
    design: Design,
    config: Configuration,
    got: ZoneResolution,
    env: Envelope,
    front: float | None,
    angles: Sequence[float],
    fitters: dict[Any, Fitter],
    step_deg: float,
    *,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    plan: Any = None,
) -> tuple[Screened, Fitter]:
    """One design screened on one envelope and one named front, for
    :func:`screen_lot` to rank against the others it tries. ``plan`` keys
    the search apart where a through lot's ends are named (FOLLOWUPS 6(i))."""
    key = (env.source, env.setbacks, front, plan)
    if key not in fitters:
        fitters[key] = Fitter(env.geom, angles, ground=env.ground)
    if here.facts.alley_at_rear and not here.facts.alley_rear_whole:
        # A rear alley along PART of the rear line is the court's
        # aisle only where the stretch it runs, with this envelope
        # behind it, is as long as the row (Steph 2026-09-28).
        run = usable_run_ft(here.rear_runs, here.lot_geom, env.geom, _rear_ft(env, got))
        here = dataclasses.replace(
            here, facts=dataclasses.replace(here.facts, alley_rear_run_ft=run)
        )
    facts = dataclasses.replace(here.facts, envelope_rear_ft=env.rear_cut_ft)
    fit = fit_for(
        fitters[key],
        design,
        got,
        placement=False,
        carved_rear_ft=env.rear_cut_ft,
        alley=facts.alley,
        corner=facts.corner,
        frontage_ft=facts.frontage_ft,
        street_deg=_access_deg(here, front),
    )
    if fit.beside and not beside_reaches_street(here, design, got, fit, fitters[key], env):
        # The court beside the building has its aisle in from the street;
        # where the only room for it stands back from the street (the wide
        # back of an L-shaped lot, behind a flag pole) no drive reaches it,
        # so the lot is read on the row behind the building as before.
        fit = fit_for(
            fitters[key],
            design,
            got,
            placement=False,
            carved_rear_ft=env.rear_cut_ft,
            alley=facts.alley,
            corner=facts.corner,
            frontage_ft=facts.frontage_ft,
            street_deg=(),
        )
    base = facts

    def screened(fit: Fit) -> tuple[LotFacts, Screening, Screening]:
        facts = base
        result = screen(got, facts, design, fit, policy=policy, relief=relief, config=config)
        if "open_space_shape" in result.unchecked:
            # The screen's window could not prove the outdoor square; measure it
            # on the lot's own ground and screen again on the answer.
            square = outdoor_square(here, design, got, fit, fitters[key], env)
            if square is not None:
                facts = dataclasses.replace(facts, outdoor_square_ft=square)
                result = screen(
                    got, facts, design, fit, policy=policy, relief=relief, config=config
                )
        shadow = _if_signed(
            got, facts, design, fit, result, policy=policy, relief=relief, config=config
        )
        return facts, result, shadow

    def refit(menu: Sequence[Fix]) -> Fit:
        return fit_for(
            fitters[key],
            design,
            got,
            placement=False,
            carved_rear_ft=env.rear_cut_ft,
            alley=base.alley,
            corner=base.corner,
            frontage_ft=base.frontage_ft,
            street_deg=_access_deg(here, front),
            menu=menu,
        )

    offered = court_across(design, got, base.alley, corner=base.corner).fixes
    facts, result, shadow = screened(fit)
    fit, facts, result, shadow = _other_fixes(
        fit, facts, result, shadow, screened, refit, offered
    )
    return (
        Screened(
            lot=here,
            design=design,
            rules=got,
            config=config,
            fit=fit,
            screening=result,
            signed=shadow,
            angles=len(angles),
            step_deg=step_deg,
            envelope=env,
            front_deg=front,
            facts=facts,
        ),
        fitters[key],
    )


def _other_fixes(
    fit: Fit,
    facts: LotFacts,
    result: Screening,
    shadow: Screening,
    screened: Callable[[Fit], tuple[LotFacts, Screening, Screening]],
    refit: Callable[[Sequence[Fix]], Fit],
    offered: Sequence[Fix],
) -> tuple[Fit, LotFacts, Screening, Screening]:
    """The court's next fix where the one taken fits but fails a rule its
    shape moves (:data:`COURT_SHAPED`) -- a dead end that leaves no outdoor
    square where a deeper aisle would. Each fix the ledger offers after it
    is tried in turn, least paving first; the first that passes every rule
    signed is taken, else the one taken first stands. Every fix tried is
    one the car was seen to use, so a fix taken here is never a court
    nobody drove (Steph 2026-10-03: the least paving the lot holds)."""
    if fit.court_fix is None or fit.beside or fit.column or shadow.triage is Triage.green:
        return fit, facts, result, shadow
    failing = {c.check for c in shadow.checks if c.verdict is CheckVerdict.fails}
    # A court that does not fit was the nearest miss of every fix already.
    if not failing or not failing <= COURT_SHAPED or failing & {"fit_ft", "fit_across_ft"}:
        return fit, facts, result, shadow
    taken = Fix(*fit.court_fix)
    if taken not in offered:
        return fit, facts, result, shadow
    for option in offered[offered.index(taken) + 1 :]:
        other = refit((option,))
        if other.beside or other.court_fix != tuple(option):
            continue
        got = screened(other)
        if got[2].triage is Triage.green:
            return (other, *got)
    return fit, facts, result, shadow


#: Which of two answers is the worse, for :func:`screen_lot`'s two
#: readings: a definite failure over a question over a path over a pass.
_WORSE: dict[Triage, int] = {Triage.green: 0, Triage.yellow: 1, Triage.unknown: 2, Triage.red: 3}

#: The colour the map shows, worst last (Steph's flag plan, 2026-10-02): a
#: miss is RED whatever path round it the triage still names (FOLLOWUPS 44).
_COLOUR: dict[flag_plan.Colour, int] = {
    flag_plan.Colour.green: 0, flag_plan.Colour.yellow: 1, flag_plan.Colour.red: 2,
}


def _shown(s: Screened) -> tuple[int, int]:
    """How bad one reading's answer is: the colour the map shows it, then
    the triage underneath -- a question over a path over a pass."""
    return _COLOUR[s.signed.colour], _WORSE[s.signed.triage]


def _street_unconfirmed(s: Screening) -> Screening:
    """``s`` as a question (:data:`~flats.score.screen.STREET_UNCONFIRMED`),
    unless it is already the worse answer."""
    reasons = s.reasons if STREET_UNCONFIRMED in s.reasons else (*s.reasons, STREET_UNCONFIRMED)
    triage = s.triage if _WORSE[s.triage] >= _WORSE[Triage.unknown] else Triage.unknown
    flags = s.flags
    if not any(f.code == "ACCESS-STREET-UNCONFIRMED" for f in flags):
        flags = (*flags, flag_plan.Flag("ACCESS-STREET-UNCONFIRMED", flag_plan.LOT, STREET_UNCONFIRMED))
    return dataclasses.replace(s, triage=triage, reasons=reasons, flags=flags)


def _rank_unknown(s: Screened) -> Screened:
    """``s`` as a question (:data:`~flats.score.screen.STREET_RANK_UNKNOWN`):
    a corner lot whose parking works off the street the measured plan chose
    and misses off the other, where nothing ranks one of its streets. Never
    applied to a red lot: the miss stands on either street."""

    def ask(x: Screening) -> Screening:
        reasons = x.reasons if STREET_RANK_UNKNOWN in x.reasons else (*x.reasons, STREET_RANK_UNKNOWN)
        triage = x.triage if _WORSE[x.triage] >= _WORSE[Triage.unknown] else Triage.unknown
        flags = x.flags
        if not any(f.code == "ACCESS-STREET-RANK-UNKNOWN" for f in flags):
            flags = (
                *flags,
                flag_plan.Flag("ACCESS-STREET-RANK-UNKNOWN", flag_plan.LOT, STREET_RANK_UNKNOWN),
            )
        return dataclasses.replace(x, triage=triage, reasons=reasons, flags=flags)

    if s.signed.colour is flag_plan.Colour.red:
        return s
    return dataclasses.replace(s, screening=ask(s.screening), signed=ask(s.signed))


def _pick_access(by_access: Sequence[tuple[Any, tuple[Screened, Any]]]) -> tuple[Any, Any, bool]:
    """The way in a corner plan is answered on: ``(access, shot, asked)``.

    ``by_access`` is the measured access first, then (where a street has no
    class) the driveway off the other street. The worse answer is kept, so
    an unmeasured fact takes its worst case -- except a RED that only the
    unranked street brings: the measured plan stands as a closer look,
    ``asked`` (Steph 2026-10-09: "yellow, then measure"). Only a plan that
    turns the colour or the triage worse replaces the measured one: a tie
    keeps it, so its drawing (and the flags that drawing owes) stands.
    """
    used, shot = max(by_access, key=lambda v: _front_rank(v[1][0])[:3])
    if (
        len(by_access) == 2
        and used is not by_access[0][0]
        and shot[0].signed.colour is flag_plan.Colour.red
        and by_access[0][1][0].signed.colour is not flag_plan.Colour.red
    ):
        used, shot = by_access[0]
        return used, shot, True
    return used, shot, False


def _worse(first: Screened, second: Screened) -> Screened:
    """The worse of one design's two readings (:func:`drive_reading`).

    Each is sound alone -- the line a street, the line an ordinary lot
    line -- so the worse cannot be a false GREEN. Compared on the colour
    the map shows (:func:`_shown`), where a miss is red: on the triage
    alone a reading waiting on an open fact outranked one the building
    misses on, whose variance path read yellow, and the miss was hidden
    (FOLLOWUPS 44). The verdict's own colour rides with it. A second
    reading fitted on s5o's envelope was not computed at all -- s5o cut
    that envelope with the drive as a street -- and makes the first a
    question.
    """
    if second.envelope is not None and second.envelope.source == "quadfit":
        return dataclasses.replace(
            first,
            screening=_street_unconfirmed(first.screening),
            signed=_street_unconfirmed(first.signed),
        )
    if _shown(second) > _shown(first):
        return second
    return first


def _better(first: Screened, second: Screened) -> Screened:
    """The better of one design's two readings where the applicant chooses
    between them (``private_drives.access_choice``): each is the lot as the
    code reads it for one way in, so either is a lawful plan. A second
    reading fitted on s5o's envelope was not computed (s5o cut it with the
    drive as a street) and is not offered. Compared on the colour the map
    shows, as :func:`_worse` is."""
    if second.envelope is not None and second.envelope.source == "quadfit":
        return first
    if _shown(second) < _shown(first):
        return second
    return first


#: More open facts than this on one design and its worst reading is not
#: searched: every combination of answers is a screen of its own (2**k).
BOUND_FACTS = 3

#: Where a fact flag came from when the screen could have taken the other
#: answer: nobody observed it, or the registry assumed it. A fact measured
#: TRUE on a footnote that states no number (``held``) has no worse answer
#: to try, and a measurement the screen could not take (``unmeasured``) is
#: not a yes or a no.
_BOUNDABLE = frozenset({"unobserved", "assumed"})


def _same_numbers(a: ZoneResolution, b: ZoneResolution) -> bool:
    """Whether two resolutions state the same standards: every number, every
    exemption and every gap. Where they do, the screen cannot tell them apart."""
    return (
        a.verdict == b.verdict
        and a.exempted == b.exempted
        and a.ambiguous == b.ambiguous
        and a.missing_required == b.missing_required
        and a.untrusted == b.untrusted
        and {k: v.value for k, v in a.values.items()} == {k: v.value for k, v in b.values.items()}
    )


#: The flag a plan carries where no hose route was found for its drawing.
#: Not one of the facts :func:`_bounded` answers: a combination that finds no
#: route asks the question the bounded plan is asked anyway, on its own
#: drawing, before it may be GREEN (a route found past the limit is a bind,
#: and still ends the search).
FIRE_ROUTE_UNFOUND = "MEASURE-FIRE-ROUTE"


def _bounded(
    s: Screened,
    lot: QuadfitLot,
    *,
    rules: RuleSet,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    step_deg: float,
    roads: Any,
    pool: dict[Any, dict[Any, Fitter]],
    fitter: Fitter | None = None,
    terrain: Any = None,
) -> Screened:
    """``s`` with the facts it is waiting on set to severity 0 where no
    answer to them could turn it red (FOLLOWUPS 37 item 3; Steph's flag plan,
    2026-10-02: a flag the lot clears even at its worst reading stays a flag,
    at severity 0, and does not hold the lot out of GREEN).

    Only a design the fact flags alone hold at yellow is tried, and only the
    facts whose flags do it: the lot is screened again under every
    combination of yes and no for them, the whole way -- the yards, the fit,
    the court, the fire route -- and the flags drop to 0 only where every
    combination clears with no miss and no new question big enough to count.
    A combination whose standards come out the same as the lot's own is the
    same screen and is not run again, nor is one whose standards match a
    combination already screened. A fact on a footnote that states no
    number (``ZoneResolution.unencoded``) has no worst reading anybody can
    compute and keeps its flag; so does every fact on a design with more
    than :data:`BOUND_FACTS` of them. Only the code's answers change here:
    what the lot's geometry says (its edges, its alley, its corner) is the
    lot's own and is not re-guessed.

    A plan held short of GREEN skipped the fire route where no route was
    found (:func:`fire_checked`); one made GREEN here is held to it now, as
    every GREEN is, and keeps its lowered flags through that re-screen.
    """
    signed = s.signed
    if signed.binds or s.config is None:
        return s
    reg = flag_plan.registry()
    line = flag_plan.colour_rules().yellow_at_severity
    facts = {
        flag_plan.fact_code(n): n
        for n in s.config.leans_on(s.rules.levers)
        if n not in s.rules.unencoded
    }
    held = [
        f
        for f in signed.flags
        if f.source in _BOUNDABLE and f.code in facts and flag_plan.severity_of(f, reg) >= line
    ]
    if not held:
        return s
    keys = {(f.code, f.key) for f in held}

    def zeroed(flags: tuple[flag_plan.Flag, ...]) -> tuple[flag_plan.Flag, ...]:
        return tuple(
            dataclasses.replace(f, severity=0) if (f.code, f.key) in keys else f for f in flags
        )

    lowered = zeroed(signed.flags)
    if flag_plan.colour(signed.binds, lowered, reg=reg) is not flag_plan.Colour.green:
        return s
    names = sorted({facts[f.code] for f in held})
    if len(names) > BOUND_FACTS:
        return s
    known = {(f.code, f.key) for f in signed.flags}
    layer_id = lot.layer_id or f"or/?/{lot.jurisdiction}"
    seen = [s.rules]
    # Every answer True first: the worst reading is the likeliest to bind,
    # and the first combination that binds ends the search.
    for combo in itertools.product((True, False), repeat=len(names)):
        observed = {**lot.observed, **dict(zip(names, combo))}
        try:
            config = configure(lot.facts, s.design, observed=observed)
        except ValueError:
            continue  # a world that cannot be: a child fact beside its parent's denial
        got = rules.resolve(layer_id, lot.zone, config.conditions, lot=config.measures)
        if any(_same_numbers(got, other) for other in seen):
            continue
        seen.append(got)
        (alt,) = _screen_lot_once(
            dataclasses.replace(lot, observed=observed),
            [s.design],
            rules=rules,
            policy=policy,
            relief=relief,
            step_deg=step_deg,
            roads=roads,
            bound=False,
            pool=pool,
            terrain=terrain,
            room=False,
        )
        if alt.signed.binds or any(
            (f.code, f.key) not in known
            and f.code != FIRE_ROUTE_UNFOUND
            and flag_plan.severity_of(f, reg) >= line
            for f in alt.signed.flags
        ):
            return s
    if s.facts is not None and not s.facts.fire_route_tried:
        s = fire_checked(s, lot, roads, policy=policy, relief=relief, fitter=fitter, green=True)
    return dataclasses.replace(
        s,
        screening=dataclasses.replace(s.screening, flags=zeroed(s.screening.flags)),
        signed=dataclasses.replace(s.signed, flags=zeroed(s.signed.flags)),
    )


def screen_lot(
    lot: QuadfitLot,
    designs: Sequence[Design],
    *,
    rules: RuleSet,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    step_deg: float = DEFAULT_STEP_DEG,
    roads: Any = None,
    terrain: Any = None,
) -> list[Screened]:
    """Screen one lot against every design, and where a street line rests
    only on a private drive whose standing is in doubt, screen the lot
    again without it and keep the worse answer (:func:`drive_reading`).

    ``roads`` is the street centreline index the fire route is measured to
    (:func:`flats.fit.fire.load_truck_roads`); without it the route starts
    at the street lot line, which only a test may accept.

    ``terrain`` is the elevation models the grade under each plan is read
    off (:class:`flats.fit.slope.Terrain`, :func:`slope_checked`); without
    it no grade is measured and the slope ruling goes unchecked. The steep
    ground comes on the lot itself (:func:`with_steep`).
    """
    if lot.sidewalk_easement_ft:
        # Every resolution this lot's screen asks for -- the yards, the
        # worst-bound readings, the strip's and the slope's re-screens --
        # measures the street setbacks from the easement line.
        rules = _Eased(rules, lot.sidewalk_easement_ft)  # type: ignore[assignment]
    got = _screen_lot_once(
        lot, designs, rules=rules, policy=policy, relief=relief, step_deg=step_deg, roads=roads,
        terrain=terrain,
    )
    got = easement_checked(
        lot, got, rules=rules, policy=policy, relief=relief, step_deg=step_deg, roads=roads,
        terrain=terrain,
    )
    if lot.second is None:
        return got
    alt = _screen_lot_once(
        lot.second, designs, rules=rules, policy=policy, relief=relief, step_deg=step_deg,
        roads=roads, terrain=terrain,
    )
    alt = easement_checked(
        lot.second, alt, rules=rules, policy=policy, relief=relief, step_deg=step_deg,
        roads=roads, terrain=terrain,
    )
    if lot.second_better:
        return [_better(a, b) for a, b in zip(got, alt)]
    return [_worse(a, b) for a, b in zip(got, alt)]


def _chose(lot: QuadfitLot, s: Screened) -> bool:
    """Whether :func:`_screen_lot_once` chose between readings of ``lot`` for
    this design: a corner's fronts, a through lot's ends, a part-alley rear
    cut two ways."""
    if lot.edges is None:
        return False
    fronts = corner_fronts(lot.edges, front_lot_line_rule(s.rules))
    if fronts and fronts != (None,):
        many = len(fronts) > 1
    else:
        many = len(through_plans(lot.edges, front_lot_line_through_rule(s.rules))[0]) > 1
    return many or part_rear_alley(lot)


def _lost(s: Screened, before: Screened) -> bool:
    """Whether ``s`` -- a design screened with its street yards floored --
    misses where ``before``, the same design at the code's own yards, did
    not: its fit (:func:`_fit_missed`), or any check the deeper yard turned
    to a failure, as the fire hose's route the yard lengthens past its limit
    (FOLLOWUPS 43, 2026-10-06 bound: 3 big Oregon City lots red on the hose
    at 10 ft, never asked at 5)."""
    if _fit_missed(s):
        return True
    had = {c.check for c in before.screening.checks if c.verdict is CheckVerdict.fails}
    return any(
        c.verdict is CheckVerdict.fails and c.check not in had for c in s.screening.checks
    )


def _waits_on_easement(s: Screened) -> bool:
    """Whether this design's answer waits on the utility easement question."""
    if s.config is None:
        return False
    return easement.FACT in s.config.unknown and easement.FACT in s.config.leans_on(s.rules.levers)


def easement_checked(
    lot: QuadfitLot,
    got: list[Screened],
    *,
    rules: RuleSet,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    step_deg: float = DEFAULT_STEP_DEG,
    roads: Any = None,
    terrain: Any = None,
) -> list[Screened]:
    """``got`` with the utility easement question answered where Steph's
    ruling reaches the lot (FOLLOWUPS 43; ``flats/config/easements.yaml``).

    Steph, 2026-10-01: the building fits with a 10 ft yard on every street
    line -> green; fits at 5 ft but not 10 -> yellow; not even at 5 -> red.
    So each design that waits on ``utility_easement`` is screened again, the
    whole way, with every street yard floored at the city's ``green_ft`` and
    the question answered no: where that plan fits, it is the answer, and
    the lot waits on whatever else it waited on. Where it does not -- or
    fails a check it passed at the code's own yards (:func:`_lost`): the
    yard is still what stands in the way -- the design is screened at
    ``yellow_ft`` with the question still open: yellow where that plan
    holds, red on its miss where it does not
    (:func:`flats.fit.easement.pick`). Both carry the
    UTILITY-EASEMENT-ASSUMED flag through :attr:`LotFacts.easement_street_ft`.

    A design that misses at the code's own yards keeps its answer unless
    the green yard fits: the easement is not why it fails. The green yard is
    asked of it only where the screening chose between readings of the lot
    (:func:`_chose`), since there the open question can be what chose the
    reading it missed on (:func:`_front_rank`); one reading, and the floor
    can only shrink what missed. A plan the floor cannot reach -- fitted on
    quadfit's envelope, where FLATS cut none of its own -- keeps its answer
    too.
    """
    rule = easement.rule_for(lot.layer_id)
    if rule is None or easement.FACT in lot.observed:
        return got
    missed = {i: _fit_missed(s) for i, s in enumerate(got)}
    todo = [
        i for i, s in enumerate(got)
        if _waits_on_easement(s) and (not missed[i] or _chose(lot, s))
    ]
    if not todo:
        return got

    def floored(ft: float, answered: bool) -> QuadfitLot:
        observed = {**lot.observed, easement.FACT: False} if answered else lot.observed
        facts = dataclasses.replace(lot.facts, easement_street_ft=ft)
        return dataclasses.replace(lot, facts=facts, observed=observed, second=None)

    def screened(here: QuadfitLot, which: Sequence[int]) -> dict[int, Screened]:
        out = _screen_lot_once(
            here, [got[i].design for i in which], rules=rules, policy=policy, relief=relief,
            step_deg=step_deg, roads=roads, terrain=terrain,
        )
        return dict(zip(which, out))

    green = screened(floored(rule.green_ft, answered=True), todo)
    measured = {
        i: green[i].envelope is not None and green[i].envelope.source == "flats" for i in todo
    }
    lost = {i: _lost(green[i], got[i]) for i in todo}
    # The narrow yard leaves the question open, and so the same reading
    # first: it is not asked of a plan that missed as it stands.
    narrow = [i for i in todo if measured[i] and lost[i] and not missed[i]]
    yellow = screened(floored(rule.yellow_ft, answered=False), narrow) if narrow else {}
    choice = {
        i: easement.pick(
            as_is_missed=missed[i],
            green_missed=lost[i],
            green_measured=measured[i],
            yellow_missed=i not in yellow or _lost(yellow[i], got[i]),
        )
        for i in todo
    }
    out = list(got)
    for i in todo:
        if choice[i] == "green":
            out[i] = green[i]
        elif choice[i] == "yellow":
            out[i] = yellow[i]
    return out


def _screen_lot_once(
    lot: QuadfitLot,
    designs: Sequence[Design],
    *,
    rules: RuleSet,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    step_deg: float = DEFAULT_STEP_DEG,
    roads: Any = None,
    bound: bool = True,
    pool: dict[Any, dict[Any, Fitter]] | None = None,
    terrain: Any = None,
    fit_only: bool = False,
    room: bool = True,
) -> list[Screened]:
    """Screen one lot against every design, one envelope search for all.

    The configuration and the resolution are per design (a design's own
    conditions ride in); the :class:`~flats.fit.rectangle.Fitter` is built
    once, at the angles the zone allows: a zone that makes the building face
    the street confines the search to s4's street directions, every other
    zone gets the sweep with those directions folded in. A lot with no
    street direction is swept either way -- not knowing the front is not a
    reason to search nothing, and ``NO_FRONTAGE`` already names the lot.

    On a corner lot the code's ``front_lot_line_corner`` names the front
    (:mod:`flats.geom.corner`): the shorter street where the code fixes it,
    both streets tried and the better answer kept where the owner chooses.
    ``Screened.front_deg`` records the street taken; ``None`` is the old
    reading, every street a front.

    ``bound`` tries each design's worst reading of the facts it waits on
    (:func:`_bounded`); ``pool`` carries the envelope searches from one of
    those readings to the next, by the angles they were swept at -- the same
    lot, the same ground, only the code's answers differ.

    ``fit_only`` is for a caller that reads nothing but the fit
    (:func:`slope_checked`): the drawing, the fire route and the strip's
    second reading, the dearest steps on a big lot, are not run.

    ``room`` measures how much bigger each pod could be on a lot it is not
    red on (:attr:`Screened.room`); a caller that discards the answer
    (:func:`_bounded`) spares the search.
    """
    pool = {} if pool is None else pool
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
    fitters: dict[Any, Fitter] = pool.setdefault(tuple(angles), {})

    out: list[Screened] = []
    for design, config, got in resolved:
        # WHICH STREET IS THE FRONT (FOLLOWUPS 4(e)): where the code names it
        # the lot is cut with that front; where it leaves it to the applicant
        # each street is tried and the better answer kept. None: no front is
        # named and every street edge is a front, as before 2026-09-26.
        #
        # WHICH END OF A THROUGH LOT (FOLLOWUPS 6(i)): a lot with a street
        # at each end names its far line by `front_lot_line_through` --
        # `owner` tries each end as the front with the other the rear and
        # keeps the better; `both_unless_no_access` and unread screen both
        # fronts and each end as the rear and keep the WORSE, since nothing
        # says which is true; `both` is the lot as cut.
        fronts: tuple[float | None, ...] = corner_fronts(
            lot.edges, front_lot_line_rule(got)
        ) or (None,)
        plans: list[tuple[Any, LotEdges | None, float | None]] = []
        worst = False
        if fronts != (None,) and lot.edges is not None:
            plans = [(f, name_front(lot.edges, f), f) for f in fronts]
        else:
            readings, worst = through_plans(lot.edges, front_lot_line_through_rule(got))
            plans = [(("through", k), e, None) for k, e in enumerate(readings)]
            if not plans:
                plans = [(None, lot.edges, None)]
        tried: list[tuple[Screened, Fitter]] = []
        access_log: list[dict[str, Any]] = []
        unranked: list[bool] = []
        plain: ZoneResolution | None = None
        alleyed: ZoneResolution | None = None
        for plan_key, plan_edges, front in plans:
            here = lot
            if plan_edges is not lot.edges:
                here = dataclasses.replace(lot, edges=plan_edges)
            # A lowest-class driveway off a corner lot whose named front is
            # the quieter street comes off the front (Steph 2026-10-05).
            plan_got = measured_access(got, plan_edges, front)
            # A street class nobody measured: the driveway is tried off each
            # street and the worse answer kept (FOLLOWUPS 49(c)).
            other_got = unknown_access(got, plan_edges, front)
            if plain is None and lot.observed.get("alley_at_rear") and rear_off_alley(here.edges):
                # A rear line off the alley owes the ordinary rear setback:
                # the same lot resolved without the rear alley (FOLLOWUPS 12(b)).
                bare = configure(
                    lot.facts, design, observed={**lot.observed, "alley_at_rear": False}
                )
                plain = rules.resolve(layer_id, lot.zone, bare.conditions, lot=bare.measures)
            if alleyed is None and part_rear_alley(here):
                # A rear alley along PART of the line: the covered stretch
                # abuts the alley and takes its rear (Steph 2026-09-28).
                on = configure(lot.facts, design, observed={**lot.observed, "alley_at_rear": True})
                alleyed = rules.resolve(layer_id, lot.zone, on.conditions, lot=on.measures)
            envs = [envelope_for(here, got, plain)]
            if alleyed is not None and part_rear_alley(here):
                # Both cuts are tried and the better answer kept: the stretch
                # cut is charged the court against the alley's (smaller) rear
                # everywhere, since the fit does not say where along the line
                # the court stands, which can cost more behind the uncovered
                # stretch than it gains behind the covered one; the whole-line
                # ordinary cut is the answer before 2026-09-29. Each is sound
                # alone, so the better of the two is.
                cut = envelope_for(here, got, plain, alleyed)
                if cut.setbacks != envs[0].setbacks:
                    envs.append(cut)
            # The better of the envelope cuts for this reading of the lot;
            # the readings are ranked against each other below.
            by_access = [
                (variant, min(
                    (
                        _screen_on(
                            here, design, config, variant, env, front, angles, fitters, step_deg,
                            policy=policy, relief=relief, plan=plan_key,
                        )
                        for env in envs
                    ),
                    key=lambda t: _front_rank(t[0]),
                ))
                for variant in (plan_got, other_got)
                if variant is not None
            ]
            # Only a plan that turns the colour or the triage worse replaces
            # the one measured access chose: a tie keeps it, so its drawing
            # (and the flags that drawing owes) stands.
            used, shot, asked = _pick_access(by_access)
            unranked.append(asked)
            if front is not None:
                access_log.append(access_record(got, used, plan_edges, front))
            tried.append(shot)
        # Drawn for the winner only: one more window search per design.
        if worst:
            # The worse reading: the lower colour, the tighter fit, and on a
            # tie (the pod's slack is often measured across the lot, which
            # the ends do not touch) the smaller envelope.
            won, fitter = max(tried, key=lambda t: (*_front_rank(t[0]), -_env_sqft(t[0])))
        else:
            won, fitter = min(tried, key=lambda t: _front_rank(t[0]))
        ask_rank = unranked[next(i for i, t in enumerate(tried) if t[0] is won)]
        if access_log and len(access_log) == len(tried):
            won = dataclasses.replace(won, access=_access_won(access_log, tried, won))
        if fit_only:
            out.append(_rank_unknown(won) if ask_rank else won)
            continue
        won = dataclasses.replace(won, drawing=drawing_for(won, fitter))
        won = fire_checked(won, lot, roads, policy=policy, relief=relief, fitter=fitter)
        won = slope_checked(
            won, lot, terrain, rules=rules, policy=policy, relief=relief, step_deg=step_deg,
            roads=roads,
        )
        won = flatter_checked(
            won, lot, terrain, fitter, rules=rules, policy=policy, relief=relief,
            step_deg=step_deg, roads=roads,
        )
        if _coarse_blocked(won, lot):
            # Eliminated on the coarse map's steep ground alone: screened
            # again, the whole way, as though it were not there, and flagged
            # (FOLLOWUPS 49(h), Steph 2026-10-07).
            (won,) = _screen_lot_once(
                unconfirmed_steep(lot), [design], rules=rules, policy=policy, relief=relief,
                step_deg=step_deg, roads=roads, bound=bound, terrain=terrain, room=room,
            )
            out.append(won)
            continue
        if bound:
            won = _bounded(
                won, lot, rules=rules, policy=policy, relief=relief, step_deg=step_deg,
                roads=roads, pool=pool, fitter=fitter, terrain=terrain,
            )
        if room and won.signed.colour is not flag_plan.Colour.red:
            # Before the strip's second reading: a plan that reading replaces
            # was red, and the reading measures its own.
            won = dataclasses.replace(won, room=_room(won, fitter))
        won = strip_waived(
            won, lot, rules=rules, policy=policy, relief=relief, step_deg=step_deg,
            roads=roads, bound=bound, terrain=terrain,
        )
        out.append(_rank_unknown(won) if ask_rank else won)
    return out


class _Eased:
    """``rules`` with every street setback measured from a sidewalk
    easement line ``depth_ft`` inside the lot
    (:func:`flats.geom.sidewalk.easement_shifted`), for one lot's screen."""

    def __init__(self, rules: RuleSet, depth_ft: float) -> None:
        self._rules = rules
        self._depth_ft = depth_ft

    def resolve(self, *args: Any, **kwargs: Any) -> ZoneResolution:
        return easement_shifted(self._rules.resolve(*args, **kwargs), self._depth_ft)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._rules, name)


class _Waived:
    """``rules`` with the named standards read as unstated, for
    :func:`strip_waived`'s second reading: every resolution the screen asks
    for on the way -- the yards, the worst-bound readings, the slope's
    re-screen -- comes back without them."""

    def __init__(self, rules: RuleSet, fields: Sequence[str]) -> None:
        self._rules = rules
        self._fields = frozenset(fields)

    def resolve(self, *args: Any, **kwargs: Any) -> ZoneResolution:
        got = self._rules.resolve(*args, **kwargs)
        if not self._fields & set(got.values):
            return got
        return dataclasses.replace(
            got,
            values={k: v for k, v in got.values.items() if k not in self._fields},
            untrusted=tuple(n for n in got.untrusted if n not in self._fields),
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._rules, name)


#: The checks a planted strip can move: the ground the building and its court
#: stand on, and what is measured on the plan drawn there. A bind on any other
#: check (a height, a lot size, the use) stays whatever the strip does.
STRIP_MOVES: frozenset[str] = COURT_SHAPED | {"fire_access_ft", STEEP_GROUND}

#: A fit short by more than this many strip widths is not read again: the
#: strip gives the envelope back at most its own width off each line it
#: stands on, and a shortfall past a few of those is a miss either way. A
#: lot cut here stays RED where a reading might have made it a question --
#: a false red, never a false green.
STRIP_REACH = 3.0


def strip_waived(
    s: Screened,
    lot: QuadfitLot,
    *,
    rules: RuleSet,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    step_deg: float,
    roads: Any,
    bound: bool,
    terrain: Any = None,
) -> Screened:
    """``s``, or the same design screened without the planted strip the code
    keeps between parking and the lot lines where the strip alone is what
    the plan misses by (Steph 2026-10-04: "Let's have strips be a flag for
    yellow at this time").

    Whether a townhome project owes the strip is open -- OAR
    660-046-0220(2)(e)(E) may hold middle housing to the single-family
    parking standards, which ask none (FOLLOWUPS 36) -- so a plan that
    misses with it and clears without it is a question: the second reading,
    screened the whole way (yards, fit, court, fire, slope, worst bound) on
    rules that state no strip, and carrying
    :data:`~flats.score.screen.PARKING_STRIP_UNCONFIRMED` and its flag, which
    hold it out of GREEN. Kept only where that reading binds nothing; a
    plan that misses either way keeps the strip's answer. Only a plan with a
    miss the strip could move is read again (:data:`STRIP_MOVES`,
    :data:`STRIP_REACH`).
    """
    strip = lot_line_buffer_ft(s.rules)
    binds = s.signed.binds
    if strip <= 0 or not binds or lot.facts.strip_waived:
        return s
    for b in binds:
        if b.check not in STRIP_MOVES:
            return s
        if b.check in ("fit_ft", "fit_across_ft", STEEP_GROUND) and (b.shortfall or 0.0) > STRIP_REACH * strip:
            return s
    waived = dataclasses.replace(lot, facts=dataclasses.replace(lot.facts, strip_waived=True))
    (alt,) = _screen_lot_once(
        waived, [s.design], rules=_Waived(rules, (STRIP_FIELD,)),  # type: ignore[arg-type]
        policy=policy, relief=relief, step_deg=step_deg, roads=roads, bound=bound,
        terrain=terrain,
    )
    return s if alt.signed.binds else alt


def fire_checked(
    s: Screened,
    lot: QuadfitLot,
    roads: Any,
    *,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    fitter: Fitter | None = None,
    green: bool = False,
) -> Screened:
    """``s`` re-screened with the fire hose's route measured on its drawing
    (FOLLOWUPS 28, OFC 503.1.1).

    The route runs from the street to the farthest point of the building
    the drawing stands nearest the street (:func:`flats.fit.fire.route_ft`),
    entering over any of the lot's street lines -- every street, whichever
    one the plan was laid out fronting, and a private road the yards do not
    count (:attr:`QuadfitLot.access`): the truck may use any of them. A
    plan already RED both ways cannot be moved by it and is not measured.
    Where no route is found -- nothing drawn, a fit that fell short (its
    drawing shows the shortfall, not a building that could stand there),
    no polygon or street line, no truck road near -- a plan that would otherwise be GREEN either way,
    or green on the map (:func:`_map_green`), is
    tried and unobserved, which holds it out of GREEN; any other plan is
    left unchecked, its colour already short of GREEN for another reason.
    Where the drawing stands the building at a front no truck road serves
    -- the freeway end of a through lot, a front on an unnamed drive --
    and the route misses, the plan is drawn once more at the fronts a truck
    can reach (``fitter``), and kept where the building fits there and the
    hose reaches it sooner: the same fit, the end the developer would
    build at. Where the route still misses, the plan is drawn at the fit's
    other angles (:func:`_turned_for_fire`) and kept at one the hose
    reaches. Other placements at an angle than the one nearest the street
    are not searched: where one would reach, the answer is a false red,
    never a false green. ``green`` says the plan
    is GREEN whatever its triage reads -- its open facts were bounded
    (:func:`_bounded`) -- and holds it to the same rule.
    """
    from shapely.geometry import Polygon

    from flats.fit import fire

    if s.rules.get("fire_access_max_ft") is None or s.facts is None:
        return s
    if s.screening.triage is Triage.red and s.signed.triage is Triage.red and not _map_green(s):
        return s
    streets: tuple[tuple[float, float, float, float], ...] = ()
    if lot.edges is not None:
        streets = tuple(
            (e.x1, e.y1, e.x2, e.y2)
            for e in lot.edges.edges
            if e.cls in (EdgeClass.front, EdgeClass.street_side)
        )
    # A private road the yards do not count is still a road the truck may
    # stand on (where it is one: the offset keeps only truck roads).
    streets += tuple(a for a in lot.access if a not in streets)
    offset = fire.point_offset(*roads) if roads is not None else None
    # The hose measured from the curb itself (FOLLOWUPS 29): only to flag a
    # red the stricter reading alone makes.
    from_curb = fire.point_offset(*roads, reading="curb") if roads is not None else None

    def measure(drawing: dict[str, Any] | None, offset: Any = offset) -> float | None:
        # Only a drawing whose room holds the building and its court stands
        # the building anywhere: where the fit fell short it shows the
        # shortfall, and a route to that would turn a lot RED off a
        # building that cannot be built there (run 54: 14,419 answers). A
        # fit passed tight is drawn fitting (``tight``, :func:`_tight_ft`).
        ring = (drawing or {}).get("building")
        if not ((drawing or {}).get("fits") and ring and len(ring) >= 4 and lot.lot_geom is not None and streets):
            return None
        return fire.route_ft(Polygon(ring), lot.lot_geom, streets, offset)

    route = measure(s.drawing)
    limit = float(s.rules.get("fire_access_max_ft"))
    at = None
    if (route is None or route > limit) and fitter is not None:
        fronts = _street_lines(s.lot)
        served = fire.reachable(fronts, offset)
        if served and len(served) < len(fronts):
            at = served
            drawn = drawing_for(s, fitter, street=served)
            again = measure(drawn) if drawn and drawn.get("fits") else None
            if again is not None and (route is None or again < route):
                s, route = dataclasses.replace(s, drawing=drawn), again
    green = green or Triage.green in (s.screening.triage, s.signed.triage) or _map_green(s)
    if route is None and not green:
        return s

    def screened(s: Screened, route: float | None) -> Screened:
        curb = measure(s.drawing, from_curb) if from_curb is not None and route is not None and route > limit else None
        facts = dataclasses.replace(s.facts, fire_route_ft=route, fire_route_tried=True, fire_route_curb_ft=curb)
        s = dataclasses.replace(s, fire_why=_fire_why(s, lot, streets, offset) if route is None else None)
        result = screen(s.rules, facts, s.design, s.fit, policy=policy, relief=relief, config=s.config)
        shadow = _if_signed(
            s.rules, facts, s.design, s.fit, result, policy=policy, relief=relief, config=s.config
        )
        return dataclasses.replace(s, screening=result, signed=shadow, facts=facts)

    out = screened(s, route)
    # The other angles are drawn only where the hose is all that stands in
    # the way: a plan missing something else stays short of GREEN whatever
    # the route, and the search is the dearest step on a big lot.
    # A route that was never found is not turned for: the fit's own angle
    # has the most room, and where its drawing holds no building the others
    # seldom do -- every angle drawn for nothing (run on a 7-acre lot: 13 s
    # to 233 s). The plan stays out of GREEN, unobserved.
    binds = out.signed.binds
    alone = route is not None and bool(binds) and all(b.check == "fire_access_ft" for b in binds)
    if fitter is not None and alone:
        turned, again = _turned_for_fire(s, fitter, measure, route, limit, street=at)
        if turned is not s:
            out = screened(turned, again)
    return out


def _fire_why(
    s: Screened, lot: QuadfitLot, streets: Sequence[tuple[float, float, float, float]], offset: Any
) -> str:
    """Which input :func:`flats.fit.fire.route_ft` was missing when it
    found no route for ``s``'s drawing."""
    from flats.fit import fire

    drawing = s.drawing or {}
    ring = drawing.get("building")
    if not (drawing.get("fits") and ring and len(ring) >= 4):
        return "no_building_drawn"
    if lot.lot_geom is None:
        return "no_lot_polygon"
    if not streets:
        return "no_street_lines"
    if offset is not None and not fire.reachable(streets, offset):
        return "no_truck_road_within_50ft"
    return "no_path_to_walls"


#: The angles :func:`_turned_for_fire` draws: every one the fit searched
#: within this many degrees of square to a street, and one in this many
#: beyond. Each angle is a window search, dear on a big lot; a reach missed
#: between them leaves a red standing, never a false green.
TURN_NEAR_DEG = 15.0
TURN_STEP_DEG = 5.0
#: At most this many angles are drawn, nearest square first: on a 7-acre lot
#: each drawing and its route cost half a second, and every reading of the
#: lot (the strip's, the slope's) turns again.
TURN_MAX = 24

def _turned_for_fire(
    s: Screened,
    fitter: Fitter,
    measure: Any,
    route: float | None,
    limit: float,
    *,
    street: tuple[tuple[float, float, float, float], ...] | None = None,
) -> tuple[Screened, float | None]:
    """``s`` drawn at the angle the hose reaches soonest, and that route
    (FOLLOWUPS 39, Steph 2026-10-04).

    The drawing stands the building at the fit's angle -- the one with the
    most room -- and the route is measured from there. Where it misses, the
    same building, orientation and court are drawn at the other angles the
    fit searched (the fitter's grids: only the angles the code allows), each
    nearest the street -- nearest square to a street first; every angle
    within :data:`TURN_NEAR_DEG` of square, one in :data:`TURN_STEP_DEG`
    beyond, at most :data:`TURN_MAX` of them -- and the first route within ``limit`` is kept, else the
    shortest that beats ``route``. Only a drawing whose room holds the building and its court on
    ground counts (``measure``), so the placement kept is one the fit would
    have passed: a red lifted, never a green invented. ``street`` is the
    fronts a truck can reach where the caller narrowed them.
    """
    if s.fit.angle_deg is None:
        return s, route
    square = [normalize(b + turn) for b in s.lot.front_bearings for turn in (0.0, 90.0)]

    def off(angle: float) -> float:
        d = min((abs(angle - a) % 180.0 for a in square), default=0.0)
        return min(d, 180.0 - d)

    def tried(angle: float) -> bool:
        # Every angle near square to a street; every TURN_STEP_DEG beyond.
        step = angle / TURN_STEP_DEG
        return off(angle) <= TURN_NEAR_DEG or math.isclose(step, round(step), abs_tol=1e-6)

    angles = sorted(
        (a for a in {g.angle_deg for g in fitter.grids}
         if tried(a) and not math.isclose(a, s.fit.angle_deg, abs_tol=1e-6)),
        key=lambda a: (off(a), a),
    )[:TURN_MAX]
    best: tuple[float, dict[str, Any]] | None = None
    for angle in angles:
        turned = dataclasses.replace(s, fit=dataclasses.replace(s.fit, angle_deg=angle))
        drawn = drawing_for(turned, fitter, street=street)
        got = measure(drawn) if drawn and drawn.get("fits") else None
        if got is not None and (best is None or got < best[0]):
            best = (got, drawn)
            if got <= limit:
                break
    if best is None or (route is not None and best[0] >= route):
        return s, route
    return dataclasses.replace(s, drawing=best[1]), best[0]


def with_steep(lot: QuadfitLot, terrain: Any) -> QuadfitLot:
    """``lot`` with its ground too steep to build or park on measured and
    taken off (FOLLOWUPS 38; Steph 2026-10-04: "slope-based lot
    elimination should happen before pod placement").

    The part of the taxlot steeper than ``steep_over_pct``
    (``flats/config/slope.yaml``), read by :meth:`flats.fit.slope.Terrain.
    steep`, rides on the lot as :attr:`QuadfitLot.steep` and comes off the
    envelope and the court's ground (:func:`envelope_for`), so the fit is
    searched on the flat ground alone; its area and the model that read it
    ride in the facts. The second reading of the lot (:func:`drive_reading`)
    is the same ground and takes the same cut. A lot no model covers, or no
    ``terrain``, is returned as it came.

    The same reading counts the ground over each grade a city's net acre
    deducts (:data:`flats.rules.net_area.SLOPES`) into the lot's measured
    deductions -- on the 1 m model only, and only beside the overlays s5o
    measured, so a lot with no measured deductions stays without.
    """
    if terrain is None or lot.lot_geom is None:
        return lot
    ruled = slope_rules()
    got = terrain.steep(
        lot.lot_geom,
        ruled.steep_over_pct,
        min_bank_ft=ruled.min_bank_ft,
        areas_over=tuple(NET_SLOPES.values()),
    )
    if got is None:
        return lot
    steep = got.geom if got.sqft > 0 else None
    over = {key: round(got.areas[at], 1) for key, at in NET_SLOPES.items() if at in got.areas}

    def cut(one: QuadfitLot) -> QuadfitLot:
        net = one.facts.net_deductions
        if net is not None and got.source == ONE_M and over:
            net = {**net, **over}
        facts = dataclasses.replace(
            one.facts, steep_sqft=round(got.sqft, 1), steep_source=got.source,
            net_deductions=net,
        )
        return dataclasses.replace(one, steep=steep, facts=facts)

    second = None if lot.second is None else cut(lot.second)
    return dataclasses.replace(cut(lot), second=second)


def _coarse_blocked(s: Screened, lot: QuadfitLot) -> bool:
    """Whether steep ground read on the coarse 10 m model alone is what
    eliminated this plan (:attr:`LotFacts.steep_blocks`), where the coarse
    model may not make a lot RED (``coarse_red_is_closer_look``)."""
    return (
        slope_rules().coarse_red_is_closer_look
        and s.facts is not None
        and s.facts.steep_blocks
        and lot.steep is not None
        and lot.facts.steep_source == TEN_M
    )


def unconfirmed_steep(lot: QuadfitLot) -> QuadfitLot:
    """``lot`` with the steep ground the coarse 10 m model read left on it,
    and that said in its facts (:attr:`LotFacts.steep_unconfirmed`).

    Steph 2026-10-07: a lot the coarse map's steep ground eliminates is
    "yellow with flag. 7 severity" -- a 10 m cell is wider than the ground
    it would take off, and the coarse map never makes a lot RED alone
    (``coarse_red_is_closer_look``). So the lot is screened without the
    cut: RED only on what else it misses, and flagged SLOPE-STEEP-COARSE
    for the 1 m lidar or a survey to settle. Its second reading
    (:func:`drive_reading`) is screened on its own.
    """
    facts = dataclasses.replace(lot.facts, steep_unconfirmed=True)
    return dataclasses.replace(lot, steep=None, facts=facts, second=None)


def _fit_short(s: Screened) -> float | None:
    """How far the plan's fit fell short, in feet; None where it was met."""
    for c in s.screening.checks:
        if c.check in ("fit_ft", STEEP_GROUND) and c.verdict is CheckVerdict.fails:
            return c.shortfall
    return None


#: The steep ground takes the blame for a fit the lot misses without it too
#: once it is most of the miss: the shortfall on the flat ground more than
#: this many times the shortfall on the whole lot (FOLLOWUPS 49(e)).
STEEP_SHARE = 2.0


def _fit_missed(s: Screened) -> bool:
    """Whether the plan missed its fit -- :data:`STEEP_GROUND` is the same
    miss, named for the slope that caused it (:func:`slope_checked`)."""
    return any(
        c.check in ("fit_ft", STEEP_GROUND) and c.verdict is CheckVerdict.fails
        for c in s.screening.checks
    )


def slope_checked(
    s: Screened,
    lot: QuadfitLot,
    terrain: Any,
    *,
    rules: RuleSet,
    policy: SlackPolicy,
    relief: ReliefPolicy,
    step_deg: float,
    roads: Any,
) -> Screened:
    """``s`` re-screened with what the slope did to it (FOLLOWUPS 38).

    First, whether the steep ground is what eliminated the lot
    (:attr:`LotFacts.steep_blocks`): the plan missed its fit on the flat
    ground (:func:`with_steep` took the rest off), and either that ground
    cannot hold even the building's footprint where the lot without the
    cut could -- Steph's test, "see if there's even enough land for the
    pod. If no, don't check pod placement" -- or the same lot screened with
    the steep ground left on does not miss, or misses by less than half as
    much (:data:`STEEP_SHARE`; FOLLOWUPS 49(e): 2.5 ft short on the whole
    lot and 63 ft on its flat ground is a hillside, not a variance). Then
    the miss is the slope's and is named so
    (:data:`flats.score.screen.STEEP_GROUND`); otherwise the lot was too
    tight anyway and the fit keeps the blame.

    Second, the fall across the ground the drawn plan's building and court
    stand on (:meth:`flats.fit.slope.Terrain.grade`), only where the drawing
    holds both -- a drawing that fell short shows the shortfall, not a pad;
    one the fit passed tight holds both (FOLLOWUPS 45, :func:`_tight_ft`).
    No model under the pad: tried, unobserved. Without ``terrain`` nothing
    is measured and ``s`` comes back as it came.
    """
    from shapely.geometry import Polygon

    if terrain is None or s.facts is None:
        return s
    facts = s.facts
    if lot.steep is not None and not lot.steep.is_empty and _fit_missed(s):
        flat = s.envelope.sqft if s.envelope is not None else 0.0
        need = s.design.ground_sqft
        bare = dataclasses.replace(lot, steep=None, second=None)
        whole = envelope_for(bare, s.rules).sqft
        if flat < need <= whole:
            facts = dataclasses.replace(facts, steep_blocks=True)
        elif whole >= need:
            (alt,) = _screen_lot_once(
                bare, [s.design], rules=rules, policy=policy, relief=relief,
                step_deg=step_deg, roads=roads, bound=False, fit_only=True,
            )
            whole_short, flat_short = _fit_short(alt), _fit_short(s)
            if whole_short is None or (
                flat_short is not None and flat_short > STEEP_SHARE * whole_short
            ):
                facts = dataclasses.replace(facts, steep_blocks=True)
    drawing = s.drawing or {}
    ring = drawing.get("building")
    if drawing.get("fits") and ring and len(ring) >= 4:
        pads = [Polygon(ring)]
        court = drawing.get("court")
        if court and len(court) >= 4:
            pads.append(Polygon(court))
        got = terrain.grade(pads)
        facts = dataclasses.replace(
            facts,
            site_grade_pct=None if got is None else round(got.pct, 2),
            site_grade_source=None if got is None else got.source,
            site_grade_tried=True,
        )
    if facts is s.facts:
        return s
    result = screen(s.rules, facts, s.design, s.fit, policy=policy, relief=relief, config=s.config)
    shadow = _if_signed(
        s.rules, facts, s.design, s.fit, result, policy=policy, relief=relief, config=s.config
    )
    return dataclasses.replace(s, screening=result, signed=shadow, facts=facts)


#: How far past the envelope's street edge the court beside the building may
#: start and still be the drive in from the street: a few grid cells and the
#: sampling step along the street line (:data:`flats.fit.draw.STREET_STEP_FT`).
BESIDE_REACH_TOL_FT = 3.0


def _beside_drawn(
    here: QuadfitLot,
    design: Design,
    got: ZoneResolution,
    fit: Fit,
    fitter: Fitter,
    env: Envelope,
) -> Any:
    """The plan with its court beside the building, drawn where the lot page
    draws it (nearest the street), or None where it cannot be drawn."""
    if here.edges is None:
        return None
    facts = here.facts
    beside = side_court(
        design, got, facts.alley, corner=facts.corner, frontage_ft=facts.frontage_ft
    )
    beyond = None if beside is None else _beside_beyond(
        beside, fit.required_ft, got, env.rear_cut_ft
    )
    if beside is None or beyond is None or math.isinf(beyond):
        return None
    return draw(
        fitter,
        fit,
        width_ft=design.footprint.width_ft,
        depth_ft=design.footprint.depth_ft,
        lane_ft=0.0,
        court_depth_ft=0.0,
        court_beyond_ft=beyond,
        street=_street_lines(here),
        beside_band_ft=beside.band_ft,
        beside_len_ft=beside.length_ft,
    )


def beside_reaches_street(
    here: QuadfitLot,
    design: Design,
    got: ZoneResolution,
    fit: Fit,
    fitter: Fitter,
    env: Envelope,
) -> bool:
    """Whether the court beside the building (FOLLOWUPS 4(a)) starts at the
    envelope's street edge, so that its aisle is the drive in from the street.

    The search that found the fit asks only for a rectangle at the street's
    directions, anywhere on the envelope; on an L-shaped lot, or behind a flag
    lot's pole, the only such room can stand far back from the street with
    nothing to reach it. The plan is drawn nearest the street (the drawing
    tries every window that fits); where even that court starts further from
    the front lines than the envelope does, plus :data:`BESIDE_REACH_TOL_FT`,
    no window reaches the street. No lot polygon, no front lines, or no
    drawing: not shown to reach, so not taken.
    """
    import shapely

    if here.edges is None or env.geom is None:
        return False
    fronts = [shapely.LineString([(x1, y1), (x2, y2)]) for x1, y1, x2, y2 in _street_lines(here)]
    if not fronts:
        return False
    drawn = _beside_drawn(here, design, got, fit, fitter, env)
    if drawn is None or drawn.court is None:
        return False
    edge = max(env.geom.distance(f) for f in fronts)
    return min(drawn.court.distance(f) for f in fronts) <= edge + BESIDE_REACH_TOL_FT


def outdoor_square(
    here: QuadfitLot,
    design: Design,
    got: ZoneResolution,
    fit: Fit,
    fitter: Fitter,
    env: Envelope,
) -> float | None:
    """The largest outdoor square this plan leaves on the lot, in feet
    (FOLLOWUPS 7(b); :mod:`flats.fit.outdoor`), or None where it cannot be
    measured.

    The plan is drawn the way the lot page draws it -- building at the street
    end, lane beside it, the court's stalls and aisle behind the standoff --
    and the ground left is the lot less the front setback, those shapes and
    every overlay carve. A court reached across a side yard (a side street or
    a side alley) has a drive the drawing does not place, so its whole depth
    band is taken, lot line to lot line. None, leaving the shape unobserved,
    where there is no lot polygon or front line, the front setback is
    unstated, the drawing finds no room for the plan, or a side-fed court
    stands as a column.
    """
    side = got.get("open_space_min_dimension_ft")
    if side is None or here.lot_geom is None or here.edges is None:
        return None
    front_ft = _yard(got, "setback_front_ft")
    street = tuple((e.x1, e.y1, e.x2, e.y2) for e in here.edges.of_class(EdgeClass.front))
    if front_ft is None or not street:
        return None
    facts = here.facts
    alley, corner = facts.alley, facts.corner
    fix = _fix(fit)
    across = court_across(design, got, alley, corner=corner, fix=fix)
    # A court reached across a side yard (a side street or a side alley):
    # the drive's line is not drawn, so the court's whole depth band is
    # paved from lot line to lot line. A column along a side alley is its
    # own drive and stays unmeasured.
    side_drive = bool(
        design.parking.parks and across.stalls and not across.lane_ft and not facts.alley_at_rear
    )
    if fit.beside:
        # A court BESIDE the building (FOLLOWUPS 4(a)): its aisle is the
        # drive in from the street, so the building and that band are all
        # the plan paves -- drawn where the lot page draws them, never as a
        # court behind the building the plan does not have.
        drawn = _beside_drawn(here, design, got, fit, fitter, env)
        if drawn is None or drawn.court is None:
            return None
        return _largest_left(here, got, side, street, front_ft, fit, [(drawn.building, drawn.court)])
    if side_drive and fit.column:
        return None
    if fit.column:
        column = side_column(design, got, alley)
        court = column[0] if column is not None else 0.0
    else:
        court = court_depth(design, got, alley, corner=corner, fix=fix)[0]
    gap = design.parking.building_gap_ft
    if (stated := got.get("parking_building_buffer_ft")) is not None:
        gap = max(gap, float(stated))
    drawn = draw(
        fitter,
        fit,
        width_ft=design.footprint.width_ft,
        depth_ft=design.footprint.depth_ft,
        lane_ft=across.lane_ft,
        court_depth_ft=court,
        court_beyond_ft=_court_beyond_rear(
            design,
            got,
            env.rear_cut_ft,
            alley,
            column=fit.column and court > 0,
            corner=corner,
            fix=fix,
        ),
        street=street,
        paved_across_ft=None if fit.column else max(across.width_ft, across.lane_ft),
        gap_ft=gap,
        side_drive=side_drive,
    )
    if drawn is None:
        return None
    # A plan the fit passed only on the tolerance draws a room a cell or so
    # short (``drawn.fits`` False): its shapes still stand where the plan
    # does, and whatever they overhang is taken off the ground all the same.
    # The column's side of the room is not drawn: the whole court band goes.
    plans = [(drawn.building, p) for p in drawn.paved] or [
        (drawn.building, drawn.lane, drawn.court)
    ]
    return _largest_left(here, got, side, street, front_ft, fit, plans)


def _largest_left(
    here: QuadfitLot,
    got: ZoneResolution,
    side: Any,
    street: tuple[tuple[float, float, float, float], ...],
    front_ft: float,
    fit: Fit,
    plans: list[tuple[Any, ...]],
) -> float:
    """The largest square left by the best-placed of ``plans`` (each
    the shapes one placement of the plan takes off the lot)."""
    need = got.get("open_space_min_sqft")
    need = float(need) if need is not None else float(side) ** 2
    angles = tuple(a for a in (fit.angle_deg, *map(normalize, here.front_bearings)) if a is not None)
    return max(
        largest_square(
            open_ground(
                here.lot_geom, front_lines=street, front_ft=front_ft, taken=taken, carve=here.carve
            ),
            angles,
            min_area_sqft=need,
        )
        for taken in plans
    )


def _tight_ft(s: Screened) -> float:
    """How far short of the plan the drawing's room may be: the fit's
    tolerance where the screen passed the fit tight (Steph 2026-09-25), else
    nothing -- a plan that missed by more is drawn short, as it is."""
    if not (s.screening.tight_fit or s.signed.tight_fit):
        return 0.0
    return max(
        (c.tolerance for r in (s.screening, s.signed) for c in r.checks if c.check == "fit_ft"),
        default=0.0,
    )


def _map_green(s: Screened) -> bool:
    """Whether either reading of the plan is GREEN on the flag plan's map
    (:attr:`flats.score.screen.Screening.colour`) -- a lot the Lots pages
    show green whatever its triage reads (a minimum density missed is a
    flag below the line, not a wall: FOLLOWUPS 49(a))."""
    return flag_plan.Colour.green in (s.screening.colour, s.signed.colour)


def drawing_for(
    s: Screened,
    fitter: Fitter,
    *,
    street: tuple[tuple[float, float, float, float], ...] | None = None,
    where: Any = None,
    listing: list[Any] | None = None,
    max_front_ft: float | None = None,
) -> dict[str, Any] | None:
    """Where the fit stood this design, for the lot page (FOLLOWUPS 5).

    The same search the verdict read, asked once more for a window: the
    building at the street end, its lane beside it, the court behind it at
    the depth :func:`flats.score.paper.court_depth` charges (or the column
    along a side alley, :func:`flats.score.paper.side_column`; or the court
    BESIDE the building, :func:`flats.score.paper.side_court`), and the room
    the search found around them. Changes no verdict. The building stands
    as near the lot's front lines as named for this screen as the room
    allows -- on a corner lot, the street it was laid out fronting; or at
    ``street``, some of those lines, where the caller names them
    (:func:`fire_checked`). ``where``, ``listing`` and ``max_front_ft`` are
    :func:`flats.fit.draw.draw`'s: a chosen window, or the windows listed
    (:mod:`flats.ingest.flatter`).
    """
    alley, corner = s.lot.facts.alley, s.lot.facts.corner
    rear = s.envelope.rear_cut_ft if s.envelope else None
    if street is None:
        street = _street_lines(s.lot)
    short = _tight_ft(s)
    if s.fit.beside:
        beside = side_court(
            s.design, s.rules, alley, corner=corner, frontage_ft=s.lot.facts.frontage_ft
        )
        beyond = None if beside is None else _beside_beyond(beside, s.fit.required_ft, s.rules, rear)
        if beside is None or beyond is None or math.isinf(beyond):
            return None
        got = draw(
            fitter,
            s.fit,
            width_ft=s.design.footprint.width_ft,
            depth_ft=s.design.footprint.depth_ft,
            lane_ft=0.0,
            court_depth_ft=0.0,
            court_beyond_ft=beyond,
            street=street,
            beside_band_ft=beside.band_ft,
            beside_len_ft=beside.length_ft,
            short_ft=short,
            where=where,
            listing=listing,
            max_front_ft=max_front_ft,
        )
        return None if got is None else got.to_json(s.envelope.geom if s.envelope else None)
    if s.fit.column:
        got = side_column(s.design, s.rules, alley)
        court = got[0] if got is not None else 0.0
    else:
        court = court_depth(s.design, s.rules, alley, corner=corner, fix=_fix(s.fit))[0]
    beyond = _court_beyond_rear(
        s.design,
        s.rules,
        rear,
        alley,
        column=s.fit.column and court > 0,
        corner=corner,
        fix=_fix(s.fit),
    )
    got = draw(
        fitter,
        s.fit,
        width_ft=s.design.footprint.width_ft,
        depth_ft=s.design.footprint.depth_ft,
        lane_ft=court_across(s.design, s.rules, alley, corner=corner).lane_ft,
        court_depth_ft=court,
        court_beyond_ft=beyond,
        street=street,
        short_ft=short,
        where=where,
        listing=listing,
        max_front_ft=max_front_ft,
    )
    if got is None:
        return None
    return got.to_json(s.envelope.geom if s.envelope else None)


#: A stall band's standing in the choice of front: Steph's ruling of
#: 2026-09-19 (HUMAN_TODO 21) prefers the ``preferred`` band.
_BAND_RANK: dict[str | None, int] = {"preferred": 0, "target": 1, "minimum": 2}


def _env_sqft(s: Screened) -> float:
    return s.envelope.sqft if s.envelope is not None else 0.0


def _access_won(
    log: list[dict[str, Any]], tried: list[tuple[Screened, Fitter]], won: Screened
) -> tuple[dict[str, Any], ...]:
    """``log`` with each plan's colour and the plan ``won`` stood on marked."""
    return tuple(
        {**rec, "colour": s.signed.colour.value, "won": s is won}
        for rec, (s, _) in zip(log, tried)
    )


def _front_rank(s: Screened) -> tuple[int, int, int, int, float]:
    """Which of a corner lot's fronts the applicant would choose.

    Steph's ruling of 2026-09-19 (HUMAN_TODO 21): the front that turns the
    lot green, then the one reaching the preferred stall band, then -- where
    quadfit compares the court's exposure to the streets, which the screen
    does not draw -- the one with more room to spare. The colour once signed
    first, as the Lots pages show it (the flag plan's, where a miss is red
    -- FOLLOWUPS 44: on the triage a miss with a variance path read yellow
    and outranked a front that fits but waits on an open fact), then its
    triage; the colour today breaks a tie.
    """
    slack = s.screening.fit_slack_ft
    return (
        _COLOUR[s.signed.colour],
        _RANK[s.signed.triage.value],
        _RANK[s.screening.triage.value],
        _BAND_RANK.get(s.screening.parking_band, 3),
        -(slack if slack is not None else -math.inf),
    )


def row_for(s: Screened) -> dict[str, Any]:
    """One flat record per lot x design, what the batch writes."""
    leaning = s.config.leans_on(s.rules.levers)
    failing = tuple(c.check for c in s.screening.checks if c.verdict is CheckVerdict.fails)
    # The flag plan's record, on the colour the map shows (as if signed --
    # Steph 2026-10-02). The write gate: an incomplete flag stops here.
    flag_plan.validate(s.signed.flags)
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
        "tight_fit": s.screening.tight_fit,
        "warnings": ",".join(s.screening.warnings),
        "fit_column": s.fit.column,
        "front_deg": s.front_deg,
        "side_street_lane": side_street_fed(s.rules, s.lot.facts.alley, s.lot.facts.corner),
        "access_json": json.dumps(s.access, separators=(",", ":")) if s.access else None,
        "fire_why": s.fire_why,
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
        "drawing": json.dumps(s.drawing, separators=(",", ":")) if s.drawing else None,
        "fire_route_ft": s.facts.fire_route_ft if s.facts is not None else None,
        "steep_sqft": s.facts.steep_sqft if s.facts is not None else None,
        "steep_source": s.facts.steep_source if s.facts is not None else None,
        "steep_blocks": bool(s.facts.steep_blocks) if s.facts is not None else False,
        "steep_unconfirmed": bool(s.facts.steep_unconfirmed) if s.facts is not None else False,
        "site_grade_pct": s.facts.site_grade_pct if s.facts is not None else None,
        "site_grade_source": s.facts.site_grade_source if s.facts is not None else None,
        "colour": s.signed.colour.value,
        "flags": flag_plan.dumps(s.signed.flags, lot=s.lot.tlid),
        "binds": flag_plan.dumps(s.signed.binds),
        # The room each passing standard had to spare (FOLLOWUPS 37(ii)):
        # for the pod design report, never read by the colour.
        "margins": margin_record.dumps(s.signed.margins),
        # And how much bigger the pod could be, each way, on the lot's own
        # shape (FOLLOWUPS 37(ii)); None where it was not measured.
        "room_width_ft": round(s.room.width_ft, 3) if s.room is not None else None,
        "room_depth_ft": round(s.room.depth_ft, 3) if s.room is not None else None,
        "room_both_ft": round(s.room.both_ft, 3) if s.room is not None else None,
        # The sidewalk easement the street setbacks were measured from, at
        # its worst (FOLLOWUPS 41(iii)); None where no code asks.
        "sidewalk_easement_ft": s.lot.sidewalk_easement_ft,
    }


# --- the batch ---------------------------------------------------------------

_WORKER: dict[str, Any] = {}


def _init_worker(
    step_deg: float,
    sources: Path | None = None,
    roads: Path | None = None,
    dem: Path | None = None,
    curbs: Path | None = None,
) -> None:
    """Load the corpus, catalog, policies, corridor maps, the street
    centrelines the fire route is measured to (with the curbs and widths
    of ``curbs``, a snapshot directory) and the elevation models the slope
    is read off, once per process."""
    from flats.designs.model import load_catalog
    from flats.encode.load import load_trusted
    from flats.fit.fire import load_truck_roads
    from flats.geom.curbs import load as load_street_edges
    from flats.score import relief as relief_mod, slack as slack_mod

    _WORKER["rules"] = load_trusted(strict=False).rules
    _WORKER["designs"] = list(load_catalog())
    _WORKER["policy"] = slack_mod.load_policy()
    _WORKER["relief"] = relief_mod.load_policy()
    _WORKER["step_deg"] = step_deg
    _WORKER["corridors"] = load_corridor_maps(sources) if sources is not None else ()
    street_edges = load_street_edges(curbs) if curbs is not None and roads is not None else None
    _WORKER["roads"] = (
        (*load_truck_roads(roads, street_edges), street_edges) if roads is not None else None
    )
    _WORKER["terrain"] = terrain_at(dem) if dem is not None else None


def terrain_at(raw: Path) -> Any:
    """The elevation models under quadfit's raw directory: s0's 1 m tiles
    (``dem``) and the ~10 m model warped beside them (``dem10_utm``)."""
    from flats.fit.slope import Terrain

    return Terrain(raw / "dem", raw / "dem10_utm")


def _work_chunk(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        lot = lot_from_row(row, _WORKER["rules"].layers, _WORKER["corridors"])
        lot = with_steep(lot, _WORKER.get("terrain"))
        for s in screen_lot(
            lot,
            _WORKER["designs"],
            rules=_WORKER["rules"],
            policy=_WORKER["policy"],
            relief=_WORKER["relief"],
            step_deg=_WORKER["step_deg"],
            roads=_WORKER.get("roads"),
            terrain=_WORKER.get("terrain"),
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
    # The head is what is nearly solved, not why the lot is red: a lot a
    # hair over its coverage and half a lot short on flat ground reads
    # "coverage" (FOLLOWUPS 49(g), run 65). The check missed by the largest
    # share of its limit says why.
    if "dominant" in red_where_green:
        lines.append("Missed by most (dominant) -- why it is red:\n")
        lines.append(_counts(red_where_green["dominant"].fillna("(none)")) + "\n")
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


def _default_dem(s4: Path) -> Path:
    """The elevation models for a stage tree: its own ``raw`` when it holds
    1 m tiles, else the July ``quadfit/raw`` beside it.

    The July tree stops short of Washington County (no 1 m tile, and the
    10 m model ends at about -122.95), so a Washington lot screened off it
    is never graded; the stage tree is staged with every county's tiles
    (``--dem-from``) and is preferred.
    """
    own = s4.parent / "raw"
    return own if any((own / "dem").glob("*.tif")) else s4.parents[1] / "quadfit" / "raw"


def _is_reading(path: Path) -> bool:
    from flats.ingest.institutional import INSTITUTIONAL

    return path.is_file() or (path / INSTITUTIONAL).is_file()


def _institutional_source(institutional: Path | None, sources: Path | None) -> Path:
    """The institutional reading, or the snapshot to read it from; refused
    when there is neither -- Steph ruled those lots out of EVERY scan."""
    from flats.geom.institutional import missing

    path = institutional if institutional is not None else sources
    if path is not None and (_is_reading(path) or not missing(path)):
        return path
    lacking = ", ".join(missing(path))
    raise FileNotFoundError(
        f"no institutional land for this scan ({lacking} not in {path}): schools, parks and the "
        "rest are left out of every scan (FOLLOWUPS 47) -- pass --institutional a reading from "
        "flats.ingest.institutional or a snapshot holding osm_land_use and rlis_orca "
        "(acquire --keys osm_land_use rlis_orca)"
    )


def _read_institutional(rows: list[dict[str, Any]], snapshot: Path, out: Path) -> Path:
    """Read the lots this run screens against ``snapshot`` and write the
    reading beside the run, where assign finds it through ``meta.json``."""
    import pandas as pd

    from flats.geom.institutional import load
    from flats.ingest.institutional import INSTITUTIONAL, measure

    land = load(snapshot)
    assert land is not None
    lots = pd.DataFrame(
        {
            # "or/washington/hillsboro" -> "washington", as the lot table names it.
            "county": [(str(r.get("jurisdiction") or "").split("/") + ["", ""])[1] for r in rows],
            "tlid": [str(r["TLID"]) for r in rows],
            "wkb": [r.get("lot_wkb") for r in rows],
        }
    )
    path = out / INSTITUTIONAL
    measure(lots, land).to_parquet(path, index=False)
    return path


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
    zones: Iterable[str] = (),
    tlids: Iterable[str] = (),
    step_deg: float = DEFAULT_STEP_DEG,
    chunk_size: int = 500,
    sources: Path | None = None,
    transit: Path | None = None,
    roads: Path | None = None,
    dem: Path | None = None,
    curbs: Path | None = None,
    institutional: Path | None = None,
    cache: Path | None = None,
    log: Any = print,
) -> Path:
    """Screen every lot and write ``lots.parquet``, ``meta.json``, ``summary.md``.

    Parts are written as they finish (``parts/NNNNN.parquet``) and
    concatenated at the end, so a run that dies at hour three keeps its
    first three hours. Re-running with the same ``out`` starts over, but
    for the lots ``cache`` holds -- and the command keeps one by default,
    so a re-launch resumes (FOLLOWUPS 48).
    ``sources`` is a snapshot directory (``data/flats/sources/<date>``) whose
    corridor maps answer the corridor facts; without it they stay unasked.
    ``transit`` is the distance file :mod:`flats.ingest.transit` wrote for
    the transit release in use; without it no lot has a distance to transit.
    ``roads`` is quadfit s1's street centrelines (``s1_streets.parquet``),
    which the fire route is measured to; it defaults to the file beside
    ``s4`` and a run without one is refused -- measured from the lot line,
    the route would come out SHORTER than the hose's (FOLLOWUPS 28).
    ``dem`` is quadfit's raw directory holding the elevation models
    (:func:`terrain_at`); it defaults to the stage directory's own ``raw``
    (staged with the county's tiles), else ``quadfit/raw`` beside it, and a
    run without 1 m tiles there is refused -- without them
    no lot is graded and Steph's slope ruling silently goes unchecked
    (FOLLOWUPS 38). ``curbs`` is a snapshot directory holding the published
    curb lines and pavement widths (:mod:`flats.geom.curbs`); it defaults to
    ``sources``, and a run whose snapshot lacks one of them is refused -- a
    street none measures is taken as the narrowest, so without them every
    Portland street would be (FOLLOWUPS 29). ``institutional`` is the
    reading :mod:`flats.ingest.institutional` wrote for the snapshot, or a
    snapshot directory holding ``osm_land_use`` and ``rlis_orca`` (the run
    then reads the lots it screens itself and writes the reading beside its
    output); it defaults to ``sources``. Its lots -- schools, parks,
    hospitals, utilities -- are left out of the scan and assign answers them
    RED (Steph 2026-10-06, FOLLOWUPS 47: "flagged out of scans for any
    reason" -- every scan, a test scan included), and a run with neither is
    refused.

    The lots run costliest first and ``timings.parquet`` says what each
    cost (:mod:`flats.ingest.batch`). ``cache`` is a directory of answers
    kept by earlier runs: a lot whose row, code, packages, step and input
    files are all unchanged is read from it instead of screened, and every
    lot screened is kept there -- the BEFORE side of a bound is computed
    once, not on every retry (FOLLOWUPS 46).
    """
    import time

    from flats.geom.curbs import missing as curbs_missing
    from flats.ingest import batch

    roads = roads if roads is not None else s4.parent / "s1_streets.parquet"
    curbs = curbs if curbs is not None else sources
    if not roads.exists():
        raise FileNotFoundError(f"no street centrelines for the fire route: {roads}")
    dem = dem if dem is not None else _default_dem(s4)
    if not any((dem / "dem").glob("*.tif")):
        raise FileNotFoundError(f"no 1 m elevation tiles for the slope: {dem / 'dem'}")
    if lacking := curbs_missing(curbs):
        raise FileNotFoundError(
            f"no {', '.join(lacking)} for where the fire truck stands in {curbs}: "
            "run acquire, or pass --curbs a snapshot that holds them"
        )
    institutional = _institutional_source(institutional, sources)
    out.mkdir(parents=True, exist_ok=True)
    parts_dir = out / "parts"
    parts_dir.mkdir(exist_ok=True)
    for old in parts_dir.glob("*.parquet"):
        old.unlink()

    zones, tlids = sorted(zones), sorted(tlids)
    rows = list(
        iter_rows(
            s4, s5o, transit=transit, limit=limit, sample=sample, seed=seed,
            jurisdictions=jurisdictions, zones=zones, tlids=tlids, streets=roads,
        )
    )
    if not _is_reading(institutional):
        institutional = _read_institutional(rows, institutional, out)
    from flats.ingest.institutional import skip_tlids

    skip = skip_tlids(institutional)
    kept = [r for r in rows if str(r["TLID"]).rstrip() not in skip]
    skipped = len(rows) - len(kept)
    rows = kept
    log(f"bridge: {skipped:,} institutional lots left out of the scan ({institutional})")
    classed = with_local_street(rows, sources)
    if classed:
        log(f"bridge: street class read on {classed:,} lots")
    eased = with_sidewalk_easement(rows, sources)
    if eased:
        log(f"bridge: worst-case sidewalk easement taken on {eased:,} lots")
    # Costliest lots first, started as free memory allows, and the answers a
    # cache already holds not screened again (FOLLOWUPS 46): the same
    # records in the same order as lot by lot in file order.
    answers = None
    if cache is not None:
        batch.prune(cache)
        answers = batch.AnswerCache(
            cache,
            batch.run_key(
                step_deg=step_deg,
                inputs={"sources": sources, "roads": roads, "dem": dem, "curbs": curbs},
            ),
        )
    # The workers screen with flats.ingest.quadfit's _work_chunk, so they are
    # set up by that module's _init_worker -- under `python -m` this file is
    # __main__, a second copy whose _WORKER the screen never reads.
    from flats.ingest import quadfit as screened

    t0 = time.time()
    frame, timings, done = batch.screen_rows(
        rows,
        parts_dir,
        processes=processes,
        chunk_size=chunk_size,
        init=screened._init_worker,
        initargs=(step_deg, sources, roads, dem, curbs),
        cache=answers,
        step_deg=step_deg,
        log=log,
    )
    timings.to_parquet(out / "timings.parquet", index=False)
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
        "zones": zones,
        "tlids": tlids,
        "sources": str(sources) if sources is not None else None,
        "transit": str(transit) if transit is not None else None,
        "roads": str(roads),
        "dem": str(dem),
        "curbs": str(curbs) if curbs is not None else None,
        "institutional": str(institutional),
        "institutional_skipped": skipped,
        "batch": done.meta(),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if results is not None and results.exists() and len(frame):
        (out / "summary.md").write_text(compare(frame, results), encoding="utf-8")
    log(f"bridge: wrote {len(frame):,} rows to {out / 'lots.parquet'} in {meta['seconds']}s")
    return out / "lots.parquet"


def _read_tlids(path: Path) -> list[str]:
    return [t.strip() for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]


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
    ap.add_argument("--zone", action="append", default=[], help="<jurisdiction>:<zone>, repeatable")
    ap.add_argument("--tlid", action="append", default=[])
    ap.add_argument("--tlid-file", type=Path, help="one TLID per line")
    ap.add_argument("--step-deg", type=float, default=DEFAULT_STEP_DEG)
    ap.add_argument("--chunk-size", type=int, default=500)
    ap.add_argument("--sources", type=Path, help="snapshot dir holding the corridor maps")
    ap.add_argument("--transit", type=Path, help="distances.parquet from flats.ingest.transit")
    ap.add_argument(
        "--roads",
        type=Path,
        help="street centrelines for the fire route (default: s1_streets beside --s4)",
    )
    ap.add_argument(
        "--dem",
        type=Path,
        help="quadfit raw dir holding dem/ and dem10_utm/ (default: ../quadfit/raw from --s4)",
    )
    ap.add_argument(
        "--curbs",
        type=Path,
        help="snapshot dir holding the curb lines and pavement widths (default: --sources)",
    )
    ap.add_argument(
        "--institutional",
        type=Path,
        help="institutional.parquet (or its directory) from flats.ingest.institutional, or a snapshot "
        "holding osm_land_use and rlis_orca: lots left out of the scan (default: --sources; refused without)",
    )
    ap.add_argument(
        "--cache",
        type=Path,
        help="answer cache dir: unchanged lots are read from it, screened lots kept in it, so a "
        "re-launch resumes (default: bridge_cache beside --out)",
    )
    ap.add_argument("--no-cache", action="store_true", help="screen every lot afresh and keep no answers")
    args = ap.parse_args(argv)
    # A run that dies resumes when it is launched again, by default: every
    # chunk it finished is in the cache (FOLLOWUPS 48, Steph 2026-10-07:
    # "Don't want to lose time to avoidable problems"). Beside --out, runs
    # in one directory share it -- on 137 that is /root/bridge_cache.
    cache = None if args.no_cache else args.cache or args.out.resolve().parent / "bridge_cache"
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
        zones=args.zone,
        tlids=[*args.tlid, *(_read_tlids(args.tlid_file) if args.tlid_file else [])],
        step_deg=args.step_deg,
        chunk_size=args.chunk_size,
        sources=args.sources,
        transit=args.transit,
        roads=args.roads,
        dem=args.dem,
        curbs=args.curbs,
        institutional=args.institutional,
        cache=cache,
    )
    return 0


__all__ = [
    "CLACKAMAS",
    "LOTS_RESULTS",
    "OBSERVABLE",
    "DOUBTFUL_STREET_KINDS",
    "DRIVE_STREET_KINDS",
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
    "scope_mask",
    "lot_edges",
    "lot_from_row",
    "observed_facts",
    "per_lot",
    "rear_off_alley",
    "row_for",
    "run",
    "screen_lot",
    "setbacks_for",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
