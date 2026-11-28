"""The answer keys' own settings, as explicit overrides of the shipped file.

Production (``flats/config/foundation.yaml``) measures and prices the FRAMING
footprint, 79 ft 8-3/4 in x 24 ft 8-15/16 in, centred in the 80 x 25 ft
finished faces (DECISIONS N-finished, Factory-Sim FOLLOWUPS 238(i)), with FD8's
real doors, precast steps, six-step cap, code numbers and section 2d rows
(FOLLOWUPS 213).

Three keys are reproduced here, each as an override, so each proof stands
while production carries the new settings. No tolerance changes with them.

* :func:`key_settings` -- the FD6 reference model (``FD6_foundation_model.py``
  key issue 1), its tables and FD7's cases: 80 x 25 ft walls, party lines at
  20 / 40 / 60 ft, doors at 10 / 30 / 50 / 70 ft on both faces, FD3's
  80 ft 3-3/4 in for the fixed lines, and FLATS's settings before FD8
  (:data:`BEFORE_FD8`).
* :func:`as_flats_built` -- ``FD6_foundation_model.py --as-flats-built`` (FD8
  section 3): the framing size on FLATS's settings before FD8, doors mid-home
  on both faces.
* :func:`fd8_table` -- FD8 section 3 "the same test lots under Steph's
  decisions": the shipped settings with the section 2d rows switched off (the
  table was worked with the precast rule, the cap and the real doors only)
  and the footing 18 in below the ground on every lot.
"""

from __future__ import annotations

from decimal import Decimal

from flats.foundation import settings
from flats.foundation.settings import Price, Settings

#: The per-riser prices FLATS ran before FD8 (FD6 section 6).
PER_RISER = {
    "riser": Price(Decimal(60), Decimal(130), "per riser (B every riser; A every riser after the first)",
                   "low: treated wood built on site, materials [est]; high: precast steps, installed [vendor listing]"),
    "rail_ft": Price(Decimal(15), Decimal(85), "per ft", "low: wood, materials [est]; high: iron, installed [vendor listing]"),
}

#: FLATS's settings before FD8 (foundation.yaml at 5a7b7e1c), other than size.
BEFORE_FD8 = {
    "steps_rule": "per_riser",
    "riser_in": 7.75,
    "tread_in": 10.0,
    "landing_depth_in": 36.0,
    "level_bar_third_over_in": 48.0,
    "footing_w_end_in": 12.0,
    "footing_w_party_in": 14.0,
    "stepped_footing": False,
    "stair_ground": False,
    "guard_box": False,
    "fill_flag_with_strip": False,
}

#: The answer key's dimensions (FD6 spec section 4, FD3 ``POD_L_FT`` = 963.75 / 12).
KEY_DIMS = {
    "finished_length_ft": 80.0,
    "finished_width_ft": 25.0,
    "length_ft": 80.0,
    "width_ft": 25.0,
    "party_x_ft": (20.0, 40.0, 60.0),
    "door_x_front_ft": (10.0, 30.0, 50.0, 70.0),
    "door_x_back_ft": (10.0, 30.0, 50.0, 70.0),
    "fixed_length_ft": 963.75 / 12,
}


def _with_prices(s: Settings, **changes: object) -> Settings:
    return s.replace(prices={**s.prices, **PER_RISER}, **changes)


def key_settings(s: Settings | None = None, **more: object) -> Settings:
    """``s`` (default: the shipped settings) on the FD6 answer key's dimensions
    and FLATS's settings before FD8."""
    return _with_prices(s if s is not None else settings.load(), **BEFORE_FD8, **KEY_DIMS, **more)


def as_flats_built(s: Settings | None = None, **more: object) -> Settings:
    """FD8 section 3 ``--as-flats-built``: the framing size on the settings
    before FD8, doors mid-home on both faces (10 / 30 / 50 / 70 ft on 80 ft,
    scaled to the framing)."""
    s = s if s is not None else settings.load()
    mid = tuple(x * s.length_ft / 80.0 for x in (10.0, 30.0, 50.0, 70.0))
    return _with_prices(s, **BEFORE_FD8, door_x_front_ft=mid, door_x_back_ft=mid, use_frost_register=False, **more)


def fd8_table(s: Settings | None = None, **more: object) -> Settings:
    """FD8 section 3 "under Steph's decisions": the shipped rules with the
    section 2d rows off and the footing at ``embed_in`` on every lot."""
    s = s if s is not None else settings.load()
    return s.replace(stepped_footing=False, stair_ground=False, guard_box=False, use_frost_register=False, **more)
