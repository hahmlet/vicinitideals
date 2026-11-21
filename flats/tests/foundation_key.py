"""The FD6 answer key's own building dimensions, as explicit overrides.

Production (``flats/config/foundation.yaml``) measures and prices the FRAMING
footprint, 79 ft 8-3/4 in x 24 ft 8-15/16 in, centred in the 80 x 25 ft
finished faces (DECISIONS N-finished, Factory-Sim FOLLOWUPS 238(i)). The FD6
reference model (``FD6_foundation_model.py``), its tables and FD7's cases are
still worked on the old sizes: 80 x 25 ft walls, party lines at 20 / 40 / 60 ft,
doors at 10 / 30 / 50 / 70 ft, and FD3's 80 ft 3-3/4 in for the fixed lines.
The tests that prove this model does the reference's arithmetic run it on
those dimensions, so the proof stands while production carries the new size.
No tolerance changes with it.
"""

from __future__ import annotations

from flats.foundation import settings
from flats.foundation.settings import Settings

#: The answer key's dimensions (FD6 spec section 4, FD3 ``POD_L_FT`` = 963.75 / 12).
KEY_DIMS = {
    "finished_length_ft": 80.0,
    "finished_width_ft": 25.0,
    "length_ft": 80.0,
    "width_ft": 25.0,
    "party_x_ft": (20.0, 40.0, 60.0),
    "door_x_ft": (10.0, 30.0, 50.0, 70.0),
    "fixed_length_ft": 963.75 / 12,
}


def key_settings(s: Settings | None = None, **more: object) -> Settings:
    """``s`` (default: the shipped settings) on the answer key's dimensions."""
    return (s if s is not None else settings.load()).replace(**KEY_DIMS, **more)
