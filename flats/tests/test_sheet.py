"""Where on the printed page a number sits: the box a page-check card draws.

The box is a pointer, not a claim -- the reviewer looking at the page is the
check -- so what these tests hold to is that the pointer lands where a reader
would put their finger: on the number and not on a zone code that happens to
contain the same digit, under the right zone's heading when the table prints
one, and nowhere at all when the quoted line cannot be found. And that the
footnote markers printed on the number are read as markers, because the note
cards are built from them.

The PDFs are written by hand, a few text objects at known positions, so every
coordinate asserted here is one the test put there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.provenance import sheet as S


def _pdf(runs: list[tuple], *, rotate: int = 0) -> bytes:
    """A one-page US-letter PDF with text runs at (x, y, size, text), y up.

    On a page turned by ``rotate``, the text is set turned the other way, as
    a publisher does to print a landscape table on a portrait sheet: it reads
    left to right once the page is displayed. A run with a fifth field set
    true is printed a quarter turn on its own, reading up the page from
    (x, y): a column heading set vertically.
    """
    ops = []
    turn = {0: "1 0 0 1", 90: "0 1 -1 0", 180: "-1 0 0 -1", 270: "0 -1 1 0"}[rotate]
    for x, y, size, text, *up in runs:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        matrix = "0 1 -1 0" if up and up[0] else turn
        ops.append(f"BT /F1 {size} Tf {matrix} {x} {y} Tm ({escaped}) Tj ET")
    stream = "\n".join(ops).encode("latin-1")
    rotation = f" /Rotate {rotate}" if rotate else ""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
            f"{rotation} /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ).encode(),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


#: Gresham's setback table in miniature: zones as columns, a footnote on the
#: front setback, a marker on the row label and one in a column heading.
TABLE = [
    (72, 700, 11, "Table 4.0130 Development Requirements"),
    (220, 670, 11, "LDR-5"),
    (320, 670, 11, "LDR-7"),
    (420, 670, 11, "TR"),
    (72, 640, 11, "Minimum lot area"),
    (220, 640, 11, "5,000 sq. ft."),
    (320, 640, 11, "7,000 sq. ft."),
    (420, 640, 11, "5,000 sq. ft."),
    (72, 610, 11, "LDR-5"),
    (104, 614, 6, "4"),
    (220, 610, 11, "10 ft."),
    (252, 614, 6, "5"),
    (320, 610, 11, "8 ft."),
    (420, 610, 11, "20 ft."),
    (72, 400, 11, "5. Where an alley abuts the rear, the front may be 8 feet."),
]


@pytest.fixture
def book(tmp_path: Path) -> Path:
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(TABLE))
    return path


def _line(sheet: S.Sheet, text: str) -> S.Line:
    found = S.find(sheet, text)
    assert found is not None, f"fixture assumption: {text!r} is on the page"
    return found


def test_a_printed_line_is_found_from_the_stored_one_despite_its_spacing(book):
    sheet = S.read(book, 1)

    # pypdf's layout mode pads the columns with runs of spaces; PDFium reports
    # none. The two are the same line once the spacing is taken out.
    found = S.find(sheet, "  Minimum lot area         5,000 sq. ft.     7,000 sq. ft.     5,000 sq. ft.")

    assert found is not None
    assert found.words[0].text.startswith("Minimum")


def test_the_box_lands_on_the_number_and_not_on_a_zone_code_with_the_same_digit(book):
    sheet = S.read(book, 1)
    line = _line(sheet, "LDR-54 10 ft.5 8 ft. 20 ft.")

    spans = S.hits(line, 5, sheet.aspect)

    # "LDR-5" states no number; neither do the superscripts 4 and 5. Nothing
    # on this row is a five-foot standard.
    assert spans == []
    assert [line.words[a].text for a, _ in S.hits(line, 10, sheet.aspect)] == ["10"]


def test_a_repeated_number_is_narrowed_to_the_column_under_its_zone(book):
    sheet = S.read(book, 1)
    cited = [(3, 1, "Minimum lot area 5,000 sq. ft. 7,000 sq. ft. 5,000 sq. ft.", "", "")]

    for_tr = S.place({1: sheet}, cited, 5000, zone="TR")
    for_ldr5 = S.place({1: sheet}, cited, 5000, zone="LDR-5")

    assert for_tr.status == for_ldr5.status == "column"
    (tr_box, _), = for_tr.boxes[1]
    (ldr5_box, _), = for_ldr5.boxes[1]
    # TR's column is printed at x=420, LDR-5's at x=220, on a 612-wide page.
    assert tr_box.x0 > 0.6 > ldr5_box.x1


def test_without_a_heading_to_go_by_every_occurrence_is_boxed(book):
    sheet = S.read(book, 1)
    cited = [(3, 1, "Minimum lot area 5,000 sq. ft. 7,000 sq. ft. 5,000 sq. ft.", "", "")]

    placed = S.place({1: sheet}, cited, 5000, zone="(layer defaults)")

    assert placed.status == "several"
    assert len(placed.boxes[1]) == 2


def test_the_footnote_on_a_number_and_the_one_on_its_row_are_both_read(book):
    sheet = S.read(book, 1)
    cited = [(4, 1, "LDR-54 10 ft.5 8 ft. 20 ft.", "", "")]

    placed = S.place({1: sheet}, cited, 10, zone="LDR-5")

    assert placed.status == "boxed"
    assert {(m.mark, m.on) for m in placed.markers} == {("5", "number"), ("4", "row")}


def test_a_number_not_printed_as_a_numeral_marks_the_line_instead(book):
    sheet = S.read(book, 1)
    cited = [(4, 1, "LDR-54 10 ft.5 8 ft. 20 ft.", "", "")]

    placed = S.place({1: sheet}, cited, True)

    assert placed.status == "lines"
    assert [kind for _box, kind in placed.boxes[1]] == ["line"]


def test_a_line_that_is_not_on_the_page_draws_nothing(book):
    sheet = S.read(book, 1)
    cited = [(9, 1, "Maximum building height 35 feet", "", "")]

    placed = S.place({1: sheet}, cited, 35)

    # An unmarked page rather than a box somewhere plausible: a pointer on the
    # wrong cell looks like corroboration.
    assert placed.status == "unfound"
    assert placed.boxes == {}


def test_a_note_is_found_after_the_table_that_cites_it():
    text = ["Table", "LDR-5 10 ft.5", "Notes:", "4. See Section 10.0200.", "5. Where an alley abuts."]

    assert S.note_line(text, "5", 2) == 5
    assert S.note_line(text, "9", 2) is None


def test_a_note_is_not_a_section_number_or_a_cell_far_from_the_margin():
    """Gresham Table 4.0130's note 9 card showed a line of the height table
    (Steph 2026-10-20): "9.0600 Height Transition", printed 226 columns in, was
    read as note 9. Rivergrove's "(2)" indented under 5.050(a) was read as the
    "2" at the foot of the page (FOLLOWUPS 98)."""
    gresham = [
        "Townhouse   16 ft.   16 ft.",
        " " * 226 + "9.0600 for 9.0600 for 9.0600",
        "  1. 9.0600 Height Transition",
        "4.0131.",
        "9.                In the LDR-7, LDR-5, TR, and TLDR districts a reduction ...",
    ]
    assert S.note_line(gresham, "9", 1) == 5
    assert S.note_line(gresham, "4", 1) is None

    rivergrove = [
        "minimum lot size outside the Flood Hazard District is 10,000 square feet.",
        "            (a)       One single-family detached dwelling",
        "                        (2)       the dwelling shall have a pitched roof",
        "2             RLDO 5.010 is subject to an interpretation of the Planning Commission.",
    ]
    assert S.note_line(rivergrove, "2", 1) == 4


def test_a_numbered_row_label_inside_the_table_is_not_its_note():
    """Gresham Table 4.0130 numbers its sub-rows as its notes are numbered:
    the note 2 card showed "2. Width at building line: Corner lot" (Steph
    2026-10-20, check 630). The note is the sentence after "Notes:"."""
    text = [
        "B. Minimum Lot Size                5,000 sq. ft.",
        "  1. Width at building line: Interior lot",
        "        Townhouse                   16 ft.",
        "  2. Width at building line: Corner lot",
        "        Townhouse                   20 ft.         20 ft.",
        "  2. Minimum Street Frontage: Corner lots",
        "        Townhouse                   None           None",
        "2. Section 7.0400 Rear Height Limits",
        "Single Detached,",
        "Table 4.0130 Notes:",
        "1.  If a multi-family residential development abuts a",
        "parcel zoned R-10, R-8, R-6, there shall be a",
        "2.        Development of a Lot of Record which is less than the required minimum lot size may be",
        "4. Refer to Figure 70.15.10.2.3",
        "12.   Also see Section 10.1100 for shoreline height standards.",
    ]

    assert S.note_line(text, "2", 1) == 13
    # Short notes are notes: one that wraps (Oregon City), one with no stop
    # (Beaverton), one that is a sentence.
    assert S.note_line(text, "1", 3) == 11
    assert S.note_line(text, "4", 1) == 14
    assert S.note_line(text, "12", 1) == 15


def test_a_web_note_numbered_on_a_line_of_its_own_is_found():
    """Happy Valley 16.43 prints "NOTES: / 1 / Parking maximums are based on
    ..."; Oregon City prints a marker on a line of its own above its row,
    which is not the note."""
    happy_valley = [
        "1 per dwelling[3,5]",
        "1",
        "Townhouse 0 feet (attached)/5 feet",
        "NOTES:",
        "1",
        "Parking maximums are based on A and B Zone designations, pursuant to Metro rules.",
        "1.",
        "Required parking facilities may be located off-site.",
    ]
    assert S.note_line(happy_valley, "1", 1) == 5


def test_a_superscript_in_another_cell_of_the_column_is_not_the_columns_note(tmp_path: Path):
    """Gresham Table 4.0130 prints "12.1 units per / acre⁵" on MDR-24's minimum
    density. Two rows down, the maximum density card asked about note 5 as
    though the column heading carried it (Steph 2026-10-20). A marker on the
    heading itself still reaches every row under it."""

    def table(heading_mark: str | None) -> S.Sheet:
        runs = [
            (300, 700, 11, "MDR-24"),
            (72, 660, 11, "Minimum density"),
            (300, 660, 11, "12.1 units per"),
            (296, 646, 11, "acre"),
            (320, 650, 6, "5"),
            (72, 610, 11, "Maximum density"),
            (300, 610, 11, "24.2 units per"),
            (300, 596, 11, "acre"),
        ]
        if heading_mark:
            runs.append((316, 704, 6, heading_mark))
        path = tmp_path / f"book{heading_mark or ''}.pdf"
        path.write_bytes(_pdf(runs))
        return S.read(path, 1)

    plain = table(None)
    maximum = _line(plain, "Maximum density 24.2 units per")
    assert S.markers(plain, maximum, S.hits(maximum, 24.2, plain.aspect)) == []

    headed = table("3")
    maximum = _line(headed, "Maximum density 24.2 units per")
    assert [m.mark for m in S.markers(headed, maximum, S.hits(maximum, 24.2, headed.aspect))] == ["3"]


def test_boxes_follow_the_page_when_it_is_printed_turned(tmp_path: Path):
    """A landscape table on a portrait sheet turned 90 degrees."""
    path = tmp_path / "turned.pdf"
    path.write_bytes(_pdf([(300, 100, 11, "Maximum height 35 feet")], rotate=90))

    sheet = S.read(path, 1)
    line = _line(sheet, "Maximum height 35 feet")

    # Set at (300, 100) on the unturned sheet: a hundred points up from the
    # bottom edge, which the quarter turn clockwise makes the left edge.
    assert line.box.x0 == pytest.approx(100 / 792, abs=0.01)
    assert line.box.y0 == pytest.approx(1 - 300 / 612 - 11 / 612, abs=0.02)
    assert line.box.x1 - line.box.x0 > line.box.y1 - line.box.y0, "reads across, not down"
    assert sheet.aspect > 1, "a portrait page turned on its side displays wide"


@pytest.mark.parametrize(
    ("word", "number"),
    [
        ("5,000", 5000.0),
        ("10ft.", 10.0),
        ("2½", 2.5),
        ("Sixty", 60.0),
        ("fifty-eight", 58.0),
        ("50%", 50.0),
        ("LDR-5", None),
        ("R2.5", None),
    ],
)
def test_what_counts_as_a_printed_number(word, number):
    read_off = S.numeral(word)
    assert (read_off[0] if read_off else None) == number


def test_a_letter_spaced_numeral_is_read_whole_but_columns_are_not_joined():
    def w(text: str, x0: float) -> S.Word:
        return S.Word(text, S.Box(x0, 0.5, x0 + 0.01 * len(text), 0.515))

    # Oregon City prints "10,000" as "1 0 , 000": gaps narrower than a glyph.
    spaced = S.Line((w("1", 0.10), w("0", 0.113), w(",", 0.126), w("000", 0.139)))
    # A table row of single digits: gaps many glyphs wide.
    columns = S.Line((w("1", 0.10), w("0", 0.30)))

    assert S.hits(spaced, 10000) == [(0, 3)]
    assert S.hits(columns, 10) == []


def test_a_render_is_an_image_of_the_page(book, tmp_path, monkeypatch):
    monkeypatch.setattr(S, "PNG_CACHE", tmp_path / "sheets")

    image = S.render(book, 1)

    assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert S.render(book, 1) == image, "drawn once, then served from the cache"


def test_a_wrapped_cell_is_found_inside_the_printed_line_it_shares(tmp_path: Path):
    """Hillsboro: pypdf reads "Rear Yard 20 feet" as a line of its own; on the
    page it shares a line with the next cell's text."""
    path = tmp_path / "wrapped.pdf"
    path.write_bytes(
        _pdf([(72, 600, 11, "Rear Yard 20 feet"), (220, 600, 11, "waived for townhouses 10 feet")])
    )
    sheet = S.read(path, 1)

    line = S.find(sheet, " Rear Yard 20 feet")

    assert line is not None
    assert [w.text for w in line.words] == ["Rear", "Yard", "20", "feet"]
    placed = S.place({1: sheet}, [(1, 1, " Rear Yard 20 feet", "", "")], 20)
    assert placed.status == "boxed"


def _book(tmp_path: Path, pages: list[list[tuple[float, float, float, str]]]) -> Path:
    """A several-page book, by stitching one-page PDFs with pypdf."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for runs in pages:
        writer.add_page(PdfReader(BytesIO(_pdf(runs))).pages[0])
    path = tmp_path / "book.pdf"
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_a_page_footer_is_not_mistaken_for_part_of_a_rule(tmp_path: Path):
    """Oregon City: a citation across a page break quotes "266.5 Oregon City
    Supp. No. 48" between its two halves, and it was tinted as a rule."""
    pages = [
        [(72, 400, 11, f"Body text on page {n}"), (300, 40, 9, f"26{n}.5 Oregon City Supp. No. 48")]
        for n in (1, 2, 3)
    ]
    book = _book(tmp_path, pages)
    sheet = S.read(book, 2)
    running = S._running(book, 2)

    flagged = [" ".join(w.text for w in ln.words) for ln in sheet.lines if S._is_running(ln, running)]

    assert flagged == ["262.5 Oregon City Supp. No. 48"]


def test_a_repeated_table_heading_still_boxes_a_number_printed_on_it(tmp_path: Path):
    """A continued table repeats its heading at the same height on every page.
    The heading is dropped from the drawing -- unless the number is on it."""
    pages = [[(72, 760, 11, "Minimum lot area 5,000 sq. ft."), (72, 500, 11, f"Row {n}")] for n in (1, 2)]
    book = _book(tmp_path, pages)
    sheets = {2: S.read(book, 2)}
    running = S._running(book, 2)
    line = S.find(sheets[2], "Minimum lot area 5,000 sq. ft.")

    assert S._is_running(line, running), "fixture assumption: the heading repeats"
    assert S.hits(line, 5000, sheets[2].aspect), "so the number's own line is kept"


def test_pages_read_from_many_threads_at_once_all_come_back(book: Path):
    """PDFium is not thread-safe. The web app reads pages from a thread pool,
    and two requests opening books at once failed with "Data format error"
    on a good file (2026-10-01, the page check 500'd)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(i: int) -> int:
        return len(S._read.__wrapped__(book, 1, i).lines)

    with ThreadPoolExecutor(max_workers=8) as pool:
        counts = list(pool.map(one, range(200)))

    assert len(set(counts)) == 1 and counts[0] > 0


def test_a_sentence_printed_twice_is_told_apart_by_the_lines_around_it(tmp_path: Path):
    """Oregon City page 1039 prints one district's standards after another's,
    in the same words, and the line either side of each copy is the
    same "A." and "B.". Only the district heading above tells them apart, so
    the copy the text cites is found from the wider context, not guessed."""
    block = ["Dimensional standards apply.", "A.", "The maximum front setback is five feet.", "B."]
    runs = [(72, 720, 11, "Commercial District")]
    runs += [(72, 700 - 20 * k, 11, text) for k, text in enumerate(block)]
    runs += [(72, 560, 11, "Mixed-Use Downtown District")]
    runs += [(72, 540 - 20 * k, 11, text) for k, text in enumerate(block)]
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(runs))
    sheet = S.read(path, 1)
    lines = list(sheet.lines)

    found = S.find(
        sheet,
        "The maximum front setback is five feet.",
        before="Mixed-Use Downtown District\nDimensional standards apply.\nA.",
        after="B.",
    )

    assert found is not None
    above = " ".join(" ".join(w.text for w in ln.words) for ln in lines[: lines.index(found)])
    assert above.count("District") == 2, "the second copy, below both headings"
    # With only the nearest line to go by it is a tie, and a tie is not a guess.
    assert S.find(sheet, "The maximum front setback is five feet.", before="A.", after="B.") is None


#: Oregon City Table 17.08.040 in miniature: headings centred over columns
#: whose values are set flush left, and two of the three columns printed in a
#: smaller face on the same baseline.
CENTRED = [
    (72, 700, 11, "Standard"),
    (260, 700, 11, "R-10"),
    (380, 700, 11, "R-8"),
    (500, 700, 11, "R-6"),
    (72, 660, 11, "Maximum building lot coverage"),
    (220, 660, 8, "40%,"),
    (340, 660, 11, "40%,"),
    (460, 660, 8, "40%,"),
]


def test_a_smaller_face_on_the_baseline_is_not_a_footnote_marker(tmp_path: Path):
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(CENTRED))
    sheet = S.read(path, 1)
    row = _line(sheet, "Maximum building lot coverage 40%, 40%, 40%,")

    assert not [w.text for w in row.words if w.sup], "a percentage is never a note number"
    assert len(S.hits(row, 40, sheet.aspect)) == 3


def test_a_heading_centred_over_a_flush_left_column_still_claims_it(tmp_path: Path):
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(CENTRED))
    sheet = S.read(path, 1)
    row = _line(sheet, "Maximum building lot coverage 40%, 40%, 40%,")
    spans = S.hits(row, 40, sheet.aspect)

    for zone, n in (("R-10", 0), ("R-8", 1), ("R-6", 2)):
        assert S.under_heading(sheet, row, spans, zone) == [spans[n]], zone


def test_a_note_on_a_group_heading_reaches_the_rows_indented_under_it(tmp_path: Path):
    """Oregon City Table 17.12.040: "Minimum lot size¹" heads its own row and
    the sizes sit indented beneath it. A flat table's neighbouring standard,
    set flush with the row, lends it nothing."""
    runs = [
        (72, 700, 11, "Minimum lot size"),
        (160, 704, 6, "1"),
        (90, 680, 11, "Duplex"),
        (300, 680, 11, "4,000 square feet"),
        (90, 660, 11, "Triplex"),
        (300, 660, 11, "6,000 square feet"),
        (72, 620, 11, "Maximum density"),
        (160, 624, 6, "2"),
        (300, 620, 11, "N/A"),
        (72, 600, 11, "Minimum lot width"),
        (300, 600, 11, "50 feet"),
    ]
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(runs))
    sheet = S.read(path, 1)

    triplex = _line(sheet, "Triplex 6,000 square feet")
    width = _line(sheet, "Minimum lot width 50 feet")

    assert [m.mark for m in S.markers(sheet, triplex, S.hits(triplex, 6000, sheet.aspect))] == ["1"]
    assert S.markers(sheet, width, S.hits(width, 50, sheet.aspect)) == []


#: Gresham Table 4.0131 in miniature: zones down the side, standards across
#: the top, and one row stating 20 ft four times -- under Garage and under
#: each of the three street-side columns (Steph 2026-10-20).
SETBACKS = [
    (150, 700, 9, "Front"),
    (200, 700, 9, "Front"),
    (250, 700, 9, "Garage"),
    (300, 700, 9, "Interior"),
    (350, 700, 9, "Street"),
    (400, 700, 9, "Street"),
    (450, 700, 9, "Street"),
    (500, 700, 9, "Rear No"),
    (550, 700, 9, "Rear"),
    (150, 690, 9, "Wall"),
    (200, 690, 9, "Porch"),
    (300, 690, 9, "Side"),
    (350, 690, 9, "Side Wall"),
    (400, 690, 9, "Side"),
    (450, 690, 9, "Side"),
    (500, 690, 9, "Alley"),
    (550, 690, 9, "With"),
    (400, 680, 9, "Porch"),
    (450, 680, 9, "Garage"),
    (500, 680, 9, "Access"),
    (550, 680, 9, "Alley"),
    (40, 650, 9, "MDR-24"),
    (150, 650, 9, "10 ft."),
    (200, 650, 9, "10 ft."),
    (250, 650, 9, "20 ft."),
    (300, 650, 9, "NA"),
    (350, 650, 9, "20 ft."),
    (400, 650, 9, "20 ft."),
    (450, 650, 9, "20 ft."),
    (500, 650, 9, "15 ft."),
    (550, 650, 9, "NA"),
]


@pytest.fixture
def setbacks(tmp_path: Path) -> S.Sheet:
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(SETBACKS))
    return S.read(path, 1)


def _boxed_x(placed: S.Placed) -> list[float]:
    # The column each box starts in, to the 50 pt grid the fixture is set on.
    return [round(box.x0 * 612 / 50) * 50 for box, kind in placed.boxes[1] if kind == "value"]


def test_a_number_repeated_across_standards_is_boxed_under_its_own_heading(setbacks):
    row = _line(setbacks, "MDR-24 10 ft. 10 ft. 20 ft. NA 20 ft. 20 ft. 20 ft. 15 ft. NA")
    cited = [(1, 1, "MDR-24 10 ft. 10 ft. 20 ft. NA 20 ft. 20 ft. 20 ft. 15 ft. NA", "", "")]

    def at(value, field, when=()):
        return _boxed_x(S.place({1: setbacks}, cited, value, zone="MDR-24", field=field, when=when))

    # "Street Side Garage" is not the garage setback; "Front Porch" is not
    # the front wall; "Rear With Alley" is not the rear of a lot with none.
    assert len(_boxed_x(S.place({1: setbacks}, cited, 20, zone="MDR-24"))) == 4
    assert at(20, "setback_garage_entrance_ft") == [250]
    assert at(20, "setback_street_side_ft") == [350]
    assert at(10, "setback_front_ft") == [150]
    assert at(None, "setback_side_ft") == [300]
    assert at(None, "setback_rear_ft", ("abuts_alley",)) == [550]
    assert row.words[0].text == "MDR-24"


def test_a_heading_that_does_not_settle_it_leaves_every_hit_boxed(setbacks):
    cited = [(1, 1, "MDR-24 10 ft. 10 ft. 20 ft. NA 20 ft. 20 ft. 20 ft. 15 ft. NA", "", "")]

    # Nothing is headed "height"; a standard with no heading words is never
    # narrowed by a guess.
    assert len(_boxed_x(S.place({1: setbacks}, cited, 20, zone="MDR-24", field="max_height_ft"))) == 4
    assert len(_boxed_x(S.place({1: setbacks}, cited, 20, zone="MDR-24", field="max_far"))) == 4


def test_a_standard_held_as_not_applying_boxes_the_cell_that_says_so(setbacks):
    row = _line(setbacks, "MDR-24 10 ft. 10 ft. 20 ft. NA 20 ft. 20 ft. 20 ft. 15 ft. NA")

    assert [row.words[a].text for a, _ in S.hits(row, None, setbacks.aspect)] == ["NA", "NA"]


def test_a_lettered_heading_rows_marker_is_not_a_cell_note(tmp_path: Path):
    """Gresham Table 4.0130: "C. Minimum Net Density³" runs across every
    column, a line under the lot-size row -- its note is the density row's,
    though a cell's number sits in the column just above it."""
    runs = [
        (72, 700, 9, "All other uses"),
        (220, 700, 9, "5,000 sq. ft."),
        (72, 685, 9, "C. Minimum Net Density"),
        (230, 689, 5, "3"),
        (260, 685, 9, "(See definition of Net Density in Article 3)"),
        (72, 670, 9, "All uses"),
        (220, 670, 9, "6.22 units per"),
    ]
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(runs))
    sheet = S.read(path, 1)
    row = _line(sheet, "All uses 6.22 units per")

    assert "3" in [m.mark for m in S.markers(sheet, row, S.hits(row, 6.22, sheet.aspect))]


def test_a_note_on_a_heading_over_several_columns_reaches_each(tmp_path: Path):
    """Gresham Table 4.0131 heads Front Façade, Front Porch and Garage with
    one "FRONT²", its ² over the porch; the façade's and the garage's numbers
    carry note 2 too, the side yards under "SIDE" do not (Steph check 538)."""
    runs = [
        (174, 700, 9, "FRONT"),
        (199, 704, 5, "2"),
        (349, 700, 9, "SIDE"),
        (130, 685, 9, "Front"),
        (175, 685, 9, "Front"),
        (215, 685, 9, "Garage"),
        (255, 685, 9, "Interior"),
        (300, 685, 9, "Common"),
        (345, 685, 9, "Street"),
        (390, 685, 9, "Street"),
        (435, 685, 9, "Street"),
        (130, 675, 9, "Wall"),
        (175, 675, 9, "Porch"),
        (255, 675, 9, "Side"),
        (300, 675, 9, "Wall"),
        (72, 650, 9, "LDR-5"),
        (125, 650, 9, "10 ft."),
        (172, 650, 9, "8 ft."),
        (212, 650, 9, "20 ft."),
        (252, 650, 9, "5 ft."),
        (300, 650, 9, "NA"),
        (342, 650, 9, "11 ft."),
        (387, 650, 9, "12 ft."),
        (432, 650, 9, "21 ft."),
    ]
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(runs))
    sheet = S.read(path, 1)
    row = _line(sheet, "LDR-5 10 ft. 8 ft. 20 ft. 5 ft. NA 11 ft. 12 ft. 21 ft.")

    def marks(value):
        return [m.mark for m in S.markers(sheet, row, S.hits(row, value, sheet.aspect))]

    assert "2" in marks(10)
    assert "2" in marks(20)
    assert "2" not in marks(5)
    assert "2" not in marks(21)


#: Gresham Table 4.0430 in miniature: the corridor zones head the columns,
#: CMF's heading carries note 14, and the lot-size cell wraps over four lines
#: with its notes at the end (Steph 2026-10-20).
CORRIDOR = [
    (256, 700, 9, "CMF"),
    (276, 704, 5, "14"),
    (320, 700, 9, "CMU"),
    (72, 670, 9, "A. Minimum Lot Size"),
    (72, 655, 9, "Minimum lot size"),
    (220, 655, 9, "10,000 sq. ft. for"),
    (320, 655, 9, "None"),
    (220, 645, 9, "residential;"),
    (262, 645, 9, "none for"),
    (220, 635, 9, "mixed-use"),
    (258, 639, 5, "6,7"),
    (72, 615, 9, "B. Minimum Frontage"),
    (220, 615, 9, "100 ft. for"),
    (320, 615, 9, "None"),
    (220, 603, 9, "residential"),
    (268, 607, 5, "8,11"),
]


@pytest.fixture
def corridor(tmp_path: Path) -> S.Sheet:
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(CORRIDOR))
    return S.read(path, 1)


def test_a_note_on_the_zones_own_heading_is_read(corridor):
    row = _line(corridor, "Minimum lot size 10,000 sq. ft. for None")

    marks = {m.mark: m.on for m in S.markers(corridor, row, S.hits(row, 10000, corridor.aspect), "CMF")}

    # "CMF¹⁴" prints its marker right of the column's numbers; it is the
    # column's note all the same. CMU's card is not asked about it.
    assert marks.get("14") == "column"
    cmu = S.markers(corridor, row, S.hits(row, None, corridor.aspect)[-1:], "CMU")
    assert "14" not in [m.mark for m in cmu]


def test_notes_closing_a_wrapped_cell_are_the_numbers(corridor):
    row = _line(corridor, "Minimum lot size 10,000 sq. ft. for None")

    marks = [m.mark for m in S.markers(corridor, row, S.hits(row, 10000, corridor.aspect), "CMF")]

    # "6,7" ends the cell three lines down, past a "none" in the cell's own
    # sentence; "8,11" is the next row's frontage, and is printed past the
    # right edge of its number.
    assert {"6", "7"} <= set(marks)
    assert "8" not in marks
    frontage = _line(corridor, "B. Minimum Frontage 100 ft. for None")
    marks = [m.mark for m in S.markers(corridor, frontage, S.hits(frontage, 100, corridor.aspect), "CMF")]
    assert {"8", "11"} <= set(marks)


def test_a_note_in_the_next_cell_in_words_is_that_cells(tmp_path: Path):
    """Gresham Table 4.0130 corner frontage: MDR-12 "None", MDR-24 "Varies
    depending on access¹⁰". Note 10 is MDR-24's (Steph 2026-10-20)."""
    runs = [
        (72, 700, 9, "Townhouse"),
        (220, 700, 9, "None"),
        (300, 700, 9, "Varies"),
        (300, 690, 9, "depending on"),
        (300, 680, 9, "access"),
        (330, 684, 5, "10"),
        (380, 700, 9, "None"),
    ]
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(runs))
    sheet = S.read(path, 1)
    row = _line(sheet, "Townhouse None Varies None")

    assert "10" not in [m.mark for m in S.markers(sheet, row, S.hits(row, None, sheet.aspect)[:1], "MDR-12")]


def test_a_note_under_the_next_numbered_block_is_not_the_cells(tmp_path: Path):
    """Gresham Table 4.0130: MDR-24's interior frontage "45 ft." sits over
    "2. Minimum Street Frontage: Corner lots" and the corner cell "Varies
    depending on access¹⁰"; note 10 is the corner cell's (Steph check 646)."""
    runs = [
        (72, 700, 9, "All other uses"),
        (300, 700, 9, "45 ft."),
        (72, 689, 9, "2. Minimum Street Frontage: Corner lots"),
        (72, 678, 9, "Townhouse"),
        (300, 678, 9, "Varies"),
        (300, 667, 9, "depending on"),
        (300, 656, 9, "access"),
        (330, 660, 5, "10"),
    ]
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(runs))
    sheet = S.read(path, 1)
    row = _line(sheet, "All other uses 45 ft.")

    assert "10" not in [m.mark for m in S.markers(sheet, row, S.hits(row, 45, sheet.aspect), "MDR-24")]


def test_a_row_label_naming_several_zones_gives_each_its_own_note(tmp_path: Path):
    runs = [
        (72, 700, 9, "LDR-5"),
        (98, 704, 5, "4"),
        (110, 700, 9, "TLDR"),
        (134, 704, 5, "7"),
        (220, 700, 9, "15 ft."),
    ]
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(runs))
    sheet = S.read(path, 1)
    row = _line(sheet, "LDR-5 TLDR 15 ft.")
    spans = S.hits(row, 15, sheet.aspect)

    assert [m.mark for m in S.markers(sheet, row, spans, "TLDR")] == ["7"]
    assert [m.mark for m in S.markers(sheet, row, spans, "LDR-5")] == ["4"]
    # A card for a zone the label does not name keeps every marker.
    assert sorted(m.mark for m in S.markers(sheet, row, spans, "TR")) == ["4", "7"]


def test_a_zone_named_where_the_row_label_wraps_gets_its_own_note(tmp_path: Path):
    """Gresham Table 4.0131: "LDR-5⁴, LDR-7⁴," over "TLDR⁹, and TR⁴"; the
    TLDR card circled LDR-5's marker (Steph 2026-10-20)."""
    runs = [
        (72, 700, 9, "LDR-5"),
        (98, 704, 5, "4"),
        (110, 700, 9, "LDR-7"),
        (136, 704, 5, "4"),
        (220, 700, 9, "15 ft."),
        (72, 691, 9, "TLDR"),
        (96, 695, 5, "9"),
        (108, 691, 9, "and TR"),
        (140, 695, 5, "4"),
    ]
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(runs))
    sheet = S.read(path, 1)
    row = _line(sheet, "LDR-5 LDR-7 15 ft.")
    spans = S.hits(row, 15, sheet.aspect)

    assert [m.mark for m in S.markers(sheet, row, spans, "TLDR")] == ["9"]


#: Gresham Table 4.1415B (Pleasant Valley) in miniature: the zones down the
#: side, and every column heading printed turned, reading up the page. A
#: turned heading's letters stack one above another, so read as upright
#: lines they fell one or two to a line and no column could be named.
TURNED = [
    (72, 740, 9, "Table 4.1415B: Setbacks"),
    (160, 650, 9, "Front Wall", True),
    (210, 650, 9, "Front Porch", True),
    (260, 650, 9, "Interior Side", True),
    (310, 650, 9, "Street Side Wall", True),
    (360, 650, 9, "Rear No Alley", True),
    (410, 650, 9, "Rear With Alley", True),
    (72, 630, 9, "A. Minimum Setbacks"),
    (72, 615, 9, "Single Detached, Duplex, Triplex, Quadplex"),
    (72, 600, 9, "MDR-PV"),
    (150, 600, 9, "10 ft."),
    (200, 600, 9, "8 ft."),
    (250, 600, 9, "5 ft."),
    (300, 600, 9, "10 ft."),
    (350, 600, 9, "10 ft."),
    (400, 600, 9, "10 ft."),
    (72, 585, 9, "HDR-PV"),
    (150, 585, 9, "5 ft."),
    (200, 585, 9, "5 ft."),
    (250, 585, 9, "5 ft."),
    (300, 585, 9, "5 ft."),
    (350, 585, 9, "15 ft."),
    (400, 585, 9, "5 ft."),
    (72, 560, 9, "1. The minimum garage setback may be 5 feet when the garage is flush with an adjacent wall."),
]


@pytest.fixture
def turned(tmp_path: Path) -> S.Sheet:
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(TURNED))
    return S.read(path, 1)


def test_a_column_heading_printed_turned_still_names_its_column(turned):
    """Pleasant Valley and Springwater print their setback headings turned,
    so a card boxed every 10 ft. on the row and Steph could not tell which
    one was asked (FOLLOWUPS 103(b))."""
    cited = [(1, 1, "MDR-PV 10 ft. 8 ft. 5 ft. 10 ft. 10 ft. 10 ft.", "", "")]

    def at(value, field, when=()):
        return _boxed_x(S.place({1: turned}, cited, value, zone="MDR-PV", field=field, when=when))

    # The heading is read up the page, as printed, not left in the lines as
    # stray letters.
    assert [w.text for w in turned.turned][-3:] == ["Rear", "With", "Alley"]
    assert all(len(line.key) > 2 for line in turned.lines)
    assert at(10, "setback_front_ft") == [150]
    assert at(10, "setback_street_side_ft") == [300]
    assert at(10, "setback_rear_ft") == [350]
    assert at(10, "setback_rear_ft", ("alley_at_rear",)) == [400]
    # No heading names the standard: every hit stays boxed, never a guess.
    assert len(at(10, "max_height_ft")) == 4


def test_a_row_split_over_two_stored_lines_boxes_only_its_own_column(turned):
    """The text copy split Pleasant Valley's MDR-PV row in two, and the card
    quoting both halves boxed the street-side and rear 10 ft. beside the
    front one."""
    cited = [
        (1, 1, "MDR-PV 10 ft. 8 ft. 5 ft.", "", ""),
        (2, 1, "10 ft. 10 ft. 10 ft.", "", ""),
    ]
    placed = S.place({1: turned}, cited, 10, zone="MDR-PV", field="setback_front_ft")

    assert _boxed_x(placed) == [150]
    assert placed.status == "column"


#: Gresham Table 4.0131 in miniature: note 1 on the table's title, note 2 on
#: the "Front" column heading only, and the table's notes under it.
TITLED = [
    (72, 720, 10, "Table 4.0131 - Minimum Setbacks in Residential Districts"),
    (392, 724, 6, "1"),
    (200, 700, 9, "Front"),
    (225, 704, 5, "2"),
    (300, 700, 9, "Side"),
    (400, 700, 9, "Rear"),
    (72, 680, 9, "LDR-5"),
    (218, 680, 9, "10 ft."),
    (300, 680, 9, "5 ft."),
    (400, 680, 9, "15 ft."),
    *[(72, 668 - 12 * k, 9, f"Z{k}") for k in range(10)],
    (72, 540, 9, "TR"),
    (200, 540, 9, "11 ft."),
    (300, 540, 9, "6 ft."),
    (400, 540, 9, "16 ft."),
    (72, 500, 10, "Table 4.0131 Notes:"),
    (72, 485, 9, "1. Setbacks are measured from the property line."),
    (72, 470, 9, "LDR-5 lots platted before 1990 may keep 12 ft. rear yards."),
]


@pytest.fixture
def titled(tmp_path: Path) -> S.Sheet:
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(TITLED))
    return S.read(path, 1)


def test_a_note_on_the_tables_title_reaches_every_cell_and_a_columns_only_its_own(titled):
    """Steph 2026-10-21 (FOLLOWUPS 103(e)): a note on the table's title is
    asked of every number in the table; a note on a column heading only of
    that column's."""

    def marks(text, value):
        row = _line(titled, text)
        return {m.mark: m.on for m in S.markers(titled, row, S.hits(row, value, titled.aspect))}

    # Ten rows down and far left of the ¹, the rear and side setbacks carry
    # the title's note all the same.
    assert marks("TR 11 ft. 6 ft. 16 ft.", 16) == {"1": "title"}
    assert marks("TR 11 ft. 6 ft. 16 ft.", 6) == {"1": "title"}
    assert marks("LDR-5 10 ft. 5 ft. 15 ft.", 15) == {"1": "title"}
    # The column's note reaches its own column alone.
    assert marks("LDR-5 10 ft. 5 ft. 15 ft.", 10) == {"2": "column", "1": "title"}
    assert marks("LDR-5 10 ft. 5 ft. 15 ft.", 5) == {"1": "title"}
    # Under the table's notes, a number is not in the table.
    assert "1" not in marks("LDR-5 lots platted before 1990 may keep 12 ft. rear yards.", 12)


def test_a_table_continued_from_the_page_before_carries_its_titles_note(titled, tmp_path: Path):
    """The rows overleaf print no caption; the title is on the page before."""
    path = tmp_path / "overleaf.pdf"
    path.write_bytes(_pdf([(72, 700, 9, "MDR-12"), (200, 700, 9, "8 ft."), (300, 700, 9, "4 ft.")]))
    from dataclasses import replace

    overleaf = replace(S.read(path, 1), n=2)
    cited = [(40, 2, "MDR-12 8 ft. 4 ft.", "", "")]
    before = {1: _without_notes(titled)}

    placed = S.place({2: overleaf}, cited, 4, earlier=before.get)

    (title,) = [m for m in placed.markers if m.on == "title"]
    assert (title.mark, title.page) == ("1", 1)
    # Without the page before, nothing is guessed.
    assert S.place({2: overleaf}, cited, 4).markers == []
    # Past the table's notes, the page before's title no longer reaches.
    assert S.place({2: overleaf}, cited, 4, earlier={1: titled}.get).markers == []


def _without_notes(sheet: S.Sheet) -> S.Sheet:
    from dataclasses import replace

    return replace(sheet, lines=tuple(ln for ln in sheet.lines if ln.box.y0 < 0.35))


def test_a_sentence_naming_a_table_is_not_its_title():
    def line(*texts):
        return S.Line(tuple(S.Word(t, S.Box(0.1 * k, 0.1, 0.1 * k + 0.05, 0.12)) for k, t in enumerate(texts)))

    assert S._caption(line("Table", "4.0131", "-", "Minimum", "Setbacks")) == "title"
    assert S._caption(line("TABLE", "4.1130", "CONTINUED")) == "title"
    assert S._caption(line("Table", "4.1508", "(continued):", "Minimum", "Setbacks")) == "title"
    assert S._caption(line("Table", "4.0130", "Notes:")) == "notes"
    assert S._caption(line("Table", "4.1311", "summarizes", "the", "density")) == ""
    assert S._caption(line("Tables", "show")) == ""


def test_a_column_headings_note_reaches_a_row_far_below_it(tmp_path: Path):
    """Gresham Table 4.0130 runs a dozen rows and more under its zone
    headings; a note on a heading reached only the rows within a few lines of
    it. The table's heading band, from its title to its first row, is read
    whatever the distance -- and a note printed in another cell of the
    column is still that cell's."""
    runs = [
        (72, 740, 10, "Table 4.0130: Development Requirements"),
        (220, 720, 9, "Detached"),
        (300, 720, 9, "Attached"),
        (338, 724, 5, "3"),
        *[(72, 700 - 12 * k, 9, f"Standard {k}") for k in range(14)],
        (72, 520, 9, "Maximum height"),
        (220, 520, 9, "35 ft."),
        (330, 520, 9, "35 ft."),
        (72, 500, 9, "Lot coverage"),
        (330, 500, 9, "40%"),
        (348, 504, 5, "8"),
        (72, 488, 9, "Rear setback"),
        (220, 488, 9, "15 ft."),
        (330, 488, 9, "15 ft."),
    ]
    path = tmp_path / "book.pdf"
    path.write_bytes(_pdf(runs))
    sheet = S.read(path, 1)
    row = _line(sheet, "Maximum height 35 ft. 35 ft.")

    tr, ldr5 = S.hits(row, 35, sheet.aspect)[-1:], S.hits(row, 35, sheet.aspect)[:1]
    assert {m.mark: m.on for m in S.markers(sheet, row, tr, "")}.get("3") == "column"
    assert "3" not in [m.mark for m in S.markers(sheet, row, ldr5, "")]
    rear = _line(sheet, "Rear setback 15 ft. 15 ft.")
    marks = [m.mark for m in S.markers(sheet, rear, S.hits(rear, 15, sheet.aspect)[-1:], "")]
    assert "3" in marks and "8" not in marks


def _no_fetch(url: str) -> bytes:
    raise AssertionError(f"the test reads the cached book only, not {url}")


def test_gresham_aisle_width_note_reaches_the_ninety_degree_rows():
    """Gresham Table 9.0825A heads its aisle columns "Width¹" fifteen lines
    above the 90-degree rows the aisle widths are read from, and prints the 1
    just past the right edge of the numbers under it. Note 1 sets the aisle
    for emergency access at 20 and 24 feet; the cards never asked it."""
    from flats.provenance import books
    from flats.provenance.store import ProvenanceStore

    store = ProvenanceStore()
    document = "or/multnomah/gresham/9.0800.parking.txt"
    try:
        url = store.load(document).url
    except Exception:
        pytest.skip("Gresham's parking chapter is not stored")
    if not books.cache_path(url).is_file():
        pytest.skip("Gresham's parking book is not cached")
    ranges = [(66, 70), (302, 302), (319, 327), (340, 343)]
    for field, value in (("parking_aisle_two_way_ft", 24), ("parking_aisle_one_way_ft", 23)):
        placed = S.locate(store, document, ranges, value, field=field, get=_no_fetch)
        assert {m.mark: m.on for m in placed.markers} == {"1": "column"}, field
    # The stall columns carry no note.
    placed = S.locate(store, document, ranges, 8.5, field="parking_stall_width_ft", get=_no_fetch)
    assert placed.markers == []
