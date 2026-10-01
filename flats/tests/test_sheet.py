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


def _pdf(runs: list[tuple[float, float, float, str]], *, rotate: int = 0) -> bytes:
    """A one-page US-letter PDF with text runs at (x, y, size, text), y up.

    On a page turned by ``rotate``, the text is set turned the other way, as
    a publisher does to print a landscape table on a portrait sheet: it reads
    left to right once the page is displayed.
    """
    ops = []
    turn = {0: "1 0 0 1", 90: "0 1 -1 0", 180: "-1 0 0 -1", 270: "0 -1 1 0"}[rotate]
    for x, y, size, text in runs:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"BT /F1 {size} Tf {turn} {x} {y} Tm ({escaped}) Tj ET")
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
