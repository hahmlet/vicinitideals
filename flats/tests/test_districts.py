"""Every district a city's own documents name, and what we decided about it.

:mod:`flats.encode.districts` reads the stored corpus and reports the
designations a jurisdiction prints that its encoded zone list does not carry.
That is a lead generator; this file is the answer sheet. One line per
designation, each opening with a verdict and then arguing from the page.

The property being defended is not that the answers are right -- it is that
**no designation goes unanswered**. The zone gap has been found four times in
this project, and every time the failure was silence rather than error: nobody
looked (Lake Oswego), a chapter stated a district with no observed lots
(Wilsonville V), two lists were never compared (the 35 zones ``rules.yaml`` had
never heard of), and a zone refused on a category the city's own glossary
disproves (Oregon City R-2). A ledger that prints a designation nobody has
ruled on is the same failure a fifth time, so this test fails when that
happens -- in either direction. A ruling for a designation the corpus no
longer prints is also a failure, because a decision that has outlived its
question is the staleness the dismissal re-read spent a day removing.

**What this file cannot see.** The ledger finds a designation only where the
corpus prints it as a parenthesised introduction, as a repeated bare line, or
inside a run of bare lines long enough to be a table's column heads. Three
kinds of district slip through all three: a one-character designation (Oregon
City's ``C``), one that appears exactly once and alone, and one that appears
in a document nobody has fetched. Those are recorded in :data:`BY_HAND`, found
while ruling the ledger's rows and kept here so the reading is not lost.
"""

from __future__ import annotations

import re

from flats.encode.districts import by_layer, unheld

#: How a ruling may open, and what each opening word commits us to next.
#:
#: ``encode``       a real base zone where our building belongs; queue it.
#: ``fetch``        a real base zone whose governing text is not in the store.
#: ``prohibited``   the code says our building may not go there.
#: ``conditional``  allowed only on a discretionary approval, which we refuse
#:                  the same way Oregon City R-2 was *accepted* -- by asking
#:                  whether the use is permitted outright, not whether it is
#:                  imaginable.
#: ``not-listed``   the use table carries no row our building could be.
#: ``column``       the document is held and the row is found, and the cell
#:                  still cannot be read because the table's cells and its
#:                  column heads do not line up in the extracted text. Lake
#:                  Oswego forced this one into existence. It is neither a
#:                  fetch (nothing to fetch) nor a reading (nothing readable),
#:                  and calling it either hides the only work that closes it.
#: ``overlay``      an overlay or plan district, not a base zone.
#: ``not-a-zone``   a formula variable, a table legend, a plan's name, a FEMA
#:                  map label, or extractor debris.
#: ``aliased``      a real base zone that IS encoded, under the spelling the
#:                  parcel layer uses rather than the one the ordinance
#:                  prints. Oregon City forced this one into existence: Title
#:                  17 says WFD from end to end and the county parcel layer
#:                  says WFDD on the four lots that carry it, and the rules
#:                  have to be keyed on the parcel spelling or they reach no
#:                  land at all. It is not an ``encode`` -- there is nothing
#:                  left to do -- and calling it one would leave a permanent
#:                  entry on a queue of work.
VERDICTS = frozenset(
    {
        "encode",
        "fetch",
        "prohibited",
        "conditional",
        "not-listed",
        "column",
        "overlay",
        "not-a-zone",
        "aliased",
    }
)

#: Verdicts that are claims about what a code says, and so must cite it. The
#: standing rule that a refusal has to argue from the page, applied to the one
#: half of this vocabulary where "the page" means something: ``overlay`` and
#: ``not-a-zone`` are claims about what a token *is*, and the sighting the
#: ledger prints is already the evidence.
MUST_CITE = frozenset(
    {"encode", "fetch", "prohibited", "conditional", "not-listed"}
)

RULINGS: dict[str, dict[str, str]] = {
    "or/clackamas/_unincorporated": {
        # Table 315-1's column heads are in the store at zdo.315.txt L44-L54:
        # R-5 - R-30 | VR-4/5 & VR-5/7 | R-2.5 | VTH | PMD | MR-1 | MR-2 |
        # HDR | VA | SHD | RCHDR. The Quadplexes row at L296-L306 reads
        # P[7,8], P[7,8], X, P, P, P, P, P, P, P, P -- so the one prohibition
        # is R-2.5 and every other urban residential district permits the pod
        # outright. The column order is confirmed a second way: three rows
        # (Child Care Facilities, Adult Daycare, Civic and Cultural) print an
        # "L" in positions 8, 10 and 11, and 315.03.1.2 names exactly HDR, SHD
        # and RCHDR as the districts with listed limited uses.
        # Five rulings stood here until 2026-09-08 -- R-2.5 prohibited, and
        # PMD, MR-1, MR-2 and VA to encode -- and all five are gone because
        # the work was done. That is the deletion this file's own staleness
        # test demands: a ruling is a decision about a question the ledger is
        # still asking, so when the zone is encoded the ledger stops reporting
        # it and the ruling is a record of a question, not an answer to a live
        # one. Four are left below, all of them fetches.
        #
        # ZDO Section 316 arrived in the store on 2026-09-08 and brought six
        # more designations with it: RA-1, RA-2, RR, RRFF-5, FF-10 and FU-10,
        # printed both as parenthesised introductions in 316.02 and as the
        # column heads of Table 316-1. Five carry lots and were encoded the
        # same day, all five refusals. RR carries none, so it stays a ruling.
        "RR": (
            "prohibited: Recreational Residential, the third column of ZDO "
            "Table 316-1. Its only dwelling rows are detached single-family "
            "(P), manufactured, prefabricated and single room occupancy; "
            "duplexes read X in this column and there is no triplex, quadplex "
            "or townhouse row anywhere in the table. Note 8 states it "
            "affirmatively -- 'each lot of record may be developed with only "
            "one of the following' -- and 316.03(A)(1) makes the silence a "
            "prohibition: 'Uses not listed are prohibited.' No lots carry it "
            "in the parcel layer, which is why it is ruled and not encoded."
        ),
        "VTH": (
            "fetch: Village Townhouse -- quadplexes P in Table 315-1, but its "
            "standards are in Table 315-3, which prints two cells in several "
            "of its three-column rows; lot size, coverage and rear setback "
            "are a column question before they are a reading."
        ),
        "HDR": (
            "fetch: High Density Residential -- quadplexes P in Table 315-1, "
            "but Table 315-4 answers rear setback, side setback and building "
            "separation with 'See Subsection 1005.02(L)', and no ZDO 1005 is "
            "in the store."
        ),
        "SHD": (
            "fetch: Special High Density -- quadplexes P in Table 315-1, "
            "setbacks deferred to Subsection 1005.02(L), which is not in the "
            "store."
        ),
        "RCHDR": (
            "fetch: Regional Center High Density Residential -- quadplexes P "
            "in Table 315-1, setbacks deferred to Subsection 1005.02(L), "
            "which is not in the store."
        ),
        # The density formula's variables. ZDO 1012.04 spells the whole thing:
        # {GSA - [NR + HRA + (MRA x 0.5)]} / DLA = BD.
        "DLA": (
            "not-a-zone: district land area, the per-dwelling divisor ZDO "
            "1012.04 assigns to a district, not a district."
        ),
        "NR": (
            "not-a-zone: new road area, the first subtraction in the ZDO "
            "1012.04 density formula and capped there at 15 percent of GSA."
        ),
        "HRA": (
            "not-a-zone: highly restricted areas -- the steep slope, mass "
            "movement, floodway, greenway, habitat and water quality land ZDO "
            "1012.04 subtracts in full before dividing."
        ),
        "MRA": (
            "not-a-zone: moderately restricted areas, the 20-to-50 percent "
            "slopes ZDO 1012.04 halves before dividing."
        ),
        "BD": (
            "not-a-zone: base density, the result of the ZDO 1012.04 formula "
            "rather than a place it applies to."
        ),
        "HCAD": "overlay: Habitat Conservation Area District, ZDO Section 706.",
        "HCA": (
            "overlay: Habitat Conservation Area, the land ZDO Section 706 "
            "regulates; the same overlay as HCAD, spelled without the D."
        ),
        "WQRAD": (
            "overlay: Water Quality Resource Area District, ZDO Section 709."
        ),
        "HL": (
            "overlay: Historic Landmark, one of the three cultural resource "
            "designations ZDO 202 sends to Section 707."
        ),
        "HD": "overlay: Historic District, ZDO 202 and Section 707.",
        "HC": "overlay: Historic Corridor, ZDO 202 and Section 707.",
    },
    "or/clackamas/gladstone": {
        "FM": "overlay: Flood Management Area District, GMC 17.29.",
        "WQ": "overlay: Water Quality Resource Area District, GMC 17.27.",
        "HCAD": "overlay: Habitat Conservation Area District, GMC 17.25.",
        "HCA": "overlay: Habitat Conservation Area, the land GMC 17.25 covers.",
        "AE": (
            "not-a-zone: a FEMA flood insurance rate map zone letter, quoted "
            "by GMC 17.29 where it lists Zones A, AE and so on."
        ),
    },
    "or/clackamas/happy-valley": {
        "FU-10": (
            "prohibited: Table 16.22.010-1 permits 'One single-family "
            "dwelling, modular dwelling unit, mobile or manufactured home per "
            "lot' and carries no duplex, triplex or quadplex row; FU-10 is a "
            "holding area for land not yet urbanised."
        ),
        "NROZ": "overlay: Natural Resources Overlay Zone, HVMC 16.32.",
    },
    "or/clackamas/lake-oswego": {
        # LOC 50.03.002's use table is the loosest residential permission in
        # the corpus and the least readable: its only household-living row is
        # "Residential use at R-5 density or greater", and the extractor
        # prints eleven cells against fifteen column heads. Which zones carry
        # the P cannot be read off the page, so every commercial, industrial
        # and public column is ruled the same way -- one fix (reading the
        # table by column) answers all ten at once.
        "NC": (
            "column: Neighborhood Commercial, a head of the LOC 50.03.002 use "
            "table whose 'Residential use at R-5 density or greater' row "
            "prints 11 cells against 15 heads."
        ),
        "GC": "column: General Commercial, same LOC 50.03.002 table.",
        "HC": "column: Highway Commercial, same LOC 50.03.002 table.",
        "OC": "column: Office Campus, same LOC 50.03.002 table.",
        "EC": "column: East End Commercial, same LOC 50.03.002 table.",
        "FMU": "column: Foothills Mixed Use, same LOC 50.03.002 table.",
        "IP": "column: Industrial Park, same LOC 50.03.002 table.",
        "CI": "column: Campus Institutional, same LOC 50.03.002 table.",
        "PF": "column: Public Functions, same LOC 50.03.002 table.",
        "PNA": "column: Park Natural Area, same LOC 50.03.002 table.",
        "R-2.5": (
            "encode: WLG Townhome Residential -- LOC 50.04 Table "
            "50.04.001-15 gives its yard setbacks and 50.04 caps it at 35 ft; "
            "a townhouse zone we hold none of, use permission not yet read."
        ),
        "RMU": (
            "encode: WLG Residential Mixed Use -- LOC 50.04 Table "
            "50.04.001-17 gives its yard setbacks; a residential zone we do "
            "not hold, use permission not yet read."
        ),
    },
    "or/clackamas/milwaukie": {
        "GMU": (
            "conditional: Table 19.303.2 gives 'Duplex, Triplex, Quadplex' as "
            "CU in all three commercial mixed-use zones."
        ),
        "NMU": "conditional: the same CU cell in Table 19.303.2 as GMU.",
        "SMU": "conditional: the same CU cell in Table 19.303.2 as GMU.",
        "DMU": (
            "not-listed: Table 19.304.2's residential rows are Boarding "
            "house, Townhouse, Multifamily, Live/work units, Second-story "
            "housing and Senior and retirement housing -- there is no duplex, "
            "triplex or quadplex row in the downtown table at all."
        ),
        "OS": (
            "prohibited: Open Space, the other downtown zone, reads N against "
            "every residential row of Table 19.304.2."
        ),
        "MUTSA": (
            "not-listed: Table 19.312.2 carries Multifamily, Mixed use "
            "residential and Live/work units and no quadplex row; MMC keeps "
            "quadplex a use category separate from multifamily wherever it "
            "lists both, as Table 19.303.2 does."
        ),
        "NME": (
            "not-listed: the North Milwaukie Employment Zone, MMC 19.312.1.B "
            "-- production, manufacturing and employment, N against every "
            "residential row of Table 19.312.2."
        ),
        "NMIA": (
            "not-a-zone: the North Milwaukie Innovation Area Plan, named at "
            "MMC 19.312.1.A as what MUTSA and NME implement."
        ),
    },
    "or/clackamas/oregon-city": {
        # Four rulings stood here until 2026-09-08 -- MUC-1, MUC-2, MUD and
        # WFD, all four to encode -- and three are gone because the zones are
        # encoded and the ledger no longer asks. WFD is the fourth and it is
        # the odd one: the zone is encoded, under the parcel layer's spelling
        # WFDD, so the ledger goes on printing the ordinance's WFD forever and
        # a ruling has to stay to answer it. That is what `aliased` is for.
        #
        # Two of the three that went taught something worth keeping even
        # though the ruling itself is gone. The MUC-1 ruling written from the
        # use table said the district carries "a 5 ft maximum front setback"
        # and "the same 17.4 du/acre minimum density" -- and reading the
        # section found that OCMC 17.29.050.I exempts a standalone residential
        # development of fewer than five units from BOTH. So the two standards
        # that ruling named are the two this pod does not carry, and the
        # difference is one paragraph that MUC-2, C and the general commercial
        # district do not have. A ruling made off a use table is a queue
        # entry, never a reading.
        "WFD": (
            "aliased: OCMC 17.35, the Willamette Falls Downtown District, is "
            "encoded -- as WFDD, which is how the county parcel layer spells "
            "it on the four lots that carry it. Title 17 says WFD throughout "
            "and never WFDD; the rules must be keyed on the parcel spelling "
            "or they reach no land, and Oregon City has exactly one "
            "Willamette Falls Downtown district, so the two names cannot be "
            "two places."
        ),
        "MUC": (
            "not-a-zone: the chapter name OCMC 17.29.010 gives the mixed-use "
            "corridor; the zone list at 17.06.010 carries MUC-1 and MUC-2, "
            "not a bare MUC."
        ),
        "NROD": (
            "overlay: Natural Resource Overlay District, OCMC 17.49, one of "
            "the five overlays 17.06.010 lists after the base districts."
        ),
    },
    "or/clackamas/rivergrove": {
        "HID": (
            "overlay: the RLDO's Flood Hazard District, which it abbreviates "
            "HID; an overlay carrying special requirements in addition to the "
            "base zone."
        ),
    },
    "or/clackamas/tualatin": {
        "RMH": (
            "fetch: Medium High Density Residential, TDC Chapter 42 -- the "
            "stored 40-41.residential.txt ends on its last line at that "
            "chapter's heading, so the whole chapter body is missing."
        ),
        "WPD": "overlay: Wetlands Protection District, TDC Chapter 71.",
        "WPA": (
            "overlay: Wetlands Protected Area, the inner of the two areas TDC "
            "71 divides the Wetlands Protection District into."
        ),
        "WFA": (
            "overlay: Wetlands Flood Area, the balance of the Wetlands "
            "Protection District under TDC 71."
        ),
        "NRPO": (
            "overlay: Natural Resource Protection Overlay District, TDC "
            "Chapter 72."
        ),
    },
    "or/clackamas/wilsonville": {
        "PDR-7": (
            "encode: WC 4.113(.01)C divides Planned Development Residential "
            "into PDR-1 through PDR-7 and we hold PDR-1 through PDR-6; the "
            "seventh was never encoded."
        ),
        "PDR-S": (
            "not-a-zone: a base zone wearing the solar overlay. WC "
            "4.137(.01)A creates an 'S' overlay that 'may be used in "
            "conjunction with any underlying residential base zone (e.g., "
            "PDR-S, R-S, etc.)'."
        ),
        "R-S": "not-a-zone: the R zone under the same WC 4.137 solar overlay.",
        "RSIA": (
            "not-listed: Planned Development Industrial - Regionally "
            "Significant Industrial Area, WC 4.135.5; industrial land."
        ),
        "SROZ": (
            "overlay: Significant Resource Overlay Zone, WC Section 4.139.00."
        ),
        "CCDOD": (
            "overlay: Coffee Creek Industrial Design Overlay District, WC "
            "Section 4.134, an overlay within the RSIA zone."
        ),
        "J 1J 1J": (
            "not-a-zone: extractor debris from a tax-lot schedule in WC 4, "
            "where it sits between 'S2 TL 500' and a street address."
        ),
    },
    "or/multnomah/fairview": {
        "MH": (
            "not-listed: FMC 19.30.100 permits manufactured and prefabricated "
            "homes inside a manufactured home park, one per 2,500 sq ft space "
            "at least 30 by 40 ft; a four-unit attached building is not among "
            "its permitted uses."
        ),
        "R2": (
            "not-a-zone: a standard's identifier in the FMC 19.65 town centre "
            "design table, printed at the end of a row beside cells reading "
            "'X' and 'X - 60%'."
        ),
        "B6": (
            "not-a-zone: the same kind of FMC 19.65 row identifier as R2, "
            "beside cells reading 'None / 20% / 10%'."
        ),
        "V1-30": (
            "not-a-zone: a FEMA flood insurance zone label, quoted in FMC "
            "19.105's definition of area of special flood hazard."
        ),
        "VE": "not-a-zone: the other FEMA flood zone label in that same FMC "
        "19.105 definition.",
    },
    "or/multnomah/gresham": {
        "TC-PV": (
            "encode: the Pleasant Valley Town Center sub-district, GRC 4.1420 "
            "-- it 'permits a wide range of housing types, including "
            "live-work uses, mixed-use buildings, and adjacent townhouses and "
            "apartments'. We hold its five Pleasant Valley neighbours and not "
            "it; use table not yet read."
        ),
        "VC-SW": (
            "encode: the Springwater Village Center sub-district, which GRC "
            "3.0100 names beside the Townhouse Residential (THR-SW) land we "
            "do hold; a base sub-district we do not hold, use table not yet "
            "read."
        ),
        "ME-PV": (
            "not-listed: the Mixed Employment sub-district of Pleasant "
            "Valley, GRC 4.1400, 'primarily intended to provide a range of "
            "employment'."
        ),
        "CNPD": (
            "overlay: the Civic Neighborhood Plan District, GRC 4.1200, named "
            "in 3.0100 as the extent of the Civic Neighborhood Design "
            "District laid over its base zones."
        ),
        "DPD": (
            "overlay: the Downtown Plan District, GRC 4.1100, the extent of "
            "the Downtown Design District."
        ),
        "SUR": (
            "not-a-zone: a use-table legend cell in GRC 4.1500, printed in "
            "the allowed-use column beside 'P'."
        ),
        "L/SUR": "not-a-zone: the same legend cell in GRC 4.1400's use table.",
    },
    "or/multnomah/portland": {
        "IC": (
            "not-a-zone: the Institutional Campus comprehensive plan "
            "designation named at PZC 33.150.010; the campus institutional "
            "zones that implement it are already in the corpus."
        ),
    },
}

#: Designations found by hand while ruling the rows above, which the ledger
#: cannot surface on its own. Kept because a reading that is not written down
#: is a reading that will be done again.
BY_HAND: dict[str, dict[str, str]] = {
    "or/clackamas/oregon-city": {
        # C is gone from here on 2026-09-08, encoded. It was the entry that
        # justified this whole dict existing: one capital letter, which no
        # harvest can ever see because a lone capital is noise everywhere else
        # in the corpus, so the only way it was ever going to be found was by
        # somebody reading the chapter list. It was, and now it is 74 lots
        # with rules on them.
        #
        # NC and HC stay, and they are not stale. Both are `prohibited`, which
        # owes nobody any work, and both are now ALSO encoded -- as
        # `quadplex_allowed: false`, quoting the same sentences these two
        # rulings quote. The ruling and the rule agree, which is the state
        # this file wants; if they ever stop agreeing, that is worth knowing
        # and deleting the ruling would hide it.
        "NC": (
            "prohibited: OCMC 17.24.020.A lets neighbourhood commercial take "
            "'any use permitted in the mixed-use corridor', which would carry "
            "quadplexes in -- but the prohibited list strikes 'Residential "
            "use that exceeds fifty percent of the total square footage of "
            "the development', and a residential pod is all of it."
        ),
        "HC": (
            "prohibited: OCMC 17.26.035 prohibits 'B. Triplexes and "
            "quadplexes' and 'C. Multi-family residential' outright in the "
            "historic commercial district."
        ),
    },
}

_VERDICT = re.compile(r"^([a-z-]+): (.+)$", re.S)


def _declared() -> dict[str, set[str]]:
    return {
        layer: {row.token for row in rows}
        for layer, rows in by_layer(unheld()).items()
    }


def test_every_declared_designation_is_ruled() -> None:
    """The property the whole exercise exists for: nothing goes unanswered."""
    unruled: list[str] = []
    for layer, tokens in _declared().items():
        for token in sorted(tokens):
            if token not in RULINGS.get(layer, {}):
                unruled.append(f"{layer}/{token}")
    assert not unruled, (
        "designations the corpus prints that nobody has ruled on: "
        + ", ".join(unruled)
    )


def test_no_ruling_outlives_its_designation() -> None:
    """A decision whose question is gone is the staleness, not the record."""
    declared = _declared()
    orphaned: list[str] = []
    for layer, rulings in RULINGS.items():
        found = declared.get(layer, set())
        for token in sorted(rulings):
            if token not in found:
                orphaned.append(f"{layer}/{token}")
    assert not orphaned, (
        "rulings for designations the ledger no longer reports -- either the "
        "zone was encoded (delete the ruling) or the reader went blind (fix "
        "it): " + ", ".join(orphaned)
    )


def test_every_ruling_opens_with_a_known_verdict() -> None:
    for layer, rulings in list(RULINGS.items()) + list(BY_HAND.items()):
        for token, ruling in rulings.items():
            match = _VERDICT.match(ruling)
            assert match, f"{layer}/{token}: no '<verdict>: ' opening"
            assert match.group(1) in VERDICTS, (
                f"{layer}/{token}: unknown verdict {match.group(1)!r}"
            )


def test_every_ruling_argues_from_the_page() -> None:
    """A refusal that cites nothing is the shape that goes stale unnoticed."""
    thin: list[str] = []
    for layer, rulings in list(RULINGS.items()) + list(BY_HAND.items()):
        for token, ruling in rulings.items():
            match = _VERDICT.match(ruling)
            assert match, f"{layer}/{token}: no '<verdict>: ' opening"
            verdict, reason = match.groups()
            if verdict not in MUST_CITE:
                continue
            if len(reason) < 40 or not re.search(r"\d", reason):
                thin.append(f"{layer}/{token}")
    assert not thin, (
        "rulings that claim what a code says without pointing at where it "
        "says it: " + ", ".join(thin)
    )


def test_the_districts_still_owed_are_the_ones_we_think() -> None:
    """The queue this audit produced, pinned so it cannot quietly change.

    Ten districts to encode, five to fetch and one unreadable table (ten of
    its columns), as of 2026-09-08. Encoding one is what makes this number
    fall; discovering one is what makes it rise, and either is worth a look at
    why.

    Fourteen earlier the same day. The four that went are PMD, MR-1, MR-2 and
    VA in unincorporated Clackamas, encoded off the top of the rebuilt
    two-county coverage ledger along with R-2.5, which was a prohibition
    rather than an encode and so was never in this count. That is the first
    time this number has fallen because the queue was worked rather than
    because the reader changed.

    Five now, later the same evening, and the second fall is Oregon City's
    whole commercial side: MUC-1, MUC-2, MUD and C encoded, and WFD re-ruled
    `aliased` because the zone IS encoded and the ledger will go on printing
    the ordinance's spelling of it forever. Two more districts were encoded in
    the same pass and never appeared in this count at all -- MUE and I are
    refusals reasoned from OCMC 17.06.010.A, which the ledger cannot ask about
    because it only knows what a jurisdiction PRINTS as a designation, not
    what it declines to permit.
    """
    owed: dict[str, list[str]] = {"encode": [], "fetch": [], "column": []}
    for layer, rulings in list(RULINGS.items()) + list(BY_HAND.items()):
        for token, ruling in rulings.items():
            match = _VERDICT.match(ruling)
            assert match, f"{layer}/{token}: no '<verdict>: ' opening"
            verdict = match.group(1)
            if verdict in owed:
                owed[verdict].append(f"{layer}/{token}")
    assert len(owed["encode"]) == 5, sorted(owed["encode"])
    assert len(owed["fetch"]) == 5, sorted(owed["fetch"])
    assert len(owed["column"]) == 10, sorted(owed["column"])
