"""The refusal ledger, and why a count is the assertion worth making.

A refusal is a reading -- somebody opened the code, understood a standard and
decided it does not reach this building. Nothing can check that automatically
and nothing here tries. What can be checked is that the set is *known*: that
adding a refusal is a deliberate act with a number attached, rather than a
sentence of prose in a notes field that no ledger will ever revisit.

The motivating case is pinned at the bottom. A test docstring declared Table
4.0430's setback rows unreadable and therefore unencodable; four of the seven
columns were encoded from those exact lines afterwards, by somebody who had
never seen the refusal, and it sat there reading like a live constraint. That
is what an uncounted decision looks like weeks later.
"""

from __future__ import annotations

import pytest

from flats.encode.refusals import FLOOR, Refusal, _spans, refusals
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

#: Per source, as of 2026-08-21. These numbers are meant to move -- what they
#: are not meant to do is move quietly. A refusal added without a line here is
#: a reading nobody signed off on; a refusal removed without one is a reading
#: somebody overturned without saying so.
#: Comments went 45 -> 68 on 2026-08-27, twenty-three in one reading, and it
#: is the largest single move this ledger has recorded. The driveway family
#: was encoded across eight layers and every one of them came with sentences
#: that could not be: alley-first access rules in Gresham, driveway spacing
#: off a street classification nothing measures in Oregon City, a ten-foot
#: stall setback in Clackamas that turns out to govern cottage clusters, and
#: -- the one worth reading -- Happy Valley LDC 16.43.030.E.4, which sets
#: parking back from a street by "the same distance as the required building
#: setbacks" and prints only the loose ten-foot floor. Encoding ten would have
#: put half the real standard in the file in the permissive direction, so the
#: number went in the prose instead and this ledger counts it.
#:
#: A jump this size is the thing to be suspicious of. What makes it honest is
#: that the values landed in the same commit: 23 refusals against 21 encoded
#: values across the same eight files, which is a reading, not a retreat.
#:
#: 68 -> 67 on 2026-08-27, and it is the first time this count has gone DOWN
#: for the right reason. Happy Valley 16.43.030.E.4 was refused because it
#: states its standard by pointing at another one -- "the same distance as the
#: required building setbacks" -- and no carrier could say that. `same_as` now
#: can, so the comment came out and eleven values went in. A refusal ledger
#: whose number only ever rises is measuring reading; one that can fall is
#: measuring what the model cannot yet hold, which is what this is for.
EXPECTED = {"notes": 92, "comments": 70, "tests": 16}
#: Two of the sixteen are this file, which quotes the marker while
#: explaining it, and one is a back-reference in test_gresham_rockwood --
#: prose saying a zone *was* not encoded until it was. Left in rather than
#: special-cased, both of them: a ledger that skips one file because the file
#: is inconvenient is a ledger with an exception nobody remembers, and a
#: ledger that tries to tell a refusal from a reference to one is parsing
#: prose, which this module states plainly that it does not do.
#:
#: The two added on 2026-08-22 are test_lake_oswego_commercial_notes, and they
#: are the shape this ledger exists for: the NC zone is readable, it carries
#: 88 of the 93 lots that jurisdiction reports as zone_missing, and it is
#: deliberately not encoded until LOC 50.03.003.2 is fetched. A decision that
#: size should cost a line here.
#:
#: A refusal was added on 2026-08-24 for Portland's parking aisle and withdrawn
#: on 2026-08-25, which is the ledger working. The refusal said 33.266.120
#: states no aisle. It does not -- but 120.B.1 sends parking in a parking tract
#: to 33.266.130, whose Table 266-4 states one, and the product reaches it. A
#: refusal is a reading, and a reading that turns out to have stopped a section
#: early comes back out.
#:
#: Notes fell 90 -> 89 on 2026-08-25 for the same reason and the worse case.
#: Fairview R-6 refused a maximum FAR because the registry had no floor-area
#: field; ``max_far`` was added afterwards and encoded on that zone and four of
#: its siblings, and the refusal sat on top of the encoded value for weeks
#: reading like a live constraint. This ledger counted it the whole time --
#: counting is not checking, and nothing here can tell a refusal that is still
#: true from one that has been overtaken. What a count buys is that the
#: withdrawal has to be deliberate.
#:
#: Comments went 24 -> 25 on 2026-08-26, in the state layer, and it is the
#: widest refusal in the corpus: OAR 660-046-0010(2)(a) takes lots not zoned
#: for residential use out of Division 46 entirely, and this preemption layer
#: applies its defaults to every zone below it without asking which kind of
#: zone it is. The refusal carries the measurement -- 88 zones where the
#: density exemption cancels something, 26 where the ceiling was a real
#: number, seven of those in zones the rule arguably never reached and all
#: seven prohibiting the pod outright -- because a refusal about scope is
#: worth exactly as much as its evidence that the scope does not currently
#: bite.
#:
#: Notes went 89 -> 90 on 2026-08-26, for Gresham's Clear Vision Area, and it
#: is a refusal of a kind this corpus has not had before. 9.0200 was fetched
#: because eleven district-chapter sentences say "Comply with Section 9.0200",
#: and the section turned out to be two paragraphs that both end "The
#: dimensions of the clear vision area and exceptions are described in the
#: Public Works Standards (6.04)." The constraint is real and corner-specific
#: and there is no number in the land use code to encode. The refusal is not
#: "we read this and it does not bite" but "we read this and the number lives
#: in an engineering manual no jurisdiction file declares" -- a document class
#: the corpus has never taken in. That distinction is why it is recorded
#: rather than quietly dropped.
#:
#: Notes went 90 -> 92 the same day for Happy Valley's 16.32 and 16.34, and
#: those two are the heaviest refusals in the corpus. Both cap density on
#: slope-constrained and resource-constrained land at one or two dwelling
#: units per acre, and development on a conservation slope area -- 25% or
#: steeper over 1,000 contiguous square feet -- is prohibited outright. Four
#: units at two per acre is two acres, so where either overlay reaches, this
#: building is dead. They are refused because the form that binds is a
#: buildable-area mask and not a number: 16.32.045(A) excepts "an activity
#: that avoids conservation slope areas and transition slope areas", so the
#: question is whether the pod fits on the part of the lot under 15%, and no
#: field can say that. Encoding the density figure instead would be wrong in
#: both directions at once. This is the clearest case in the corpus of a
#: refusal that is a work order rather than a dismissal.
#:
#: Comments went 25 -> 31 on 2026-08-26 for Fairview, from the three chapters
#: the cross-reference ledger ordered. Four are in the layer defaults and two
#: are zone-level, and each group is a different kind of decline.
#:
#: 19.162.020(O), Vision Clearance, is the Gresham 9.0200 shape one step
#: worse. It is the qualifier on an exemption this layer encodes -- FMC
#: 19.70.020.A.3 waives the side setback "except that buildings shall conform
#: to the vision clearance standards in Chapter 19.162 FMC" -- and it states a
#: height and no extent: structures over three feet are barred from "'vision
#: clearance areas,' as shown above". 19.13's definition closes the loop by
#: saying the area "means the shaded area as shown on the following figure".
#: Two documents, no number, because the number is a drawing. 19.162.020(L),
#: Driveway Openings, is refused for the opposite reason -- it states two
#: numbers and the registry has nowhere to put either. L.1 gives a quadplex a
#: 10-foot minimum driveway and L.2 gives a four-to-seven-unit development 20.
#: 19.163.030(E)(3)(b) is the same shape once more and the one that costs the
#: most: a parking or maneuvering area adjacent to a building must be separated
#: from it by at least four feet, and where the building is residential
#: ground-floor living space the four feet must be landscaped rather than a
#: raised pathway. A rear court in Fairview is four feet deeper than its stalls
#: and its aisle, and ``min_building_separation_ft`` is building-to-building.
#:
#: The fourth is the largest, and it was added after Steph pointed out that
#: "no minimum" is not the same question as "what applies if we build it" --
#: which this product will. Fairview requires no parking and regulates parking
#: fully, and the rules that do the regulating sit in FMC 19.30, a chapter this
#: file already reads four values out of. 19.30.040(E) bars parking between a
#: building and a public street unless a dwelling screens it or the garages and
#: paving stay under half the frontage; 19.30.040(F)(1) caps all driveway
#: approaches at 32 feet per frontage, the same figure as Clackamas ZDO 845.02
#: because both are the state middle-housing model code; 19.30.050(D) gives the
#: townhouse branch a 12-foot cap on outdoor parking and maneuvering per lot,
#: or sends parking to the rear yard entirely. None of it was written down,
#: because no field could hold it and nothing counts a standard nobody has a
#: field for. It is transcribed into the layer now so the field family, when it
#: is built, is a copy job rather than a re-read.
#:
#: The zone pair, VSF and VMU, are refusals to copy a number sideways.
#: 19.163.030(C) states landscape minimums for six named district types and no
#: village district is among them, because the village article answers
#: landscaping itself: 19.145.070 covers VTH and VA, 19.150.070 covers VO and
#: VC. VSF is tempting because its name ends in Residential; VMU is tempting
#: because Chapter 19.150 is *titled* for it and its landscaping sentence is
#: not. Both are the shape that produces an invented standard.
#:
#: Comments went 31 -> 34 on 2026-08-26, in the state layer, and all three are
#: the tail of OAR 660-046-0220(2)(e) -- the subsection whose (B) this corpus
#: has encoded since Phase 0 and whose (C), (D) and (E) nobody had read. Same
#: lesson as Fairview, one level up: the parking clause was opened for the
#: number it caps and closed again before the sentences that say what a city
#: may do about parking it does not require.
#:
#: (E) is the one that matters and it is a redirect: a Large City "must apply
#: the same off-street parking surfacing, dimensional, landscaping, access,
#: and circulation standards that apply to single-family detached dwellings in
#: the same zone." Every stall width, stall depth and aisle width in this
#: corpus was read from a general parking table, and this sentence says the
#: standards that bind a quadplex are whichever ones bind a house on the same
#: ground. It is the fourth rule in the corpus whose content is a pointer --
#: after Gresham 9.0802(F), Clackamas ZDO 845.02 and the Portland aisle -- and
#: the first that puts a live question over geometry already encoded, in every
#: Large City at once. Refused rather than encoded because no zone here
#: records what its single-family parking standards are; until now nothing
#: asked.
#:
#: (D) and (C) are recorded for the opposite reason: neither binds. (D) says a
#: city may allow but not require a garage or carport, which is the sentence
#: that guarantees the pod's surface stalls are legal, and a guarantee is
#: worth a line. (C) lets a city credit on-street spaces against a
#: requirement, which can only ever help a lot, so leaving it out is the
#: conservative direction and saying so is cheaper than re-deciding it later.
#:
#: Comments went 34 -> 37 the same day for Wilsonville, and they are the first
#: fruit of running the required-versus-regulated question over a city that
#: was already finished. Wilsonville requires no parking and caps none -- both
#: fields read `exempt` since 2026-08-22 -- and Section 4.113(.14) subsection
#: D is titled "Standards applicable to Triplexes and Quadplexes" and regulates
#: the parking anyway: half the street frontage for garages and manoeuvring
#: areas, 32 feet of driveway approach per frontage, and on the townhouse
#: branch a 12-foot cap on outdoor parking and manoeuvring per lot. Twelve feet
#: around a nine-foot stall is a single-file driveway, so on unit lots the
#: court the site-plan generator draws is not a thing Wilsonville permits.
#:
#: The third is an absence rather than a refusal, and it is recorded because
#: absences of this kind are invisible: Chapter 4 dimensions a standard space,
#: a compact space and a motorcycle space, and states no drive-aisle width at
#: all. Holding a stall and no aisle is not the same object as an aisle of
#: zero, and 4.113(.14)D.4.c.ii points at the Public Works Standards, which is
#: the Gresham 9.0200 shape again.
#:
#: Comments went 37 -> 45 on 2026-08-27, and all eight came out of one sweep:
#: reading three cities' parking chapters to answer what parking has to LOOK
#: like, given that we build it whatever a code requires. Milwaukie three,
#: Oregon City two, Happy Valley three. They divide into three shapes, and
#: the shapes are the finding rather than the count.
#:
#: A rule that excludes this building from the standard everyone assumes
#: applies. Milwaukie's aisle table is real, is 22 feet at 90 degrees, and
#: does not reach a quadplex: the purpose paragraph of Section 19.606 excepts
#: middle housing from everything in the section except the quarter-acre
#: parking lot rules. Reading the table without reading the paragraph above it
#: would have put a number in this corpus that Milwaukie does not apply. That
#: is the whole-document-grep rule with a jurisdiction attached.
#:
#: A row whose number is legible and whose UNIT is not. Oregon City's Table
#: 17.52.020 asks a triplex or quadplex for a minimum of "2.00" and a maximum
#: of "4" under a header that says the table's figures are per 1,000 square
#: feet of net leasable area unless otherwise stated -- and the row above it
#: says "per unit" and this one says nothing. Per 1,000 square feet, per unit,
#: or in total are three different buildings, and only the third is lawful
#: under the state cap. Deducing the unit from which reading would survive
#: preemption is an argument, not a citation, so both cells are refused and
#: the state cap governs. This is the first refusal in the corpus about a
#: denominator rather than a number.
#:
#: A placement rule with no field to hold it -- now in its sixth and seventh
#: jurisdiction, and no longer a gap so much as a missing field family. Happy
#: Valley 16.43.030.E.4 sets parking back from a street lot line by the
#: building setback, which in its residential zones bans front-yard parking
#: outright rather than capping it -- LIFTED 2026-08-27, see `same_as` and
#: flats/tests/test_same_as.py; the field family it was waiting on was built,
#: and then the carrier for a standard stated by reference; Oregon City
#: 17.16.060.D caps outdoor
#: parking and manoeuvring at forty feet or half the frontage, whichever is
#: less, and 17.16.040 drops that to twelve feet on townhouse lots; Milwaukie
#: 19.607.1.D allows a quadplex a fourth front-yard space and no more, and
#: 19.505.5.F drops to ten feet on townhouse lots. Every one of them is the
#: state middle housing model code in local words, and the registry has no
#: driveway approach width, share-of-frontage, facade-relative placement or
#: manoeuvring-area width to put any of it in.
#:
#: Comments went 67 -> 70 on 2026-08-27, all three in unincorporated Clackamas
#: and all three from the same read: what parking has to look like on the third
#: largest block of pod-fitting lots in the corpus, 18,662 of them, which lays
#: out nothing today because its aisle is unknown.
#:
#: The aisle refusal is a shape the corpus has not had. It is not that the
#: county is silent -- ZDO 1015.02(A)(4) hands curb length, stall depth and
#: aisle width to the Roadway Standards, whose 320.3(a) hands them on to
#: Standard Drawings P100 and P200. Both sheets are now declared and stored,
#: and each stores three lines, because a CAD sheet's only extractable text is
#: its title block. The chain is complete and it terminates in a picture. The
#: nearest relative is Gresham's Clear Vision Area, where the number lives in
#: an engineering manual nobody declared; here the manual was declared, fetched
#: and read, and the number is still drawn rather than written. The title block
#: is not a total loss -- it names the stall, "(9' x 18')" and "(8.5' x 16')",
#: and that is where this layer's stall geometry now comes from.
#:
#: The second is Table 1015-2 note 2: above 3,500 feet in elevation, covered
#: parking for three or more dwelling units. A roof over four stalls is a
#: second structure competing for the same ground, so it is a fitment standard,
#: and there is no field for whether a stall has a roof and no layer holding a
#: lot's elevation. Recorded because unlike almost everything this corpus
#: refuses on a site fact, the condition is reachable: this jurisdiction runs
#: from the Willamette to Mount Hood.
#:
#: The third is a refusal to write `exempt`. The county caps nothing on a
#: quadplex -- Table 1015-1's Dwellings row defers to 1015-2, and 1015-2 states
#: a maximum only in the note about townhouses -- but `parking_max_per_unit` is
#: left absent rather than exempt, because exempt resolves over the state layer
#: and OAR 660-046-0220's cap is real. Absence inherits; exempt overrides. That
#: distinction has cost this corpus a wrong number before and is worth a line.
#:
#: Worth knowing about this ledger, learned writing those two: the window runs
#: FORWARD from the marker, and rows are deduplicated on the window text. A
#: refusal that puts "NOT ENCODED" at the end of its paragraph renders as a
#: stub, and two stubs in one layer collapse into one row. Both zone refusals
#: were written that way first and the count moved by one instead of two. The
#: cure is prose, not code -- lead with the marker -- but a reviewer who
#: expects a count to move and watches it not move should suspect this first.


def test_the_corpus_declares_more_refusals_than_any_ledger_counts() -> None:
    rows = refusals()
    counts = {kind: sum(1 for r in rows if r.kind == kind) for kind in EXPECTED}

    assert counts == EXPECTED
    assert len(rows) == sum(EXPECTED.values())


def test_every_layer_that_refuses_is_named() -> None:
    """Fifteen of the seventeen layers carry at least one, which is the real
    finding: this is not a corner case, it is how the corpus records judgement.
    The two that carry none are the state layer, which holds no zones, and the
    one jurisdiction encoded from a single table."""
    where = {r.where for r in refusals() if r.kind in ("notes", "comments")}
    layers = set(load_rules())

    assert where <= layers | {"or/_state"}
    assert len(where) >= 14


def test_a_refusal_folded_across_a_yaml_line_ending_is_still_found() -> None:
    """Read from the model, not the file. A folded block scalar breaks long
    prose at whatever column it likes, so "not\\nencoded" appears in the file
    and "not encoded" appears in the loaded string. Scanning the file would
    silently under-report, and under-reporting is the one direction this
    subsystem never takes."""
    assert list(_spans("something is not\n   encoded here for a reason")) == [
        "not encoded here for a reason"
    ]


def test_the_window_does_not_stop_at_a_header() -> None:
    """Half the corpus writes "NOT ENCODED, on purpose. (1) ..." and cutting at
    the nearest full stop would report the header and drop the refusal, which
    is a ledger that costs a file-open per row."""
    text = "NOT ENCODED, on purpose. (1) " + "the actual reason goes here. " * 6
    span = next(iter(_spans(text)))

    assert span.startswith("NOT ENCODED, on purpose. (1) the actual reason")
    assert len(span) > FLOOR


def test_a_refusal_carries_where_it_was_found() -> None:
    row = next(r for r in refusals() if r.zone)

    assert row.label == f"{row.where}:{row.zone}"
    assert Refusal("notes", "or/x", None, "t").label == "or/x"


def test_one_layer_can_be_asked_on_its_own() -> None:
    """Test docstrings are dropped when a layer is named, because they belong
    to no layer. Worth stating: the per-layer view is deliberately narrower
    than a filter of the whole."""
    rows = refusals("or/multnomah/gresham")

    assert {r.where for r in rows} == {"or/multnomah/gresham"}
    assert not [r for r in rows if r.kind == "tests"]


def test_the_refusal_that_prompted_this_module_is_gone() -> None:
    """Table 4.0430 was declared unreadable and then read.

    The refusal said its cells "wrap across a dozen lines each and the
    extraction shifts fragments between columns; the setback rows in particular
    cannot be assigned to a district by reading the text." That was true of the
    commercial half of those cells and never true of the Residential sub-cell,
    which RTC, SC and SC-RJ share and which reads identically in all three.

    Nothing detected the contradiction. Four columns were encoded from those
    lines while the sentence still stood."""
    stale = [r for r in refusals() if "guess wearing a citation" in r.text]

    assert stale == []
    gresham = load_rules()["or/multnomah/gresham"]
    for zone in ("RTC", "SC", "SC-RJ", "CMF", "CMU", "CC", "MC"):
        assert "setback_front_ft" in gresham.zones[zone].values, zone
