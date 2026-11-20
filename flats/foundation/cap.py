"""The six-step cap on a lot (FD8 2a; Steph 2026-11-20).

A foundation method with any door over ``cap_risers`` precast unit risers (the
floor more than ``cap_in`` = 51.5 in above the ground the stair is tested on)
is not used on the lot. Per lot (rulings.yaml):

* ``2026-11-20-foundation-six-step-cap-red`` -- RED only when every method open
  to the lot fails the cap.
* ``2026-11-20-foundation-near-cap-yellow`` -- where every method fails but the
  best one's worst door is over by ``near_cap_in`` (2 in) or less, YELLOW with a
  flag naming the door; never GREEN, not RED.
* Within ``near_cap_in`` under the cap: a note, no colour.
* The conservative rule for an unread ground class: a lot whose ground class
  is not read or not sorted may turn out to need piles, where only B+P is
  open; with A under the cap and B over it, YELLOW.

The methods open to the cap are not the methods a lot is *compared* on
(:data:`flats.foundation.support.APPLICABLE`): ordinary ground, ground that
needs its own look and ground not sorted can take A or B; soft or swelling
ground only B+P (FOLLOWUPS 213 brief). B's floor stands above A's at every
door, so on the first three the lot is red exactly when A is over.

Never a colour by itself: :mod:`flats.ingest.foundation_cap` turns a
:class:`Cap` into the screen's reason and flags.
"""

from __future__ import annotations

from dataclasses import dataclass

from flats.foundation import model, support
from flats.foundation.model import MethodResult
from flats.foundation.settings import Settings

RED = "over_cap"
NEAR = "near_cap"
CLASS_UNREAD = "class_unread"
CLOSE = "close_under_cap"
FITS = "fits"
STATES = (RED, NEAR, CLASS_UNREAD, CLOSE, FITS)

#: Methods open to the cap, by ground-support group (FOLLOWUPS 213 brief).
CAP_OPEN: dict[str, tuple[str, ...]] = {
    support.ORDINARY: ("A dry", "B"),
    support.OWN_LOOK: ("A dry", "B"),
    support.NOT_SORTED: ("A dry", "B"),
    support.PILES: ("B+P",),
}

#: Counts in words, as the reason reads ("more than six steps").
_SAID = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def said(n: int) -> str:
    return _SAID.get(n, str(n))


#: The short name a method goes by on the page.
SHORT = {"A dry": "A", "A wet": "A", "B": "B", "B+P": "B+P"}


@dataclass(frozen=True, slots=True)
class Cap:
    state: str
    group: str
    #: The methods open to the cap here, and which of them clear it.
    open_methods: tuple[str, ...]
    clear: tuple[str, ...]
    #: The open method whose worst door stands lowest, its worst door, the
    #: floor there above the ground the stair is tested on, and how far that
    #: is over (+) or under (-) the cap (in).
    best: str
    door: str
    height_in: float
    over_by_in: float
    cap_in: float
    words: str

    @property
    def colour_moves(self) -> bool:
        return self.state in (RED, NEAR, CLASS_UNREAD)

    def facts(self) -> dict[str, object]:
        return {
            "state": self.state,
            "group": self.group,
            "open_methods": list(self.open_methods),
            "clear": list(self.clear),
            "best": self.best,
            "door": self.door,
            "height_in": round(self.height_in, 1),
            "over_by_in": round(self.over_by_in, 1),
            "cap_in": self.cap_in,
            "words": self.words,
        }


def _worst(r: MethodResult) -> tuple[str, float]:
    d = r.worst_door()
    return model.door_name(d, r.doors), d.cap_height_in if d.cap_height_in is not None else d.height_in


def cap_of(methods: dict[str, MethodResult], group: str, s: Settings) -> Cap:
    """The cap on one lot from its priced methods (:func:`flats.foundation.lot.assess`)."""
    if group not in CAP_OPEN:
        raise ValueError(f"unknown ground-support group {group!r}")
    open_methods = CAP_OPEN[group]
    clear = tuple(name for name in open_methods if not methods[name].over_cap)
    ranked = sorted(open_methods, key=lambda name: _worst(methods[name])[1])
    best = ranked[0]
    door, height = _worst(methods[best])
    over_by = height - s.cap_in
    where = f"{SHORT[best]}: {door} is {height:.1f} in above the ground"
    if not clear:
        if over_by <= s.near_cap_in + s.tolerance_in:
            state = NEAR
            words = (f"foundation: within {s.near_cap_in:g} in of the {s.cap_risers}-step cap on the best method "
                     f"({where}, {over_by:.1f} in over the {s.cap_in:g} in cap); ground heights are good to an "
                     "inch or two, so yellow, not red (Steph 2026-11-20)")
        else:
            state = RED
            words = (f"foundation: a door needs more than {said(s.cap_risers)} steps on every method "
                     f"(best {where}, {over_by:.1f} in over the {s.cap_in:g} in cap)")
    elif group == support.NOT_SORTED and "B" in open_methods and methods["B"].over_cap:
        state = CLASS_UNREAD
        bdoor, bh = _worst(methods["B"])
        words = (f"foundation: the ground class is not read; A clears the {s.cap_risers}-step cap but B does not "
                 f"(B: {bdoor} is {bh:.1f} in above the ground, {bh - s.cap_in:.1f} in over), and soft or "
                 "swelling ground would leave only B on piles")
    elif over_by > -s.near_cap_in - s.tolerance_in:
        state = CLOSE
        words = (f"foundation: within {s.near_cap_in:g} in under the {s.cap_risers}-step cap "
                 f"({where}, {-over_by:.1f} in under)")
    else:
        state = FITS
        words = f"foundation: every door within {s.cap_risers} steps on {SHORT[best]} ({where})"
    return Cap(state, group, open_methods, clear, best, door, height, over_by, s.cap_in, words)


__all__ = ["CAP_OPEN", "CLASS_UNREAD", "CLOSE", "FITS", "NEAR", "RED", "STATES", "Cap", "cap_of"]
