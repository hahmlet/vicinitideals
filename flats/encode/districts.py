"""Every district designation a city's own documents print, against the ones we hold.

Three times this project has found a gap in the **list** of zones rather than in
any zone, and each time a different ledger was standing right next to it saying
nothing. The coverage ledger counts zones missing a required *field*, and a zone
nobody encoded has no fields to be missing. The mirror audit compared `rules.yaml`
against the corpus number by number for five weeks before anyone compared them as
lists. The reading queues rank lines inside chapters we already opened.

The shape they all share is that they count what they were pointed at, and nobody
had pointed one at *the names the code itself uses for its districts*.

So this module reads the stored documents for the one thing every Oregon code
does the same way: it names a district and puts its abbreviation in parentheses
beside it. "Medium High Density Residential Zone (RMH)". "Downtown Mixed Use
(DMU)". "Urban Low Density Residential (R-2.5, R-5, R-7, R-8.5, R-10, R-15, R-20,
and R-30)". Take those, subtract the zones the layer holds, and what is left is a
list of districts the city has and we have not looked at.

**Three harvests, because each earlier one misses the thing that matters most.**
A parenthesis is how a code *introduces* a district, but a use table names its
columns bare -- Milwaukie's Table 19.303.2 heads three columns `GMU`, `NMU`,
`SMU` and never spells SMU inside a parenthesis anywhere in Title 19. A column
head is exactly where a district that permits our building is most likely to be
found, so the second harvest takes any line that is *nothing but* a designation,
printed that way at least twice, within 25 lines of a sentence about zones or
districts. That caught SMU and every one of the eight Clackamas County districts
the first harvest saw only as one long parenthesis.

The third exists because **Lake Oswego's use table is printed exactly once**, so
nine of its fifteen column heads were still invisible to a rule that wants to
see a designation twice. A run of three or more consecutive designation-shaped
lines is a column-head block, and running prose never is; a run that long counts
every member once, no repetition required. One smaller fix was worth as much: a
column head **carries its footnotes with it** (`NC [8], [9]`, `HC [9]`,
`OC [8]`), and stripping that trailing marker run was the difference between
finding one of Lake Oswego's commercial zones and finding all of them.

**This is a lead generator, not a ledger of debt** -- the same standing as
:mod:`flats.encode.find`. A designation here is a *name in a parenthesis*, and
plenty of them are overlays, flood maps, plan districts, acronyms for agencies,
or the same zone we already hold spelled with a different dash. What the module
cannot do is tell those apart from a real missing district; what it can do is
make sure the question is asked out loud about every one of them. The answers
live in :mod:`flats.tests.test_districts`, one line each, and the test fails when
a designation appears that nobody has ruled on -- which is the only property that
matters, because the failure mode being defended against is silence.

**Ranking, not filtering.** Each row carries how many of its lines also mention
housing, and rows sort by that. It is a sort and not a filter for the reason the
review verticals settled on months ago: a mixed-use district's establishing
sentence often says nothing about dwellings, and dropping it would hide exactly
the kind of district Portland's CM2 and CX turned out to be.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

#: The parenthesis. Bounded so a page number or a whole sentence in brackets is
#: not mistaken for a designation list.
_PAREN = re.compile(r"\(([^()]{1,160})\)")

#: One designation as Oregon codes spell them: R-8.5, LR 7.5, C/I, MUC-2, VR-5/7,
#: RCHDR. Capitals and digits only -- a lowercase letter means it is a word.
_ONE = re.compile(r"^[A-Z][A-Z0-9]?[A-Z0-9\-./ ]{0,7}$")

#: "R-2.5, R-5, R-7, and R-30" is one parenthesis holding eight districts. Split
#: only when the parenthesis is too long to be a single designation, so "C/I"
#: and "VR-4/5" survive intact.
_SPLIT = re.compile(r"\s*(?:,|;|\band\b|\bor\b)\s*", re.I)

#: The sentence has to be about districts at all. Without this every acronym in
#: the code arrives -- and with it, a surprising number still do.
_ZONEY = re.compile(r"\b(zone|zones|district|districts)\b", re.I)

#: What makes a row worth reading first. Deliberately broad: "dwelling" catches
#: a use table, "residential" catches an establishing sentence.
_HOUSING = re.compile(
    r"\b(quadplex|quadplexes|fourplex|triplex|triplexes|middle housing|"
    r"multifamily|multi-family|multiple-family|townhouse|townhome|dwelling|"
    r"dwellings|residential)\b",
    re.I,
)

#: Not districts, and every one of them was found in a parenthesis next to the
#: word "district" or "zone" in a real Oregon code. Statutes and agencies
#: (ORS, ODFW), federal flood-map machinery (FIRM, BFE, LOMA), review types
#: (PUD, DRB), and the single letters a code uses for its own table legends.
#:
#: A name belongs here only when it is not a land designation anywhere in
#: Oregon. When in doubt, leave it out and rule it in the test -- a wrong
#: entry here is invisible, a wrong entry there is a sentence somebody reads.
_NOT_A_DISTRICT = frozenset({
    "ORS", "OAR", "USC", "CFR", "PDF", "GIS", "ADA", "FEMA", "DEQ", "ODOT",
    "DSL", "EPA", "ODFW", "OWEB", "USFWS", "NOAA", "NFIP",
    "TABLE", "FIGURE", "SEE", "AND", "OR", "THE", "NOTE", "NOTES", "MAX",
    "MIN", "FT", "SF", "DU", "AC", "NA", "N/A", "SQ", "SQFT",
    "TDC", "MMC", "OCMC", "FMC", "WDC", "LOC", "RLDO", "ZDO", "GMC", "MC",
    "UGB", "CIP", "TSP", "ADU", "ADUS", "HB", "SB", "TYPE", "LLC",
    "PUD", "PUDS", "CPUD", "DRB", "LID", "CUP", "CU", "CSU",
    "FIRM", "DFIRM", "BFE", "LOMA", "LOMR", "DBH", "MDA", "CFA", "UFC",
    "COW", "IAMP", "AO", "AH", "AR/AO", "AR/AH", "VO",
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N", "O",
    "P", "Q", "R", "S", "T", "U", "W", "Y", "Z",
    # Table furniture. The second harvest reads whole lines, and a linearised
    # table prints its row labels and its legend on lines of their own in the
    # same shape a column head has. These are the ones Oregon codifiers
    # actually produce, collected from the run rather than imagined.
    "USE", "USES", "PERMITTED", "PROHIBITED", "STANDARD", "STANDARDS",
    "DENSITY", "GENERAL", "PROCESS", "OTHER", "ZONES", "DISTRICT",
    "DISTRICTS", "PRACTICES", "LOADING", "HEIGHT", "SETBACK", "SETBACKS",
    "COVERAGE", "PARKING", "LOT", "LOTS", "AREA", "WIDTH", "DEPTH", "YARD",
    "YARDS", "FRONT", "REAR", "SIDE", "PURPOSE", "DEFINITIONS",
    "APPLICABILITY", "NONE", "SAME", "TOTAL", "ALL", "EACH", "PER",
    # Use-table legends, which are designation-shaped by accident: "P/C" is
    # "permitted or conditional", not a zone. Spelled out rather than matched
    # by a rule, because Wood Village really does have a zone called C/I.
    "P/C", "P/CU", "P/CU/N", "L/C", "C/L", "P/L",
})


def normalise(token: str) -> str:
    """A designation stripped to what makes it the same district.

    `R-MD` and `R MD` and `RMD` are one zone written three ways, and the corpus
    and the documents rarely agree on which. Dots survive because `R-8.5` and
    `R-85` are different districts.
    """
    return re.sub(r"[^A-Z0-9.]", "", token.upper())


@dataclass(frozen=True)
class Sighting:
    """One line that prints a designation."""

    document: str
    line: int
    text: str

    @property
    def housing(self) -> bool:
        return bool(_HOUSING.search(self.text))


@dataclass
class Designation:
    """A district name a layer's documents print and the layer does not hold."""

    layer: str
    token: str
    sightings: list[Sighting] = field(default_factory=list)

    @property
    def key(self) -> str:
        return normalise(self.token)

    @property
    def housing_sightings(self) -> int:
        return sum(1 for s in self.sightings if s.housing)

    @property
    def first(self) -> Sighting:
        return self.sightings[0]

    def cite(self) -> str:
        """`document:line`, the way a person would write it down."""
        return f"{self.first.document}:{self.first.line}"


def _documents(layer: str) -> Iterator[Path]:
    directory = DOCS / layer
    if not directory.is_dir():
        return
    yield from sorted(directory.glob("*.txt"))


#: How far a bare column head may sit from a sentence about districts and still
#: be read as one. A linearised table puts its caption within a few lines of its
#: heads; 25 is loose enough for a caption repeated three times by the extractor
#: and tight enough that a stray capitalised line in running prose does not
#: borrow the word "zone" from half a page away.
_NEAR_LINES = 25

#: A bare designation has to be printed as one at least twice before it counts.
#: Once is a typo or a stray capital; a column head is printed once per table
#: and every table in these documents is printed at least twice.
_MIN_BARE = 2

#: ...except when it is not. Lake Oswego's use table is printed exactly once,
#: so nine of its fifteen columns were invisible to a rule that wants to see a
#: designation twice. But a linearised table gives its column heads away by
#: their company: they arrive as a run of consecutive lines that are each
#: nothing but a designation, which running prose never does. A run this long
#: counts every member once, no repetition required.
_MIN_RUN = 3


#: A column head carries its footnotes with it. Lake Oswego's use table heads
#: its columns ``NC [8], [9]``, ``HC [9]``, ``OC [8]`` and ``EC [8]``, and the
#: one column that happens to carry no footnote -- ``OC`` again, further down --
#: was the only one of the five this ledger saw until the markers were stripped.
#: A designation is never followed by a bracketed number, so removing the run is
#: safe and it is exactly the difference between finding one of a city's
#: commercial zones and finding all of them.
_MARKERS = re.compile(r"(?:\s*\[\d+\]\s*,?)+$")


def _demark(line: str) -> str:
    """A bare line with any trailing footnote markers taken off."""
    return _MARKERS.sub("", line).strip()


def _shaped(token: str) -> bool:
    """Is this token designation-shaped at all?"""
    if not token or token in _NOT_A_DISTRICT:
        return False
    if not _ONE.match(token) or not re.search(r"[A-Z]", token):
        return False
    # "LR 7.5" is a designation; "CSU P" and "J 1J 1J" are extractor debris.
    # A space is allowed only in front of a number.
    head, _, tail = token.partition(" ")
    if tail and not tail[:1].isdigit():
        return False
    return True


def declared(layer: str) -> dict[str, Designation]:
    """Every designation this layer's stored documents print, by token.

    Both harvests, merged: a designation introduced in a parenthesis and one
    standing alone as a table column head are the same district, and the
    sightings of both end up on one row.
    """
    found: dict[str, Designation] = {}
    bare: dict[str, list[Sighting]] = defaultdict(list)
    runs: set[str] = set()

    def add(token: str, sighting: Sighting) -> None:
        found.setdefault(
            token, Designation(layer=layer, token=token)
        ).sightings.append(sighting)

    for document in _documents(layer):
        lines = document.read_text(encoding="utf-8", errors="replace").splitlines()
        zoney = [n for n, text in enumerate(lines, 1) if _ZONEY.search(text)]
        run: list[str] = []
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            if _ZONEY.search(line):
                for match in _PAREN.finditer(line):
                    inner = match.group(1).strip()
                    parts = _SPLIT.split(inner) if len(inner) > 9 else [inner]
                    for part in parts:
                        token = part.strip().rstrip(".")
                        if _shaped(token):
                            add(token, Sighting(document.name, number, stripped))
            token = _demark(stripped).rstrip(".")
            if _shaped(token) and any(
                abs(z - number) <= _NEAR_LINES for z in zoney
            ):
                bare[token].append(Sighting(document.name, number, stripped))
                run.append(token)
            elif run:
                if len(run) >= _MIN_RUN:
                    runs.update(run)
                run = []
        if len(run) >= _MIN_RUN:
            runs.update(run)

    for token, sightings in bare.items():
        if len(sightings) < _MIN_BARE and token not in runs:
            continue
        for sighting in sightings:
            add(token, sighting)
    return found


def held(rules: RuleSet | None = None) -> dict[str, set[str]]:
    """The normalised zone list of every layer, so spelling cannot fake a gap."""
    rules = rules or RuleSet(load_rules())
    return {
        layer_id: {normalise(z) for z in layer.zones}
        for layer_id, layer in rules.layers.items()
    }


def unheld(
    layers: Iterable[str] | None = None, rules: RuleSet | None = None
) -> list[Designation]:
    """Designations a layer's documents print that its zone list does not carry.

    Sorted by how much housing language surrounds them, then by how often they
    are printed -- a sort, not a filter. Every row is returned.
    """
    zones = held(rules)
    wanted = list(layers) if layers is not None else sorted(zones)
    rows: list[Designation] = []
    for layer in wanted:
        if layer not in zones:
            continue
        mine = zones[layer]
        for designation in declared(layer).values():
            if designation.key in mine:
                continue
            rows.append(designation)
    rows.sort(key=lambda d: (-d.housing_sightings, -len(d.sightings), d.layer, d.token))
    return rows


def by_layer(rows: Iterable[Designation]) -> dict[str, list[Designation]]:
    grouped: dict[str, list[Designation]] = defaultdict(list)
    for row in rows:
        grouped[row.layer].append(row)
    return dict(grouped)


def render(rows: Iterable[Designation] | None = None) -> str:
    """The CLI view: one block per layer, housing-bearing rows first."""
    rows = list(rows) if rows is not None else unheld()
    out: list[str] = []
    grouped = by_layer(rows)
    zones = held()
    for layer in sorted(grouped):
        block = grouped[layer]
        out.append(
            f"\n{layer}  held={len(zones.get(layer, ()))}  "
            f"undeclared={len(block)}"
        )
        for designation in block:
            out.append(
                f"  {designation.token:10s} "
                f"housing={designation.housing_sightings:3d} "
                f"seen={len(designation.sightings):3d}  "
                f"{designation.cite()}  {designation.first.text[:100]}"
            )
    return "\n".join(out)


def main() -> None:  # pragma: no cover - CLI
    print(render())


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
