"""The frost-depth register (FOLLOWUPS 197): what depth below grade a footing
must reach against frost, for the place a lot is in. A NOTE for the lot report
and the lot page, read by the foundation-design agent downstream -- nothing the
screen, the colour, a check or a flag reads comes from here.

``flats/config/frost_depth.yaml`` holds, as printed, the state table figure per
county (2023 ORSC Table R301.2), each county building department's own figure,
and every place FLATS screens: ``found`` (the place prints a figure, adopted or
practice), ``silent`` (we read where it would be stated and it states none) or
``not_read`` (the document could not be obtained). Steph's ruling
``2026-11-18-frost-depth-silent-falls-back``: a silent place takes the county
department's figure, else the state figure, flagged with its level. A place not
read gets no fallback; the note shows the state figure for reference only.

The YAML stores each source's printed figure token (``12"``, ``18e``,
``12 inches``) and the sentence it sits in; the inches are derived here, and a
figure that is not inside its own quote fails the load.

No lot elevation is held, so the note gives the figure for the lowest
elevation band and lists every higher band as a caveat.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PATH = Path(__file__).parent / "config" / "frost_depth.yaml"

OUTCOMES = ("found", "silent", "not_read")
KINDS = ("adopted", "practice")
COUNTIES = ("multnomah", "clackamas", "washington")

_KIND_WORDS = {
    "adopted": "adopted code",
    "practice": "department practice, not adopted code",
}
_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)?)")


def inches(figure: str) -> float:
    """The inches a printed figure token states: ``12"`` / ``12”`` / ``18e`` /
    ``12 inches`` -> the leading number. The unit is always inches here (the
    state table's column is "Frost line depth (inches)")."""
    m = _NUMBER.match(str(figure))
    if not m:
        raise ValueError(f"frost figure {figure!r} does not start with a number")
    value = float(m.group(1))
    return int(value) if value.is_integer() else value


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def _bands(where: str, raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{where}: bands must be a non-empty list")
    out = []
    for i, band in enumerate(raw):
        here = f"{where} band {i}"
        if not isinstance(band, dict) or "figure" not in band or "quote" not in band:
            raise ValueError(f"{here}: needs figure and quote")
        figure, quote = str(band["figure"]), _squash(band["quote"])
        if _squash(figure) not in quote:
            raise ValueError(f"{here}: figure {figure!r} is not in its quote")
        lo, hi = band.get("from_ft"), band.get("below_ft")
        if lo is not None and hi is not None and not lo < hi:
            raise ValueError(f"{here}: from_ft must be below below_ft")
        out.append({"figure": figure, "quote": quote, "inches": inches(figure), "from_ft": lo, "below_ft": hi})
    out.sort(key=lambda b: b["from_ft"] or 0)
    if out[0]["from_ft"]:
        raise ValueError(f"{where}: the lowest band must start at the ground (no from_ft)")
    for lower, upper in zip(out, out[1:]):
        if lower["below_ft"] is None or upper["from_ft"] != lower["below_ft"]:
            raise ValueError(f"{where}: bands must meet end to start")
    return out


def _source(where: str, entry: dict[str, Any]) -> None:
    if entry.get("kind") not in KINDS:
        raise ValueError(f"{where}: kind must be one of {KINDS}")
    for key in ("document", "cite", "read_on"):
        if not entry.get(key):
            raise ValueError(f"{where}: a found figure needs {key}")
    entry["bands"] = _bands(where, entry.get("bands"))


@lru_cache(maxsize=4)
def load(path: Path = PATH) -> dict[str, Any]:
    """The register, validated whole: a bad entry raises ``ValueError`` naming
    it (an agent reads this as authority, so it must not be half-read)."""
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    state = doc.get("state") or {}
    for key in ("edition", "document", "cite"):
        if not state.get(key):
            raise ValueError(f"state: needs {key}")
    for county in COUNTIES:
        entry = (state.get("counties") or {}).get(county)
        if not entry:
            raise ValueError(f"state: no table row for {county}")
        entry["bands"] = _bands(f"state {county}", entry.get("bands"))

    counties = doc.get("counties") or {}
    for county in COUNTIES:
        entry = counties.get(county)
        if not entry or entry.get("outcome") not in ("found", "silent"):
            raise ValueError(f"county {county}: outcome must be found or silent")
        if entry["outcome"] == "found":
            _source(f"county {county}", entry)
        elif not entry.get("read"):
            raise ValueError(f"county {county}: silent needs what was read")

    for jid, entry in (doc.get("places") or {}).items():
        where = f"place {jid}"
        if not entry.get("name"):
            raise ValueError(f"{where}: needs a name")
        if entry.get("use_county"):
            if entry["use_county"] not in counties:
                raise ValueError(f"{where}: use_county {entry['use_county']!r} is not a county entry")
            continue
        outcome = entry.get("outcome")
        if outcome not in OUTCOMES:
            raise ValueError(f"{where}: outcome must be one of {OUTCOMES}")
        if outcome == "found":
            _source(where, entry)
        elif outcome == "silent" and not entry.get("read"):
            raise ValueError(f"{where}: silent needs what was read (the ruling covers only a place we read)")
        elif outcome == "not_read" and not entry.get("reason"):
            raise ValueError(f"{where}: not_read needs the reason")
    return doc


def _higher(bands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"from_ft": b["from_ft"], "below_ft": b["below_ft"], "inches": b["inches"], "figure": b["figure"]}
        for b in bands[1:]
    ]


def _ft(value: int) -> str:
    return f"{value:,} ft"


def _band_words(bands: list[dict[str, Any]]) -> str:
    parts = []
    for b in bands:
        if b["from_ft"] is None and b["below_ft"] is None:
            parts.append(f"{b['inches']} in")
        elif b["from_ft"] is None:
            parts.append(f"{b['inches']} in below {_ft(b['below_ft'])}")
        elif b["below_ft"] is None:
            parts.append(f"{b['inches']} in from {_ft(b['from_ft'])}")
        else:
            parts.append(f"{b['inches']} in from {_ft(b['from_ft'])} to {_ft(b['below_ft'])}")
    return "; ".join(parts)


def _state(doc: dict[str, Any], county: str | None) -> dict[str, Any] | None:
    state = doc["state"]
    row = state["counties"].get((county or "").lower())
    if not row:
        return None
    bands = row["bands"]
    return {
        "inches": bands[0]["inches"],
        "figure": bands[0]["figure"],
        "quote": bands[0]["quote"],
        "below_ft": bands[0]["below_ft"],
        "higher_ground": _higher(bands),
        "bands_words": _band_words(bands),
        "edition": state["edition"],
        "document": state["document"],
        "url": state.get("url"),
        "cite": state["cite"],
        "next_edition": _squash(state.get("next_edition") or "") or None,
        "higher_ground_next_edition": _squash(row.get("higher_ground_next_edition") or "") or None,
    }


def describe(jurisdiction: str | None, county: str | None, *, path: Path = PATH) -> dict[str, Any]:
    """The frost-depth note for one lot, from its jurisdiction and county.

    ``inches`` is the figure for the lowest elevation band of whichever source
    governs (the place's own, the county's, else the state's); ``level`` says
    whose it is. A place not read has ``inches`` None and ``state`` for
    reference only."""
    doc = load(path)
    county_key = (county or "").lower()
    state = _state(doc, county_key)
    entry = (doc.get("places") or {}).get(jurisdiction or "")
    place = (entry or {}).get("name") or (jurisdiction or "").split(":", 1)[-1].split("/")[-1].replace("-", " ").title()
    note: dict[str, Any] = {
        "never_a_colour": True,
        "jurisdiction": jurisdiction,
        "county": county_key or None,
        "place": place,
        "permits_by": _squash((entry or {}).get("permits_by") or "") or None,
        "outcome": "not_read",
        "level": None,
        "kind": None,
        "inches": None,
        "figure": None,
        "quote": None,
        "document": None,
        "url": None,
        "cite": None,
        "read_on": None,
        "drawn": False,
        "below_ft": None,
        "higher_ground": [],
        "read": [],
        "caveats": [],
        "state": state,
        "above_state": False,
        "read_on_register": str(doc.get("read_on")),
    }

    source: dict[str, Any] | None = None
    if entry and entry.get("use_county"):
        c = doc["counties"][entry["use_county"]]
        note["permits_by"] = note["permits_by"] or _squash(c.get("permits_by") or c["name"])
        note["outcome"] = c["outcome"]
        if c["outcome"] == "found":
            source, note["level"] = c, "county"
        else:
            note["read"] = [_read(r) for r in c.get("read") or []]
            note["level"] = "state"
        if c.get("caveat"):
            note["caveats"].append(_squash(c["caveat"]))
    elif entry and entry["outcome"] == "found":
        note["outcome"], source, note["level"] = "found", entry, "city"
    elif entry and entry["outcome"] == "silent":
        note["outcome"] = "silent"
        note["read"] = [_read(r) for r in entry.get("read") or []]
        c = doc["counties"].get(county_key)
        if c and c["outcome"] == "found":
            source, note["level"] = c, "county"
        else:
            note["level"] = "state"
    elif entry:
        note["caveats"].append(_squash(entry["reason"]))
    else:
        note["caveats"].append("This place is not in the frost register: its building department was never read.")

    if entry and entry.get("caveat") and not entry.get("use_county"):
        note["caveats"].insert(0, _squash(entry["caveat"]))
    if source is not None and source is not entry and source.get("caveat"):
        note["caveats"].append(_squash(source["caveat"]))

    if source is not None:
        bands = source["bands"]
        note.update(
            kind=source["kind"],
            inches=bands[0]["inches"],
            figure=bands[0]["figure"],
            quote=bands[0]["quote"],
            document=_squash(source["document"]),
            url=source.get("url"),
            cite=source["cite"],
            read_on=str(source["read_on"]),
            drawn=bool(source.get("drawn")),
            below_ft=bands[0]["below_ft"],
            higher_ground=_higher(bands),
        )
        note["bands_words"] = _band_words(bands)
        note["source_name"] = source.get("name") or place
    elif note["level"] == "state" and state:
        note.update(
            kind="state code",
            inches=state["inches"],
            figure=state["figure"],
            quote=state["quote"],
            document=state["document"],
            url=state["url"],
            cite=state["cite"],
            read_on=str(doc.get("read_on")),
            below_ft=state["below_ft"],
            higher_ground=state["higher_ground"],
        )
        note["bands_words"] = state["bands_words"]
        note["source_name"] = "State of Oregon"

    if note["inches"] is not None and state:
        note["above_state"] = note["inches"] > state["inches"]
    note["words"] = _words(note)
    note["elevation_words"] = _elevation_words(note)
    return note


def _read(raw: dict[str, Any]) -> dict[str, Any]:
    return {"document": _squash(raw.get("document") or ""), "url": raw.get("url"), "cite": raw.get("cite")}


def _words(note: dict[str, Any]) -> str:
    state = note["state"]
    if note["inches"] is None:
        ref = f" For reference only, the state figure for this county is {state['inches']} in." if state else ""
        return f"Not resolved: {note['place']}'s frost depth has not been read.{ref}"
    depth = f"{note['inches']} in below grade"
    if note["level"] == "city":
        how = "drawn on its sample plan" if note["drawn"] else _KIND_WORDS[note["kind"]]
        words = f"{depth}: {note['place']}'s own figure ({how}; {note['document']})."
    elif note["level"] == "county":
        lead = (
            f"{note['place']}'s building department states no frost depth of its own, so the county figure applies"
            if note["outcome"] == "silent"
            else f"{note['place']} is served by the county building department"
        )
        words = f"{depth}: {lead} ({note['source_name']}, {_KIND_WORDS[note['kind']]}). Flagged county level."
    else:
        lead = (
            f"{note['place']}'s building department states no frost depth of its own, so the state figure applies"
            if note["outcome"] == "silent"
            else f"{note['place']} has no county building figure, so the state figure applies"
        )
        words = f"{depth}: {lead} ({state['edition'] if state else note['document']}). Flagged state level."
    if note["above_state"] and state:
        words += f" Deeper than the state's {state['inches']} in."
    return words


def _elevation_words(note: dict[str, Any]) -> str:
    """The elevation the figure holds for, and what changes above it. No lot
    elevation is held, so this is always said."""
    parts = ["Lot elevation is not held."]
    if note["inches"] is not None and note["below_ft"]:
        parts.append(f"The {note['inches']} in figure holds below {_ft(note['below_ft'])}.")
        top = note["below_ft"]
        for band in note["higher_ground"]:
            span = f"from {_ft(band['from_ft'])}" + (f" to {_ft(band['below_ft'])}" if band["below_ft"] else "")
            parts.append(f"{span}: {band['inches']} in.".capitalize())
            top = band["below_ft"]
        if top:
            parts.append(f"From {_ft(top)} the {note['source_name']} figure gives no depth.")
    state = note["state"]
    if state and note["level"] != "state":
        parts.append(f"State requirement: {state['bands_words']} ({state['edition']}).")
    if state and state.get("higher_ground_next_edition"):
        parts.append(state["higher_ground_next_edition"])
    return " ".join(parts)
