"""Every footnote in every stored document, captured before anyone judges it.

A footnote is the cheapest way for a code to make a number mean something
other than what it says, and the most expensive thing for us to miss. Gresham
prints a maximum front setback of 30 feet on an arterial and 5 feet on a local
street as a note under the table; read the cell alone and the screen passes
lots the code would refuse. That failure is silent by construction -- the
citation resolves, the number is transcribed correctly, and nothing in the
value records that a marker was sitting next to it.

The reader in ``tables.py`` already sees markers, but only inside a table it
managed to parse, and only in service of extracting a candidate value. So a
footnote in a document whose grid defeated the parser is invisible, and a
footnote block whose numbering style the parser does not recognise degrades
into the placeholder "footnote 3 (text not captured)" -- which is honest and
still leaves nobody to tell.

This module does the other job: a census of the whole store. Every marker
occurrence and every footnote body in every stored document, captured
mechanically, with no judgement about relevance. Judgement comes later and is
recorded; capture is exhaustive and dumb, because anything not pulled here can
only ever be caught by a human reading that exact page, and humans read a
small fraction of encoded rules.

Capture that claims to be complete has to prove it, so the census reconciles
in both directions:

* a body nobody points at (``unmarked``) means the marker was lost in
  extraction -- a superscript that collapsed into the number beside it, or a
  cell the layout reader never emitted;
* a marker nothing defines (``unbodied``) means the block was lost, or sits in
  a document we do not hold.

Either way the document is *not reconciled*, and it is named. That turns "we
captured the footnotes" into "we captured them or the document is on a list",
which is a weaker claim and a checkable one. The residual risk -- a footnote
rendered in a way the extractor cannot see at all -- does not vanish, but it
stops being able to pass as complete.

Numbers restart at 1 under every table, so reconciliation is scoped to the
region a block governs: the run of lines between the previous block and this
one's heading. Reconciling per document instead would let table B's marker 1
be answered by table A's note 1, which under-reports orphans -- the unsafe
direction.

Run it::

    uv run python -m flats.encode.footnotes            # the whole store
    uv run python -m flats.encode.footnotes --layer or/multnomah/gresham
    uv run python -m flats.encode.footnotes --unreconciled
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

#: A notes block announces itself. Tolerates the colspan repeat a caption cell
#: makes when it spans the grid -- "NOTES:  NOTES:" -- and the identifier
#: Gresham puts in front, "Table 4.0130 Notes:".
NOTES_HEAD = re.compile(
    r"^(?:table\s+[\w.-]+\s+)?(?:table\s+)?notes?\s*[:.]?"
    r"(?:\s+(?:table\s+[\w.-]+\s+)?(?:table\s+)?notes?\s*[:.]?)*$",
    re.I,
)

#: One line of scope between the heading and note 1. Gresham's downtown use
#: table prints "Table 4.1120 Notes:", then "The following describe limitations
#: on use categories marked as limited or special use review in Table 4.1120",
#: and only then note 1 -- and the reader walked away from the whole block
#: because the first line under a heading was not numbered.
#:
#: That rule earns its strictness: a "Notes:" heading in this corpus sits over
#: a legend far more often than over notes, and Portland's "The use categories
#: are described in Chapter 33.920" and Milwaukie's "P = Permitted" must both
#: stay out. So the lead-in has to name the table AND announce a list. One
#: line, once, and note 1 has to follow it or the block is still refused.
#:
#: Exactly one line in the corpus wears this shape, and behind it are
#: twenty-four notes to a use table -- including the one that lets a plex into
#: DTM and DMU on a lot of record of 6,500 square feet or smaller.
NOTES_LEAD = re.compile(r"(?=.*\bthe following\b)(?=.*\btable\s+[\w.-]+)", re.I)

#: A line of the permission legend, which a table prints under the same
#: "Notes:" heading as its footnotes and before them: "P = Permitted.", "CSU =
#: Permitted with community service use approval subject to Section 19.904."
#:
#: The legend is why the reader insists on a number under the heading -- in
#: this corpus a "Notes:" heading sits over a legend far more often than over
#: notes. But Milwaukie prints both, legend first, and refusing the block on
#: sight of the legend lost eight footnotes to Table 19.303.2 including the one
#: that lifts the four-consecutive-townhouse limit in the GMU zone. So a legend
#: line is stepped over rather than believed, and anything else that is not a
#: note still ends it.
LEGEND_LINE = re.compile(r"^(?P<code>[A-Z][A-Z/-]{0,6})\s*=\s*\S")

#: The same legend with the extraction pulled apart: the code, the equals sign
#: and the definition each arriving on a line of their own. Milwaukie's second
#: use table prints "P", "=", "Permitted." over four lines and then its notes.
#:
#: A bare "P" on a line is a permission cell far more often than it is a legend
#: code, so this shape is never believed on its own -- only where the very next
#: line is nothing but the equals sign, which no table cell in this corpus is.
LEGEND_CODE = re.compile(r"^[A-Z]{1,4}$")

#: One numbered note *inside* a block, in any of the spellings codifiers use:
#: "1 Density calculations...", "2. Zero lot line dwellings...", "[3] Additional
#: height...", "(4) Townhomes are exempt...".
#:
#: A single space is enough here and is not enough outside a block. Happy
#: Valley writes "1 Density calculations shall be made pursuant to Section
#: 16.63.020(F)." with no period and no column gap, which the table reader's
#: stricter rule declines -- correctly, since outside a block that pattern
#: matches every numbered paragraph in the code. Being inside a block is what
#: earns the looser rule.
#:
#: The brackets have to balance. Troutdale wraps a note onto "(20 feet)."
#: and an unbalanced reading takes that for note 20 -- which is above every
#: mark the list has reached, so it is accepted as the next note and the two
#: real notes below it are lost to the restart rule.
BLOCK_NOTE = re.compile(
    r"^(?P<open>[\[(])?(?P<n>\d{1,2})(?(open)[\])]|[.):]?)[.):]?"
    r"\s+(?P<text>\S.*)$"
)

#: The lettered form, inside a block: Wilsonville's Table 8A runs A through P.
#: A letter earns far less benefit of the doubt than a digit does, because
#: every code in the corpus letters its ordinary subsections -- so this one
#: demands the punctuation a digit may omit. "A. Minimum lot size may be
#: reduced" is a note; "A minimum lot size of 5,000 square feet" is a
#: sentence, and only the period tells them apart. The space before it is
#: extraction's, not the codifier's: Wilsonville prints "F . Front porches".
LETTER_NOTE = re.compile(r"^\(?(?P<n>[A-Z])\)?\s?[.)]\s+(?P<text>\S.*)$")

#: A self-identifying note, which needs no block: Portland prints "[3] Additional
#: FAR and height may be allowed. See 33.110.265.F." under the table with no
#: heading over it.
BRACKET_NOTE = re.compile(r"^\[(?P<n>\d{1,2})\]\s+(?P<text>\S.*)$")

#: A headless run: the number, a column gap, and the text, with nothing
#: announcing it. Milwaukie prints its table notes this way. The gap is what
#: earns the reading -- an ordinary numbered paragraph is "1. The applicant
#: shall", one space and a period -- and the run is only believed where it
#: starts at 1 and ascends, which is checked in `_blocks` rather than here.
#:
#: The period may not join the gap, tempting as it is. Milwaukie prints two
#: real notes as "1.  Properties in the MUTSA have a maximum front yard
#: setback of 10 ft", and admitting that shape to reach them turned 1,200
#: ordinary numbered subsections into footnote bodies across twenty-eight
#: documents -- Troutdale's development standards chapter alone claimed
#: seventy-nine. Punctuation plus a column is how this corpus writes a
#: subsection, not how it writes a note.
HEADLESS_NOTE = re.compile(r"^(?P<n>\d{1,2})\s{2,}(?P<text>\S.*)$")

#: The same run, parenthesised and glued: "(1)For commercial or residential
#: uses there is no minimum lot area, lot width or lot depth." Municode's HTML
#: renders a table's notes this way -- no heading over them, and the marker
#: welded to the first word.
#:
#: The weld is the whole discriminator, and it is a strong one. A codifier
#: writes its ordinary subsections with a space after the bracket -- "(1) Mixed
#: Use Development Requirement." -- so demanding *no* whitespace separates a
#: footnote body from every numbered paragraph in the code. Across the corpus
#: this shape appears on twenty lines in eight documents, and the run rule in
#: `_glued_paren_run` keeps all four of the stragglers out.
#:
#: Missing it cost real rules. Wood Village prints the whole townhouse standard
#: as note (2) under Table 210-3 -- 1,500 square feet, 20 feet of width, no
#: minimum depth -- and it was invisible while this shape was.
GLUED_PAREN_NOTE = re.compile(r"^\((?P<n>\d{1,2})\)(?!\s)(?P<text>\S.*)$")

#: The same run with no gap, no bracket and no weld: the number, one space, the
#: text. Clackamas County prints every table's notes this way -- "9 Except for
#: middle housing developed pursuant to Section 845" -- and nothing announces
#: them.
#:
#: One space is the weakest discriminator of the three, because it is also how
#: a great deal of ordinary prose begins, so this shape buys its reading with
#: the run instead: `_tight_run` demands notes 1, 2 AND 3 with nothing but
#: blank lines between them, where the gapped and glued forms are believed from
#: two. Across the whole corpus that bar admits three blocks and no false one.
#:
#: Missing it cost a county. ZDO Section 315 is the only document behind every
#: value in Clackamas unincorporated, and it carried 305 footnote markers and
#: zero bodies -- so the gate that holds a value back when an unread note
#: governs it had nothing to hold, and reported the layer clean.
TIGHT_NOTE = re.compile(r"^(?P<n>\d{1,2}) (?P<text>\S.*)$")

#: The digit welded to its own first word, with no bracket and no gap:
#: Wilsonville prints "2No additional off-street parking is required for
#: middle housing" directly under note 1. Read only inside a block, and only
#: where a capital and a lowercase letter follow -- which is what keeps a
#: measurement ("50Feet" does not occur; "10 feet" does) and a citation out.
#:
#: One line in the corpus wears this shape, and it is a parking rule, which
#: is a standard the screen reads. Swallowed as the tail of note 1 it was a
#: sentence nobody could rule on and nothing pointed at.
GLUED_NOTE = re.compile(r"^(?P<n>\d{1,2})(?P<text>[A-Z][a-z].*)$")

#: The parenthesised note with a space after the bracket, which is the shape
#: this module refuses everywhere else: `GLUED_PAREN_NOTE` demands the weld
#: precisely because "(1) Mixed Use Development Requirement." is how every code
#: in the corpus writes an ordinary subsection.
#:
#: What buys it here is where it sits. `_paren_run` believes the shape only
#: where the run climbs 1, 2, 3 one note per line, and the last line above it
#: carries a footnote marker and is not the colon that introduces a list. That
#: last clause is the whole of it: across the corpus the bare run appears in
#: fourteen documents and is an ordinary subsection in thirteen of them, every
#: one introduced by "one or more of the following:" or an equivalent.
#:
#: Missing it cost Fairview's use table. Six notes under Table 19.30.030,
#: including the one that sends a quadplex to the design standards of FMC
#: 19.30.040, and the census had zero of them.
PAREN_NOTE = re.compile(r"^\((?P<n>\d{1,2})\)\s+(?P<text>\S.*)$")

#: The number on its own line, with the text beneath it. An HTML table renders
#: each cell as its own line, so a block that reads "1  Density calculations
#: shall be..." on the page arrives as "1", newline, "Density calculations
#: shall be...". Happy Valley's largest block is written this way and was
#: invisible until the shape was allowed -- twelve notes including one that
#: reduces a corner lot's front setback to eight feet on a local street, which
#: is precisely the kind of qualifier a screen must not miss.
STACKED_NOTE = re.compile(r"^\[?\(?(?P<n>\d{1,2})\)?\]?[.):]?$")

#: The same, lettered and on its own line. Punctuation is required here for
#: the same reason: a bare "A" on a line is a table cell in half the corpus.
STACKED_LETTER = re.compile(r"^\(?(?P<n>[A-Z])\)?\s?[.)]$")

#: What ends a block. A note runs onto the next line often enough that an
#: unrecognised line has to be read as continuation, so the block needs an
#: explicit floor: the codifier's amendment history, the next section, the next
#: table, or the running header.
ENDS_BLOCK = re.compile(
    r"^(?:\(Ord[.\s]|\(Added|§|Section\s+\d|Chapter\s+\d|Table\s+[\w.-]+"
    r"|\d{1,3}\.\d{2,4}(?:\.\d{1,4})?\s+[A-Z])",
    re.I,
)

#: The marker kinds that carry no weight of their own. A lone permission code
#: and a bare capital letter are both shapes prose can wear by accident, so
#: `census` keeps them only where the block governing the line states a note
#: by that mark.
PROVISIONAL = ("lone", "letter")

#: A block cannot run forever. Past this the "unrecognised line continues the
#: previous note" rule is doing more harm than good, and whatever we are
#: reading is not a notes block any more.
BLOCK_LIMIT = 80

#: How far above a block to look for the table header it is repeating. About a
#: page of a codifier's PDF.
REPEAT_WINDOW = 80

#: A marker glued to the unit, which is what a PDF superscript becomes when
#: extraction loses its baseline: "45 feet2", "35 ft.12", "20,000 sq. ft.1".
#: Codes write runs of them -- "20 feet7,8,9,10,11" -- and each number in the
#: run is its own marker.
#:
#: Anchored to the end of the cell, which is not fussiness. Extraction
#: sometimes leaves a row's cells separated by a single space -- Oregon City's
#: height row arrives as "All 65 feet 60 feet 50 feet" -- and an unanchored
#: rule reads each cell's number as a marker on the cell before it. That one
#: relaxation invented 76 markers in a single document.
GLUED_MARKER = re.compile(
    r"(?:sq\.?\s*ft\.?|sf|ft\.|feet|percent|%)\s?(?P<n>\d{1,2}(?:,\s?\d{1,2})*)$",
    re.I,
)

#: The parenthesised form, as Wood Village prints it: "10 ft(1)".
PAREN_MARKER = re.compile(
    r"(?:sq\.?\s*ft\.?|sf|ft\.?|feet|percent|%)\s?\((?P<n>\d{1,2})\)$", re.I
)

#: The parenthesised form with no unit in front of it, which is what a marker
#: on a row *label* or on a wordless cell looks like: "Minimum Lot Size(1)",
#: "None(2)", "Minimum Landscape Required(2)". `PAREN_MARKER` cannot see these
#: because it is anchored to a unit, and half of Wood Village's Table 230-2 is
#: written without one.
#:
#: Narrow the same way `LABEL_MARKER` is: the bracket must be welded to the
#: cell's last character. What that still lets through is a code citation --
#: "Subject to TDC 40.300(4)" -- so `PAREN_CITATION` is subtracted first.
PAREN_LABEL_MARKER = re.compile(r"(?<=[0-9a-z%)])\((?P<n>\d{1,2})\)\s*$", re.I)

#: A parenthesised subsection on the end of a cross-reference: "TDC 40.300(4)",
#: "ORS 455.315(2)", "Section 8.0117(C)(3)", "Figure 4.0420(  I)(1)". The
#: dotted section number is what tells them from a marker; the whitespace
#: inside the brackets is extraction's, not the codifier's.
PAREN_CITATION = re.compile(
    r"\d{1,3}\.\d{2,4}(?:\.\d{1,4})?(?:\(\s*[A-Za-z0-9]{1,3}\s*\))+"
)

#: The bracketed form, anywhere on a line: "30 ft. [3]".
BRACKET_MARKER = re.compile(r"\[(?P<n>\d{1,2})\]")

#: The marker spelled out in words, which needs no bracket and no layout:
#: Troutdale's dimensional tables print "10 or 20" in the cell and "see note
#: 2" under it. Read anywhere on a line, like the bracket, because the phrase
#: identifies itself -- there is no other thing "see note 2" can mean.
#:
#: Forty-one of the corpus's forty-two occurrences are Troutdale's, and every
#: one of its fourteen notes was a body nobody pointed at. Four of them make a
#: setback depend on where the driveway is: front yard 20 feet instead of 10
#: if access is taken from the front, rear yard 0 feet with an alley and 10
#: without. A screen that reads the cell alone takes the looser number.
SEE_NOTE = re.compile(r"\bsee\s+notes?\s+(?P<n>\d{1,2})\b", re.I)

#: The lettered marker, which a lettered notes block is the only licence for.
#: Wilsonville runs its Frog Pond tables' notes A through P and marks the
#: cells to match -- "8,000 60' 40% E 40 35 20 F 20 M 18G 20" is four of them,
#: and an HTML extraction puts the header's run on a line of its own, "A,B".
#:
#: A bare capital letter is the weakest marker shape there is, so this one
#: carries no weight of its own: it is emitted provisional, and `census` keeps
#: it only where the block governing that line actually states a note by that
#: letter. A document with no lettered block reads none of these at all, and a
#: stray letter can never invent an orphan -- it can only satisfy a body that
#: the same block already states.
#:
#: Missing it cost Wilsonville forty-three notes, in the document behind a
#: hundred and seventy-five encoded values: the townhouse minimum lot size,
#: the quadplex minimum lot size in R-5 and R-7, the shared-wall exemption
#: from side setbacks, and the combined side yard on a wide lot.
LETTER_CELL = re.compile(r"^(?P<n>[A-Z](?:,[A-Z])*),?$")

#: The same marker welded to the value it qualifies: "18G", "10D", "6B", "1J".
#: The value has to come first, which is what keeps the zone code "S3" and the
#: street name "SW" out.
LETTER_GLUED = re.compile(r"^\d[\d,.'’%]*(?P<n>[A-Z])$")

#: Markers on a row *label* rather than a cell: "Minimum lot area1,2". Only
#: read on a line that is laid out as a table row, because in prose a trailing
#: digit is a cross-reference, a year, or the number of the paragraph.
#:
#: Two things the label may still carry behind the marker. Gresham spaces the
#: list -- "(based)1, 5, 6" -- and it puts the unit last, so the marker sits in
#: the middle of "Maximum Height1,2,3,4 (feet)". One parenthesised group is
#: allowed to follow, and it has to balance, which is what keeps the marker
#: welded to the label it belongs to rather than floating anywhere in the cell.
LABEL_MARKER = re.compile(
    r"(?:(?<=[a-z])|(?<=\)))(?P<n>\d{1,2}(?:\s*,\s*\d{1,2})*)"
    r"\s*(?:\([^()]*\))?\s*$"
)

#: A marker on a use-table cell: "P3", "L9", "L/SUR11", "P/L2". The letters are
#: the permission vocabulary and nothing else, because a bare letter-then-digit
#: rule would read the zone code "R5" as a footnoted "R". Use tables are where
#: the qualifier most often lives -- "permitted only as an accessory use" is a
#: footnote, not a column -- and Gresham writes a whole row of them per line,
#: single-spaced, so this one is read anywhere on the line rather than as a
#: whole cell.
#:
#: "A", "N" and "S" are deliberately absent from the vocabulary even though
#: codes use them, because they are also English: Gresham's flood definitions
#: name "Zones A, AO, AH, A1-30" and its design chapter labels a guideline
#: "G5" against a standard "S5". Those three letters alone invented 268
#: markers in one document. A code that permits with "A" loses its markers
#: here and gains them back as unmarked bodies, which is the honest direction
#: to fail in.
CELL_MARKER = re.compile(
    r"(?<![A-Za-z0-9/])(?:P/L|L/SUR|L/P|C/L|NP|SUR|CU|PC|P|C|X|L)"
    r"(?P<n>\d{1,2}(?:\s*,\s*\d{1,2})*)(?![\d])"
)

#: Portland's landscaping levels, which are spelled exactly like the "limited"
#: permission code with a footnote on it. "Landscaped to at least the L1
#: standard" is a cross-reference to Chapter 33.248, and "10 ft. @ L3" is a
#: buffer width and the standard it is planted to. Neither is a marker.
#:
#: Nineteen of the twenty orphans Chapter 33.130 reported were this, and a
#: ledger of invented orphans is worse than useless -- it hides the one real
#: marker underneath them and asks somebody to go looking for nineteen notes
#: that were never written. The same argument that keeps "A", "N" and "S" out
#: of the permission vocabulary, made one level down: the code is real, the
#: context is what says this is not it.
LANDSCAPE_LEVEL = re.compile(
    r"(?:@\s*|/\s*|(?i:\b(?:the|to|least|or)\s+))(?P<n>[LF]\d)\b"
    r"|(?P<m>[LF]\d)(?=\s+(?i:standards?|levels?)\b)"
)

#: A line that is nothing but one permission code and the notes on it. An HTML
#: table extraction puts every cell on its own line, so the row that says a
#: quadplex is permitted subject to notes 7 and 8 arrives as the four
#: characters "P7,8" -- one code, no column gap, and nothing else to earn its
#: reading. The pattern is unambiguous where a lone "P1" inside a sentence is
#: not: prose does not consist of a permission code.
LONE_CELL = re.compile(
    r"^(?:P/L|L/SUR|L/P|C/L|NP|SUR|CU|PC|P|C|X|L)\d{1,2}(?:\s*,\s*\d{1,2})*$"
)

#: The same cell where the codifier parenthesises its notes and leaves a space:
#: Fairview writes "X(1) (2)" for permitted subject to notes 1 and 2, and
#: "X(CU) (1)" for a conditional use subject to note 1. `PAREN_LABEL_MARKER`
#: is welded to the cell's last character on purpose -- one space of slack
#: there reads "twenty (20)" at the end of a wrapped sentence as a marker, in
#: eleven documents -- so the slack is bought by the whole line instead.
#: Prose does not consist of a permission code and a bracket.
LONE_PAREN_CELL = re.compile(
    r"^(?:P/L|L/SUR|L/P|C/L|NP|SUR|CU|PC|P|C|X|L)"
    r"(?:\s*\((?:[A-Z]{1,3}|\d{1,2})\))+$"
)

#: The digits inside such a cell. "(CU)" is the review type and not a note.
PAREN_MARK = re.compile(r"\((\d{1,2})\)")

#: A use row states several permissions, so one lonely match on a line of
#: prose is not a row. Either the line is laid out with column gaps or it
#: carries more than one of these codes.
CELL_VOCAB = re.compile(
    r"(?<![A-Za-z0-9/])(?:P/L|L/SUR|L/P|C/L|NP|SUR|CU|PC|P|C|X|L)"
    r"\d{0,2}(?![A-Za-z0-9])"
)

#: Page furniture printed inside a block: the codifier's page stamp
#: "[4.0400]-5" and the running header it sits under. Read as note text it
#: would be harmless; read as the end of the block it loses every note after
#: the page break.
#: Municode's is the section mark, the section number and the publication it
#: is running: "§ 4.127 WILSONVILLE CODE", "§ 4.127PLANNING AND LAND
#: DEVELOPMENT", with the page stamp "CD4:178.3Supp. No. 5" under it. Both
#: land in the middle of a notes list every time a list crosses a page, and
#: the section mark is what tells them from the heading of the next section --
#: a codifier prints it on the header and not on the heading. The replacement
#: character is there because extraction loses the glyph about half the time.
FURNITURE = re.compile(
    r"^\[[^\]]+\]-\d+$|Development Code\s+\(\d|^Page \d+$"
    r"|^(?:§|\ufffd)\s*\d{1,3}\.\d{2,4}"
    r"|^[A-Z]{1,3}\d+:\d+"
    # Extraction also splits a running header across two lines, so the
    # publisher and the edition date each arrive alone. Both are anchored
    # whole, because a note that ends "all other applicable requirements of
    # the Community Development Code" is a sentence, not the head of a page.
    r"|^City of [A-Z][\w ]{2,20} Development Code$"
    r"|^\(\d{1,2}/\d{2,4}\)$",
    re.I,
)

#: The page frame, in the one shape that cannot be case-folded. Troutdale
#: stamps every page "TDC3-7" and runs a header over it that pairs the section
#: number with the publication or chapter name in capitals -- "3.130
#: TROUTDALE DEVELOPMENT CODE" on one side of the spread and "ZONING
#: DISTRICTS      3.130" on the other. Both land in the middle of a notes list
#: every time one crosses a page.
#: Gresham stamps its pages "[4.1100]" and then the page number across the
#: gutter, "-9". The same thing the first form is, in another city's furniture,
#: and it carries something the first does not: the chapter the page belongs
#: to, which is what tells its running header from a real section heading.
PAGE_STAMP = re.compile(
    r"^[A-Z]{2,5}\d{1,3}-\s?\d{1,3}$|^\[(?P<ident>[^\]]+)\]\s*-\s?\d{1,3}$"
)

#: The title-then-number half, which is unambiguous: no code in this corpus
#: heads a section with the number last.
FRAME_HEAD_TRAILING = re.compile(
    r"^[A-Z][A-Z ]{4,}\s{2,}\d{1,3}\.\d{2,4}(?:\.\d{1,4})?$"
)

#: The number-then-title half, which is shaped exactly like a Gresham section
#: heading -- "4.0130      RESIDENTIAL LAND USE DISTRICT STANDARDS" is a real
#: one, and ending a block there is right. So this half is only believed
#: directly under the page stamp, which is the rest of the frame it belongs
#: to. A heading has a blank line over it, not a page number.
#:
#: And where the stamp names its chapter, the number settles it outright: a
#: running header repeats the chapter the stamp just gave -- "[4.1100]" then
#: "4.1100 DOWNTOWN PLAN DESIGN DISTRICT" -- while a real heading three lines
#: under the same stamp is a *different* number, "[4.1500]" then "4.1508
#: DEVELOPMENT STANDARDS TABLE". Reading the second as furniture ran
#: Springwater's last note on into the section below it.
FRAME_HEAD_LEADING = re.compile(
    r"^(?P<n>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)\s+[A-Z][A-Z ]{4,}$"
)

#: How close under the stamp the ambiguous half has to sit.
FRAME_REACH = 3

#: Two or more spaces: the column gap that tells a table row from a sentence.
GAP = re.compile(r"\s{2,}")

#: A full stop with a space after it -- what a sentence has and a row of table
#: cells does not. The cell rule has to read lines that lost their column gaps
#: in extraction (Gresham's plan district tables print "Single Detached
#: Dwelling P P L1" on one single-spaced line), and the price of that reach is
#: that running prose naming a design element -- "the plaza must meet the
#: minimum standards of design element P1 in Table 19.65.090(B)(2)" -- is the
#: use-table cell pattern exactly. Neither a label like "Parks, Open Spaces,
#: Paths, and Trails" nor a citation like "FMC 19.490.400" carries one.
SENTENCE = re.compile(r"\.\s")

#: A bracket that belongs to a figure or section number rather than to a cell:
#: "See Figure 50.04.001-11[5]", where the figure is named after the note that
#: sends you to it. Read as a marker it ends the block a note early, which is
#: how Lake Oswego lost the sentence putting every R-0 and R-3 standard under
#: a per-parcel check. Glued to a bare number -- "28 - 32[5]" -- it is still a
#: marker, so only the citation shapes are forgiven.
CROSS_REFERENCE = re.compile(
    r"(?:figure|table|section|§|�)\s*[\w.\-]*\[\d{1,2}\]", re.I
)

#: The head of a numbered paragraph: "4. Community Service in RM1 through RM4".
#: Deliberately the ordinary shape, because the paragraph earns its reading
#: from what it *says* rather than from how it is laid out -- see `DECLARES`.
DECLARED_HEAD = re.compile(r"^\(?(?P<n>\d{1,2})\)?[.)]\s+\S")

#: A paragraph naming the marker it answers, and the table that marker is on:
#: "This regulation applies to all parts of Table 120-1 that have a [4]."
#:
#: Portland prints no notes block under its use tables. The limitations are
#: numbered subsections of the Primary Uses section -- ordinary prose by every
#: layout test this module has -- and each one declares its own marker in its
#: first sentence. Nothing about the page says "footnote"; the sentence does.
#: Five base-zone chapters are written this way, including 33.120, the chapter
#: that decides whether a four-unit building is allowed at all, and between
#: them they carried a hundred and fifty markers no block could answer.
#:
#: The slack in the middle is extraction's. A page break lands inside the
#: table's own name -- "Table 120-" then "1 that have a [3]" -- and the
#: indefinite article arrives split as "a n [8]", so the table number is read
#: across the hyphen and a couple of short words are allowed before the
#: bracket, and the bracket itself is allowed to have picked up whitespace --
#: Portland's single-dwelling chapter prints "that have a [ 4]". The closing
#: bracket is required: without it the pattern reads any sentence that
#: mentions a table and a number.
#:
#: Three verbs and two brackets, and a corpus-wide sweep for "Table N-M
#: <words> (n)" finds no fourth of either. Portland says "that have a [4]",
#: "that have note [4]", "that have a note [4]"; Wood Village says "marked
#: with a (1)" and, once, "with the number '(2)'", and parenthesises its
#: markers to match. Widening the verb without widening the bracket would have
#: read Wood Village's sentence and then looked for a mark it does not print.
#: The curly quotes are that one sentence's -- it quotes its own marker.
DECLARES = re.compile(
    r"table\s+(?P<a>\d{2,3})\s*-\s*(?P<b>\d{1,2})\s+"
    r"(?:that\s+have|marked\s+with|with\s+the\s+number)\s+"
    r"(?:[a-z]{1,4}\s+){0,2}[“”\"']?"
    r"(?:\[\s*(?P<n>\d{1,2})\s*\]|\(\s*(?P<p>\d{1,2})\s*\))",
    re.I,
)

#: A table's caption, printed on a line of its own: "Table 120-1". A wide table
#: repeats it on every page it crosses, so the first occurrence opens the span
#: and a *different* table's caption closes it.
#:
#: Wood Village titles its captions -- "Table 240-1. Uses in Manufacturing
#: Zones" -- so a title is allowed, behind a period or a colon. The
#: punctuation is what keeps a declaring sentence out: "Table 240-1 marked
#: with a (1)" also starts a line and also names the table, and reading it as
#: the caption would open the region at the note instead of at the table.
TABLE_CAPTION = re.compile(
    r"^table\s+(?P<a>\d{2,3})\s*-\s*(?P<b>\d{1,2})\s*(?:[.:]\s+\S|$)", re.I
)

#: The head of a code section: "33.120.205 When Primary Structures are
#: Allowed". Closes a table's span where no other table follows it.
SECTION_HEAD = re.compile(r"^\d{1,3}\.\d{2,4}(?:\.\d{1,4})?\s+[A-Z]")

#: The header a chapter prints on every page, which lands in the middle of a
#: declared limitation every time one crosses a page break. `_bodies` never
#: sees these because `ENDS_BLOCK` stops a block at "Chapter 33.100"; a
#: declared paragraph has to read through them, since Portland breaks pages
#: inside a single limitation and the rest of it is still the note.
RUNNING_HEADER = re.compile(
    r"^Chapter\s+\d|^Title\s+\d{1,2},|^\d{1,2}/\d{1,2}/\d{2,4}\b"
    r"|^\d{1,3}-\s*\d{0,3}$|^\d{1,3}$"
)

#: How far a declared paragraph is read for its declaration, and how far the
#: last one in a run runs on. Long enough for the sentence to survive a page
#: break, short enough that a paragraph which declares nothing is not searched
#: into the next section.
DECLARED_LIMIT = 14


@dataclass(frozen=True, slots=True)
class Marker:
    """One footnote reference, where it sits and how it was written."""

    doc: str
    line: int
    #: As the codifier printed it: "1", "12", "A". A string because a code
    #: that letters its notes is not a code with unnumbered notes, and
    #: renumbering them to suit the type would lose which note a reviewer is
    #: being sent to read.
    mark: str
    kind: str
    text: str

    @property
    def quote(self) -> str:
        return f"{self.doc}#L{self.line}"


@dataclass(frozen=True, slots=True)
class Body:
    """One footnote's text, and the line a reviewer can open to read it."""

    doc: str
    line: int
    #: As printed -- see `Marker.mark`.
    mark: str
    text: str

    @property
    def quote(self) -> str:
        return f"{self.doc}#L{self.line}"


@dataclass(frozen=True, slots=True)
class Block:
    """A run of numbered notes, and the lines whose markers it answers.

    ``region`` is where this block's markers are allowed to be: after the
    previous block ended and before this one's heading. A marker below the
    block belongs to the next one, not this.
    """

    head: int
    end: int
    region: tuple[int, int]
    bodies: tuple[Body, ...]
    #: The lines this block's own text occupies, where that is not simply
    #: everything from its head to its end. Portland prints half a use table's
    #: limitations, then the table, then the rest of them, so a declared block
    #: straddles its own table -- and a table inside a block is a table whose
    #: markers are never counted. Empty means the ordinary reading.
    spans: tuple[tuple[int, int], ...] = ()

    @property
    def marks(self) -> frozenset[str]:
        return frozenset(b.mark for b in self.bodies)

    @property
    def covered(self) -> tuple[tuple[int, int], ...]:
        """Where this block's text sits, for the rule that markers inside a
        block are declarations rather than references."""
        return self.spans or ((self.head - 1, self.end),)


@dataclass(frozen=True, slots=True)
class Census:
    """What one document says about its own footnotes, both directions."""

    layer: str
    doc: str
    blocks: tuple[Block, ...]
    markers: tuple[Marker, ...]
    #: Markers whose number no block in their region defines.
    unbodied: tuple[Marker, ...]
    #: Bodies no marker in their region points at.
    unmarked: tuple[Body, ...]

    @property
    def bodies(self) -> tuple[Body, ...]:
        return tuple(b for block in self.blocks for b in block.bodies)

    @property
    def reconciled(self) -> bool:
        return not self.unbodied and not self.unmarked

    @property
    def total(self) -> int:
        return len(self.markers) + len(self.bodies)


def _blocks(lines: Sequence[str]) -> list[Block]:
    """Every notes block in the document, in order.

    Three shapes: a headed block, which is a "NOTES:" line followed by numbered
    entries; a bracket run, which numbers itself and needs no heading; and a
    headless run, which is a codifier printing "1", a column gap and the note
    under a table it has just finished.
    """
    found: list[Block] = []
    i = 0
    previous_end = 0
    while i < len(lines):
        stripped = lines[i].strip()
        headed = bool(stripped) and NOTES_HEAD.match(stripped) is not None
        bracketed = BRACKET_NOTE.match(stripped) is not None
        headless = (
            _headless_run(lines, i)
            or _glued_paren_run(lines, i)
            or _paren_run(lines, i)
            or _tight_run(lines, i, previous_end)
        )
        if not headed and not bracketed and not headless:
            i += 1
            continue
        head = i
        start = i + 1 if headed else i
        # A caption cell spanning the grid prints its heading once per column,
        # and an HTML extraction puts each of those on its own line.
        while start < len(lines) and NOTES_HEAD.match(lines[start].strip()):
            start += 1
        bodies, end = _bodies(lines, start)
        if not bodies:
            # A heading with nothing numbered under it is a caption for prose,
            # or a cross-reference to another table's notes. Not a block.
            i += 1
            continue
        found.append(
            Block(
                head=head + 1,
                end=end,
                region=(previous_end, head),
                bodies=tuple(bodies),
            )
        )
        previous_end = end
        i = max(end, i + 1)
    return found


def _table_span(
    lines: Sequence[str], a: str, b: str, bar: Sequence[int] = ()
) -> tuple[int, int] | None:
    """The lines of the table a declaration names, or None if it is not here.

    A declared note is not positional -- it says which table it is about -- so
    it governs that table's markers wherever the codifier chose to print the
    table. Portland prints Table 100-1 above its limitations and Table 120-1
    below them, which is exactly the ambiguity the region rule exists to
    refuse, and exactly the ambiguity the codifier resolved by naming it.

    Returning None where the caption is missing is the point of the rule: a
    note that claims a table we cannot find governs nothing, and its markers
    stay orphans.
    """
    caption = re.compile(rf"^table\s+{a}\s*-\s*{b}\s*(?:[.:]\s+\S|$)", re.I)
    first = next(
        (i for i, raw in enumerate(lines) if caption.match(raw.strip())), None
    )
    if first is None:
        return None
    high = min((j for j in bar if j > first), default=len(lines))
    for j in range(first + 1, high):
        stripped = lines[j].strip()
        if TABLE_CAPTION.match(stripped) and not caption.match(stripped):
            return first, j
        if SECTION_HEAD.match(stripped):
            return first, j
    return first, high


def _paragraph_end(
    lines: Sequence[str], i: int, heads: Sequence[int], k: int
) -> int:
    """Where the numbered paragraph starting at ``i`` stops.

    The next numbered paragraph is the obvious floor and not a sufficient one:
    the last limitation in a run is followed by the lettered subsection that
    ends the list, and then by the table itself. Reading to the next number
    swallows that table, and a table inside a block is a table whose markers
    are never counted -- which turns eleven captured notes into eleven notes
    nobody points at, and reports the document reconciled the wrong way round.
    """
    stop = heads[k + 1] if k + 1 < len(heads) else len(lines)
    for j in range(i + 1, min(stop, i + DECLARED_LIMIT * 2)):
        stripped = lines[j].strip()
        if (
            TABLE_CAPTION.match(stripped)
            or SECTION_HEAD.match(stripped)
            or LETTER_NOTE.match(stripped)
        ):
            return j
    return min(stop, i + DECLARED_LIMIT * 2)


def _declared_text(lines: Sequence[str], start: int, stop: int) -> str:
    """One declared paragraph, with the page furniture taken back out.

    A chapter header is two lines -- "Chapter 33.100" and the chapter's name
    under it -- and only the first is recognisable on its own. The second is
    dropped for sitting where it sits, which is the only thing that
    distinguishes "Open Space Zone" from a sentence.
    """
    out: list[str] = []
    header = False
    for raw in lines[start:stop]:
        stripped = raw.strip()
        if not stripped:
            continue
        if FURNITURE.search(stripped) or RUNNING_HEADER.match(stripped):
            header = stripped.lower().startswith("chapter")
            continue
        if header:
            header = False
            continue
        out.append(stripped)
    return " ".join(out)


def _declared(lines: Sequence[str], doc: str) -> list[Block]:
    """Runs of numbered paragraphs that name the marker each one answers.

    Two paragraphs are demanded before the run is believed, and each has to
    carry its own declaration -- there is no "the next one is probably a note
    too". The paragraph's own number must equal the mark it declares, which
    across the corpus it does in all ninety-one cases and which keeps a
    sentence that merely mentions another table's footnote out.
    """
    heads = [i for i, raw in enumerate(lines) if DECLARED_HEAD.match(raw.strip())]
    found: list[tuple[int, int, str, str, str]] = []
    for k, i in enumerate(heads):
        stop = heads[k + 1] if k + 1 < len(heads) else len(lines)
        stop = min(stop, i + DECLARED_LIMIT)
        joined = " ".join(raw.strip() for raw in lines[i:stop])
        got = DECLARES.search(joined)
        if got is None:
            continue
        mark = got.group("n") or got.group("p")
        head = DECLARED_HEAD.match(lines[i].strip())
        if head is None or head.group("n") != mark:
            continue
        found.append((i, _paragraph_end(lines, i, heads, k), mark, *got.group("a", "b")))

    out: list[Block] = []
    run: list[tuple[int, int, str, str, str]] = []
    for entry in found + [None]:  # type: ignore[list-item]
        same = bool(run) and entry is not None and entry[3:] == run[0][3:]
        if same:
            run.append(entry)  # type: ignore[arg-type]
            continue
        if len(run) >= 2:
            span = _table_span(lines, run[0][3], run[0][4], [e[0] for e in found])
            if span is not None:
                out.append(
                    Block(
                        head=run[0][0] + 1,
                        end=run[-1][1],
                        region=span,
                        spans=tuple((start, stop) for start, stop, _, _, _ in run),
                        bodies=tuple(
                            Body(
                                doc=doc,
                                line=start + 1,
                                mark=mark,
                                text=_declared_text(lines, start, stop),
                            )
                            for start, stop, mark, _, _ in run
                        ),
                    )
                )
        run = [entry] if entry is not None else []  # type: ignore[list-item]
    return out


def _order(mark: str) -> tuple[int, int]:
    """A sort key over mixed marks: digits first, then letters.

    Only ever used to ask whether the numbering restarted, which is how a
    block knows it has ended. A block that runs 1, 2, 3 then A, B is two
    lists in one, and reading them as one list is closer to the truth than
    cutting the second one off unread.
    """
    return (0, int(mark)) if mark.isdigit() else (1, ord(mark))


def _next_content(lines: Sequence[str], i: int) -> str:
    """The next line with anything on it, stripped, or "" at the end."""
    for raw in lines[i : i + 4]:
        stripped = raw.strip()
        if stripped:
            return stripped
    return ""


def _headless_run(lines: Sequence[str], i: int) -> bool:
    """Whether a numbered notes run starts here with nothing announcing it.

    Believed only from its first note, and only where a second follows it: a
    lone "1  something" is a table cell about as often as it is a footnote,
    and two in sequence is a list.
    """
    first = HEADLESS_NOTE.match(lines[i].strip())
    if first is None or first.group("n") != "1":
        return False
    for raw in lines[i + 1 : i + 12]:
        stripped = raw.strip()
        if not stripped:
            continue
        if ENDS_BLOCK.match(stripped) or NOTES_HEAD.match(stripped):
            return False
        following = HEADLESS_NOTE.match(stripped)
        if following is not None:
            return following.group("n") == "2"
    return False


def _glued_paren_run(lines: Sequence[str], i: int) -> bool:
    """Whether a parenthesised, glued notes run starts here.

    Same standard of proof as `_headless_run`: believed only from its own note
    1, and only where note 2 follows before anything ends the block. A lone
    "(2)See 250.200 D. Limited Uses per Title 4" is a note whose siblings the
    extraction lost, and reading it alone would let the census claim a block it
    cannot show -- so it stays an unbodied marker, which is the direction that
    reports a problem rather than hiding one.
    """
    first = GLUED_PAREN_NOTE.match(lines[i].strip())
    if first is None or first.group("n") != "1":
        return False
    for raw in lines[i + 1 : i + 12]:
        stripped = raw.strip()
        if not stripped:
            continue
        if ENDS_BLOCK.match(stripped) or NOTES_HEAD.match(stripped):
            return False
        following = GLUED_PAREN_NOTE.match(stripped)
        if following is not None:
            return following.group("n") == "2"
    return False


def _paren_run(lines: Sequence[str], i: int) -> bool:
    """Whether a spaced parenthesised notes run starts here.

    The shape alone proves nothing -- see `PAREN_NOTE` -- so this asks for
    three things at once: the run climbs 1, 2, 3 with one note per line; the
    last line above it carries a footnote marker, which is what a notes block
    sits under; and that line is not a colon, which is what a list of criteria
    hangs off. Thirteen of the corpus's fourteen bare runs are subsections
    introduced by "one or more of the following:", and the colon is how they
    say so.
    """
    first = PAREN_NOTE.match(lines[i].strip())
    if first is None or first.group("n") != "1":
        return False
    above = next((lines[k] for k in range(i - 1, -1, -1) if lines[k].strip()), "")
    if above.strip().endswith(":") or not _bears_a_marker(above):
        return False
    want = 2
    for raw in lines[i + 1 :]:
        stripped = raw.strip()
        if not stripped:
            continue
        got = PAREN_NOTE.match(stripped)
        if got is None or int(got.group("n")) != want:
            break
        if want == 3:
            return True
        want += 1
    return False


def _tight_run(lines: Sequence[str], i: int, since: int) -> bool:
    """Whether a one-space notes run starts here.

    A higher standard of proof than its two siblings, because its shape is the
    weakest. A column gap or a welded bracket is enough on its own to tell a
    note from a numbered paragraph; one space is not, because one space is also
    how an ordered list of ordinary provisions arrives. So this shape has to
    prove itself twice.

    First the run: 1, then 2, then 3, in order, with nothing but blank lines
    between them. Nothing but blank lines is the load-bearing half -- a code's
    numbered subsections are separated by the prose they govern, so a single
    interposed sentence declines the whole run and only a bare stacked list
    survives.

    Then the markers. A notes block exists to answer markers, so a run with
    nothing pointing into it from the region it would govern is a list, not a
    block -- and reading it as one manufactures bodies nobody references, which
    is worse than missing it: ``unmarked`` is how this census reports a marker
    lost in extraction, and filling it with ordinary prose lists destroys the
    signal. ZDO 845 is the case that proves it: sixteen numbered lists, not one
    footnote marker in the document.

    The other shapes are exempt from that second test on purpose. A "NOTES:"
    heading, a bracket, a column gap and a welded parenthesis each say what
    they are without help, and a block that says what it is should still be
    read when its markers are the thing that went missing.
    """
    if TIGHT_NOTE.match(lines[i].strip()) is None:
        return False
    want = 1
    sub_high = 0
    lead_in = False
    for raw in lines[i : i + 60]:
        stripped = raw.strip()
        if not stripped:
            continue
        following = TIGHT_NOTE.match(stripped)
        if following is None:
            return False
        n = int(following.group("n"))
        if sub_high:
            if n == sub_high + 1:  # the sub-list gets first refusal
                sub_high = n
                lead_in = stripped.endswith(":")
                continue
            if n == want:
                sub_high = 0  # the outer list picks up where it left off
            else:
                sub_high = max(sub_high, n)
                lead_in = stripped.endswith(":")
                continue
        if n != want:
            if n == 1 and lead_in:
                # A note that ends in a colon is introducing its own criteria,
                # and the list of them restarts at 1. Table 315-1's note 1 does
                # exactly that, which is why the run used to be read from the
                # sub-list and note 8 -- the one marked on the Quadplexes cell
                # -- was never reached. See `_bodies` for the same rule.
                sub_high = 1
                lead_in = stripped.endswith(":")
                continue
            return False
        want += 1
        lead_in = stripped.endswith(":")
        if want > 3:
            break
    else:
        return False
    return any(_bears_a_marker(lines[k]) for k in range(since, i))


def _cell_row(raw: str, stripped: str) -> bool:
    """Whether a line may be read as a row of use-table cells.

    A column gap settles it. Without one the line has to earn it, by carrying
    more than one permission code AND reading as a row rather than as a
    sentence -- because "P1" is a cell in a table and a design element in a
    paragraph, and the pattern cannot tell them apart on its own.
    """
    if GAP.search(raw):
        return True
    if LONE_CELL.match(stripped):
        return True
    if SENTENCE.search(stripped):
        return False
    return len(CELL_VOCAB.findall(stripped)) > 1


def _bears_a_marker(raw: str) -> bool:
    """Whether this line carries a footnote reference of any shape.

    Cross-references come out first: a note that ends "See Figure
    50.04.001-11[5]" is still the note, and reading its own figure number as a
    marker ends the block on the note that cites a figure.
    """
    if LONE_PAREN_CELL.match(raw.strip()) and PAREN_MARK.search(raw):
        # Asked before the citation strip, which eats "(CU)" and "(1)" alike
        # and leaves a bare "X" that carries nothing.
        return True
    stripped = PAREN_CITATION.sub("", CROSS_REFERENCE.sub("", raw.strip()))
    cells = [stripped, *(GAP.split(stripped) if GAP.search(stripped) else [])]
    if any(
        GLUED_MARKER.search(c.strip())
        or PAREN_MARKER.search(c.strip())
        or PAREN_LABEL_MARKER.search(c.strip())
        for c in cells
    ):
        return True
    if BRACKET_MARKER.search(stripped):
        return True
    return bool(CELL_MARKER.search(stripped) and _cell_row(raw, stripped))


def _flat(raw: str) -> str:
    """A line with its layout taken out, for comparing one to another."""
    return re.sub(r"\s+", " ", raw.strip())


def _bodies(lines: Sequence[str], start: int) -> tuple[list[Body], int]:
    """The numbered notes beginning at ``start``, and where they stop.

    What ends a block is the numbering, not the whitespace. A note wraps, and
    a chapter PDF breaks pages in the middle of one -- Gresham's corridor
    notes run "1. Temporary health hardship dwellings...", blank, page
    furniture, "2. Permitted only along the NE Glisan and NE 162nd Avenue
    corridors...". Ending at the blank loses that note, which happens to be
    one of the open questions in the corpus.

    So blanks and furniture are read through, and the block ends when the
    numbering restarts: the next table's note 1 cannot belong to this table's
    list. That is also what keeps two blocks from merging into one whose
    region covers neither table.
    """
    bodies: list[Body] = []
    texts: list[list[str]] = []
    #: The table's own column header, flattened, from the page this block sits
    #: at the foot of. A wide table reprints its header on every page it
    #: crosses -- Troutdale repeats "Dimensional Standard  LDR-1  LDR-2 ..."
    #: four lines below a note it interrupts -- and read as note text it lands
    #: in the middle of the sentence.
    #:
    #: Two things keep this off real prose. The line has to carry a column
    #: gap, so a heading that happens to be printed twice (a contents entry
    #: and the section itself) is not a candidate; and only the page above is
    #: looked at, because a document's contents list is hundreds of lines up.
    above = {
        flat
        for raw in lines[max(0, start - REPEAT_WINDOW) : start]
        if GAP.search(raw) and len(flat := _flat(raw)) >= 4
    }
    #: Where the last page stamp was seen, so the half of the running header
    #: that is shaped like a section heading can be told from one.
    stamped = -FRAME_REACH - 1
    #: The chapter that stamp named, where it named one. See `FRAME_HEAD_LEADING`.
    chapter = ""
    #: Whether the one allowed line of scope has been spent. See `NOTES_LEAD`.
    led = False
    #: Whether a legend has been stepped over. See `LEGEND_LINE`.
    legend = False
    #: Whether that legend arrived one part per line. See `LEGEND_CODE`.
    split = False
    highest = (-1, -1)
    #: Highest mark seen inside the sub-list a note introduced, or 0 when the
    #: reading is at the top level. See the restart branch below.
    sub_high = 0
    i = start
    while i < len(lines) and i - start < BLOCK_LIMIT:
        stripped = lines[i].strip()
        if (stamp := PAGE_STAMP.match(stripped)) is not None:
            stamped = i
            chapter = (stamp.groupdict().get("ident") or "").strip()
            i += 1
            continue
        if not stripped:
            i += 1
            continue
        lead = FRAME_HEAD_LEADING.match(stripped)
        furniture = bool(
            FURNITURE.search(stripped)
            or FRAME_HEAD_TRAILING.match(stripped)
            or (
                lead is not None
                and i - stamped <= FRAME_REACH
                and (not chapter or lead.group("n") == chapter)
            )
        )
        if furniture and not (legend and not bodies):
            # Furniture is stepped over anywhere except between a legend and
            # the note it is supposed to be standing in front of. Milwaukie
            # ends three of its legends with a section heading -- and a section
            # heading is furniture by the same rule that skips running headers
            # -- so the block walked out of the table it belonged to and read
            # the next subsection's "A." as a note. Nothing may come between.
            i += 1
            continue
        if ENDS_BLOCK.match(stripped) or (bodies and NOTES_HEAD.match(stripped)):
            break
        opening = (
            STACKED_NOTE.match(stripped)
            or HEADLESS_NOTE.match(stripped)
            or GLUED_PAREN_NOTE.match(stripped)
            or GLUED_NOTE.match(stripped)
            or BLOCK_NOTE.match(stripped)
            or STACKED_LETTER.match(stripped)
            or LETTER_NOTE.match(stripped)
        )
        if opening is not None:
            mark = opening.group("n")
            if sub_high and bodies:
                # Inside a note's own criteria. Two lists are interleaved and
                # both are ascending runs of small integers, so the question at
                # every line is which one this belongs to. The sub-list gets
                # first refusal: a mark exactly one above the highest sub-item
                # seen continues it, and that is the only thing separating
                # sub-item 2 from a note 2 the outer list is equally ready for.
                # Anything else that IS the number the outer list is waiting
                # for ends the sub-list -- 1, 2, 3, 4 then 2 is the outer list
                # picking up, and 1, 2 then 4 is as well.
                nxt = int(mark) if mark.isdigit() else None
                if nxt is not None and nxt == sub_high + 1:
                    sub_high = nxt
                    texts[-1].append(stripped)
                    i += 1
                    continue
                if nxt is not None and highest[0] == 0 and nxt == highest[1] + 1:
                    sub_high = 0
                else:
                    if nxt is not None:
                        sub_high = max(sub_high, nxt)
                    texts[-1].append(stripped)
                    i += 1
                    continue
            if bodies and mark.isalpha() != bodies[0].mark.isalpha():
                if bodies[0].mark.isalpha():
                    # Digits under letters are the lettered note's own
                    # sub-parts -- "E. Setbacks for residential garages are as
                    # follows: 1. Front loaded: minimum 20 feet." -- so they
                    # are read as more of E rather than as note 1 of a new
                    # list. Ending here lost every letter after E.
                    texts[-1].append(stripped)
                    i += 1
                    continue
                # Letters under digits are the next subsection. Troutdale's
                # "C. Townhouse dwellings:" heads the following table, and
                # swallowing it would both invent a note and cut the real one
                # above it short.
                break
            if bodies and _order(mark) <= highest:
                repeat = opening.groupdict().get("text") or ""
                if repeat and any(
                    b.mark == mark and b.text == repeat for b in bodies
                ):
                    # A caption cell spanning the grid prints its note once per
                    # column, and an HTML extraction puts each copy on its own
                    # line. Fairview's density note arrives seven times. Read
                    # as seven notes it is six bodies nobody points at, and a
                    # document that reports itself unreconciled for a reason
                    # that is not a reason.
                    i += 1
                    continue
                if mark == "1" and " ".join(texts[-1]).rstrip().endswith(":"):
                    # "1 The limited use is permitted subject to the following
                    # criteria:" and then a list that starts at 1 again. That
                    # restart is the note's own criteria, not the next table's
                    # note 1, and the colon is the codifier saying so. Read as
                    # a new list it cut Table 315-1's notes off after four of
                    # fifteen, and the two marked on the Quadplexes cell were
                    # among the eleven lost.
                    sub_high = 1
                    texts[-1].append(stripped)
                    i += 1
                    continue
                break
            text = opening.groupdict().get("text") or ""
            bodies.append(Body(doc="", line=i + 1, mark=mark, text=text))
            texts.append([text] if text else [])
            highest = _order(mark)
            i += 1
            continue
        if not bodies:
            if not led and NOTES_LEAD.search(stripped):
                # One sentence of scope between the heading and note 1. See
                # `NOTES_LEAD` for why it has to name the table to get this.
                led = True
                i += 1
                continue
            if not furniture and LEGEND_LINE.match(stripped):
                # A permission legend under the same heading as the notes.
                # Stepped over rather than believed: a legend alone still
                # yields no bodies and is still refused. See `LEGEND_LINE`.
                legend = True
                i += 1
                continue
            if not furniture and (
                split
                or (
                    LEGEND_CODE.match(stripped)
                    and _next_content(lines, i + 1) == "="
                )
            ):
                # The same legend with its code, its equals sign and its
                # definition on three lines. Entered only on that pair and
                # left at the first note, at anything that ends a block, or
                # at the page furniture the guard above stops skipping while
                # a legend is open. See `LEGEND_CODE`.
                legend = split = True
                i += 1
                continue
            # The first line under the heading is not numbered, so whatever
            # this heading announces, it is not a numbered notes block.
            break
        if _bears_a_marker(lines[i]):
            # A note wraps into prose, not into a footnoted table cell. This
            # is the next table starting, and reading it as the tail of the
            # last note would swallow its markers -- they sit inside a block
            # and blocks are where markers are not counted.
            break
        if _flat(stripped) in above:
            i += 1
            continue
        texts[-1].append(stripped)
        i += 1
    joined = [
        Body(doc=b.doc, line=b.line, mark=b.mark, text=" ".join(t))
        for b, t in zip(bodies, texts)
    ]
    return joined, i


def _markers(lines: Sequence[str], inside: Sequence[tuple[int, int]]) -> list[Marker]:
    """Every marker occurrence outside the notes blocks themselves.

    A note body carries its own number and would otherwise register as a
    marker for itself, which reconciles every block with itself and reports
    nothing.
    """
    out: list[Marker] = []
    for i, raw in enumerate(lines):
        if any(low <= i < high for low, high in inside):
            continue
        stripped = raw.strip()
        if not stripped:
            continue
        seen: set[str] = set()

        def add(mark: str, kind: str) -> None:
            if mark in seen:
                return
            seen.add(mark)
            out.append(Marker(doc="", line=i + 1, mark=mark, kind=kind, text=stripped))

        # Brackets identify themselves and are read anywhere on the line. The
        # rest are read per cell, because every one of them is a rule about
        # what a cell *ends* with.
        for m in BRACKET_MARKER.finditer(stripped):
            add(m.group("n"), "bracket")
        for m in SEE_NOTE.finditer(stripped):
            add(m.group("n"), "phrase")

        # A letter is read per token rather than per cell, because the run a
        # header states -- "Setbacks K, L, M" -- and the letters a data row
        # welds to its values sit at opposite ends of the layout.
        for token in stripped.split():
            got = LETTER_CELL.match(token) or LETTER_GLUED.match(token)
            if got is not None:
                for part in got.group("n").split(","):
                    add(part, "letter")
        planted = {
            (m.start("n") if m.group("n") else m.start("m"))
            for m in LANDSCAPE_LEVEL.finditer(stripped)
        }
        marked_cells = [
            m for m in CELL_MARKER.finditer(stripped) if m.start() not in planted
        ]
        lone = LONE_CELL.match(stripped) is not None
        if _cell_row(raw, stripped):
            for m in marked_cells:
                # "P7,8" is one cell carrying two notes, and reading only the
                # first leaves the second a body nobody points at.
                parts = [part.strip() for part in m.group("n").split(",")]
                # A line that is nothing but "P1" is a permission with a note
                # on it in one table and the identifier of row P1 in another --
                # Fairview numbers its menu of design options P1 through P8
                # exactly that way. A comma list settles it, since no row is
                # called P7,8; a single mark does not, so it is provisional and
                # `census` keeps it only where a note answers it. Reading those
                # as certain markers invented 43 orphans in two documents that
                # have no notes at all.
                kind = "lone" if lone and len(parts) == 1 else "cell"
                for part in parts:
                    add(part, kind)

        if LONE_PAREN_CELL.match(stripped):
            for mark in PAREN_MARK.findall(stripped):
                add(mark, "cell")

        # A label carries markers too -- "Residential density (maximum)1" --
        # and in an HTML extraction it has no column gap to be found by, since
        # every cell is its own line. So the whole line is read as a cell as
        # well as being split into them. The label rule earns that reach from
        # its own narrowness: the digits must follow a lowercase letter or a
        # closing parenthesis with nothing between. "Table 16.22.020-2" and
        # "MUR-M3" end in digits and match neither.
        cited = PAREN_CITATION.sub("", stripped)
        cells = [cited, *(GAP.split(cited) if GAP.search(raw) else [])]
        for cell in cells:
            cell = cell.strip()
            for kind, pattern in (
                ("glued", GLUED_MARKER),
                ("paren", PAREN_MARKER),
                ("paren", PAREN_LABEL_MARKER),
                ("label", LABEL_MARKER),
            ):
                found = pattern.search(cell)
                if found is None:
                    continue
                for part in found.group("n").split(","):
                    add(part.strip(), kind)
    return out


def census(text: str, *, layer: str = "", doc: str = "") -> Census:
    """The footnote census of one document."""
    lines = text.splitlines()
    blocks = _blocks(lines) + _declared(lines, doc)
    inside = tuple(span for b in blocks for span in b.covered)
    markers = [
        Marker(doc=doc, line=m.line, mark=m.mark, kind=m.kind, text=m.text)
        for m in _markers(lines, inside)
    ]
    blocks = tuple(
        Block(
            head=b.head,
            end=b.end,
            region=b.region,
            bodies=tuple(
                Body(doc=doc, line=body.line, mark=body.mark, text=body.text)
                for body in b.bodies
            ),
            spans=b.spans,
        )
        for b in blocks
    )

    # Provisional markers stand only where a note answers them. Done here
    # rather than in `_markers` because it is the blocks that decide it.
    markers = [
        Marker(doc=m.doc, line=m.line, mark=m.mark, kind="cell", text=m.text)
        if m.kind == "lone"
        else m
        for m in markers
        if m.kind not in PROVISIONAL
        or ((got := _governing(blocks, m.line - 1)) is not None and m.mark in got.marks)
    ]

    unbodied: list[Marker] = []
    unmarked: list[Body] = []
    claimed: set[int] = set()
    for block in blocks:
        low, high = block.region
        pointing = {m.mark for m in markers if low <= m.line - 1 < high}
        for body in block.bodies:
            if body.mark not in pointing:
                unmarked.append(body)
        claimed.update(range(low, high))
    for marker in markers:
        block = _governing(blocks, marker.line - 1)
        if block is None or marker.mark not in block.marks:
            unbodied.append(marker)

    return Census(
        layer=layer,
        doc=doc,
        blocks=blocks,
        markers=tuple(markers),
        unbodied=tuple(unbodied),
        unmarked=tuple(unmarked),
    )


def _governing(blocks: Sequence[Block], index: int) -> Block | None:
    """The block whose region contains this line, if any.

    A marker below the last block has no block at all -- its notes are in a
    document we do not hold, or in one the extractor lost.

    Regions used to be disjoint by construction, because each one ran from the
    previous block's end to this block's heading. A declared block's region is
    the table it names, which can sit anywhere -- including inside the sweep a
    later block claims by default. Where two regions contain the same line the
    tighter one wins, which is the one that had a reason for its bounds.
    """
    best: Block | None = None
    for block in blocks:
        low, high = block.region
        if low <= index < high and (best is None or high - low < best.region[1] - best.region[0]):
            best = block
    return best


def _stored(layer_id: str) -> list[Path]:
    """Documents on disk for a layer. Not what it declared -- what we have."""
    directory = DOCS / layer_id
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.txt") if p.is_file())


def _layers() -> list[str]:
    """Every layer with stored documents, as ``or/county/city``."""
    out = []
    for path in sorted(DOCS.rglob("*.txt")):
        layer = path.parent.relative_to(DOCS).as_posix()
        if layer not in out:
            out.append(layer)
    return out


def survey(layer: str | None = None) -> list[Census]:
    """The census of every stored document, or of one layer's."""
    layers = [layer] if layer else _layers()
    out: list[Census] = []
    for layer_id in layers:
        for path in _stored(layer_id):
            doc = f"{layer_id}/{path.name}"
            text = path.read_text(encoding="utf-8", errors="replace")
            out.append(census(text, layer=layer_id, doc=doc))
    return out


def render(rows: Sequence[Census], *, only_unreconciled: bool = False) -> str:
    """The census as text, for a terminal or a commit message."""
    shown = [r for r in rows if not only_unreconciled or not r.reconciled]
    width = max((len(r.doc) for r in shown), default=20)
    lines = []
    for row in shown:
        flag = "" if row.reconciled else "  UNRECONCILED"
        lines.append(
            f"{row.doc:<{width}}  {len(row.blocks):>2} blocks  "
            f"{len(row.markers):>3} markers  {len(row.bodies):>3} bodies  "
            f"{len(row.unbodied):>3} unbodied  {len(row.unmarked):>3} unmarked{flag}"
        )
    documents = len(rows)
    reconciled = sum(1 for r in rows if r.reconciled)
    with_notes = sum(1 for r in rows if r.total)
    lines.append("")
    lines.append(
        f"documents={documents}  with_footnotes={with_notes}  "
        f"reconciled={reconciled}  unreconciled={documents - reconciled}  "
        f"markers={sum(len(r.markers) for r in rows)}  "
        f"bodies={sum(len(r.bodies) for r in rows)}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    layer = None
    if "--layer" in args:
        layer = args[args.index("--layer") + 1]
    rows = survey(layer)
    print(render(rows, only_unreconciled="--unreconciled" in args))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "Block",
    "Body",
    "Census",
    "Marker",
    "census",
    "render",
    "survey",
]
