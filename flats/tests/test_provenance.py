"""The provenance store and the staleness it derives.

Two contracts carry the weight here.

*A citation must resolve.* A quote that points at nothing reads as evidence
while proving nothing, so every malformed or out-of-range reference raises
rather than returning an empty string.

*Losing the source is not the same as the source changing.* A codifier's site
timing out must never demote a county's rule set — that would be an outage we
inflicted on ourselves, dressed up as diligence.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from flats.provenance import (
    EVIDENCE_MISSING,
    SOURCE_CHANGED,
    Document,
    ProvenanceError,
    ProvenanceStore,
    apply_staleness,
    check_drift,
    parse_quote,
    sha256,
)
from flats.rules.model import Layer, Provenance, Status, Value, Zone

pytestmark = pytest.mark.unit

RETRIEVED = date(2026, 8, 12)
TEXT = "\n".join(f"line {i}" for i in range(1, 11))
PORTLAND = "or/multnomah/portland/33.110.txt"


@pytest.fixture
def store(tmp_path: Path) -> ProvenanceStore:
    s = ProvenanceStore(tmp_path)
    s.save(PORTLAND, url="https://example.gov/33/110", text=TEXT, retrieved=RETRIEVED)
    return s


def value(
    name: str,
    val: object,
    *,
    status: Status = Status.draft,
    quote: str | None = None,
) -> Value:
    review = {"reviewer": "sjk", "reviewed": RETRIEVED} if status is Status.verified else {}
    return Value(
        name=name,
        value=val,
        status=status,
        prov=Provenance(
            cite="PCC 33.110.220",
            url="https://example.gov/33/110",
            retrieved=RETRIEVED,
            quote=quote,
        ),
        **review,
    )


def layer(**values: Value) -> dict[str, Layer]:
    return {
        "or/multnomah/portland": Layer(
            layer="or/multnomah/portland",
            kind="city",
            label="Portland",
            zones={"R5": Zone(zone="R5", values=values)},
        )
    }


def r5(layers: dict[str, Layer], field: str = "setback_front_ft") -> Value:
    return layers["or/multnomah/portland"].zones["R5"].values[field]


# --- parsing a citation ----------------------------------------------


def test_a_bare_path_means_the_whole_document() -> None:
    ref = parse_quote(PORTLAND)

    assert ref.path == PORTLAND
    assert ref.whole_document


def test_a_single_line_reference_spans_that_line_only() -> None:
    ref = parse_quote("a.txt#L42")

    assert (ref.start, ref.end) == (42, 42)


def test_a_line_range_parses_with_or_without_the_second_L() -> None:
    # Both spellings appear in the wild: tooling writes #L42-L48, and people
    # citing by hand tend to drop the second L.
    assert parse_quote("a.txt#L42-L48") == parse_quote("a.txt#L42-48")


def test_a_citation_may_name_more_than_one_span() -> None:
    """A number stated in a table row and qualified by a footnote three lines
    down is cited from both places or from neither, and 133 values in the
    corpus were written the first way while the store could only read the
    second -- so they reported as evidence that does not resolve."""
    ref = parse_quote("a.txt#L132-L133,L138")
    assert ref.spans == ((132, 133), (138, 138))
    assert (ref.start, ref.end) == (132, 138)
    assert ref.numbers == (132, 133, 138)


def test_spans_that_double_back_are_refused() -> None:
    for bad in ("a.txt#L10,L5", "a.txt#L10-L20,L15"):
        with pytest.raises(ProvenanceError, match="ascend"):
            parse_quote(bad)


def test_a_multi_span_quote_reads_only_the_lines_it_names() -> None:
    doc = Document(
        path="a.txt",
        url="https://example.test/a",
        retrieved=date(2026, 1, 1),
        sha256="",
        text="\n".join(f"line {n}" for n in range(1, 11)),
    )
    ref = parse_quote("a.txt#L2-L3,L7")
    assert doc.lines(ref) == "line 2\nline 3\nline 7"
    assert doc.numbered(ref) == ((2, "line 2"), (3, "line 3"), (7, "line 7"))


def test_surrounding_whitespace_is_forgiven() -> None:
    assert parse_quote("  a.txt#L1-L2  ").path == "a.txt"


@pytest.mark.parametrize(
    "bad",
    [
        "#L4",  # no path
        "a.txt#L0",  # line numbers are 1-based
        "a.txt#L10-L5",  # inverted
        "",
    ],
)
def test_an_unresolvable_reference_is_refused(bad: str) -> None:
    # Failing loudly is the point: a citation nobody can follow is worse than no
    # citation, because it looks like proof.
    with pytest.raises(ProvenanceError):
        parse_quote(bad)


# --- quoting text -----------------------------------------------------


def test_a_span_returns_exactly_those_lines() -> None:
    doc = Document("a.txt", "https://x", RETRIEVED, sha256(TEXT), TEXT)

    assert doc.lines(parse_quote("a.txt#L3-L5")) == "line 3\nline 4\nline 5"


def test_no_span_returns_the_whole_document() -> None:
    doc = Document("a.txt", "https://x", RETRIEVED, sha256(TEXT), TEXT)

    assert doc.lines(parse_quote("a.txt")) == TEXT


def test_a_span_past_the_end_is_an_error_not_a_truncation() -> None:
    # Silently returning three lines when the citation asked for eight would let
    # a section renumbering pass review unnoticed.
    doc = Document("a.txt", "https://x", RETRIEVED, sha256(TEXT), TEXT)

    with pytest.raises(ProvenanceError, match="document has 10"):
        doc.lines(parse_quote("a.txt#L8-L14"))


# --- hashing ----------------------------------------------------------


def test_line_endings_do_not_count_as_an_amendment() -> None:
    # A codifier serving CRLF one day and LF the next would otherwise flip every
    # value on the page to stale for nothing.
    assert sha256("a\r\nb\r\n") == sha256("a\nb\n")


def test_changed_words_change_the_hash() -> None:
    assert sha256("setback 10 feet") != sha256("setback 15 feet")


# --- store round trip -------------------------------------------------


def test_saving_writes_text_and_a_sidecar(store: ProvenanceStore) -> None:
    assert store.exists(PORTLAND)

    meta = json.loads(store.meta_path(PORTLAND).read_text(encoding="utf-8"))
    assert meta["url"] == "https://example.gov/33/110"
    assert meta["retrieved"] == "2026-08-12"
    assert meta["sha256"] == sha256(TEXT)


def test_loading_returns_what_was_saved(store: ProvenanceStore) -> None:
    doc = store.load(PORTLAND)

    assert doc.text == TEXT
    assert doc.retrieved == RETRIEVED
    assert doc.sha256 == sha256(TEXT)


def test_crlf_is_normalized_on_disk(tmp_path: Path) -> None:
    # So a Windows fetch and a Linux fetch of the same page produce byte-equal
    # files, and a line number in a citation means the same thing on both.
    s = ProvenanceStore(tmp_path)
    s.save("a.txt", url="https://x", text="a\r\nb\r\nc", retrieved=RETRIEVED)

    assert s.text_path("a.txt").read_bytes() == b"a\nb\nc"


def test_citing_text_nobody_fetched_is_an_error(store: ProvenanceStore) -> None:
    with pytest.raises(ProvenanceError, match="fetch it before citing it"):
        store.load("or/multnomah/gresham/10.0400.txt")


def test_text_without_a_sidecar_has_no_provable_hash(tmp_path: Path) -> None:
    s = ProvenanceStore(tmp_path)
    (tmp_path / "loose.txt").write_text("some words", encoding="utf-8")

    with pytest.raises(ProvenanceError, match="no sidecar"):
        s.load("loose.txt")


def test_documents_lists_sources_not_sidecars(store: ProvenanceStore) -> None:
    store.save("or/multnomah/gresham/10.0400.txt", url="https://y", text="x", retrieved=RETRIEVED)

    assert store.documents() == ["or/multnomah/gresham/10.0400.txt", PORTLAND]


def test_a_quote_resolves_end_to_end(store: ProvenanceStore) -> None:
    assert store.quote(f"{PORTLAND}#L2-L3") == "line 2\nline 3"


# --- integrity --------------------------------------------------------


def test_an_untouched_store_reports_nothing_tampered(store: ProvenanceStore) -> None:
    assert store.tampered() == []


def test_editing_stored_text_is_detected(store: ProvenanceStore) -> None:
    # Evidence that can be edited without leaving a trace is not evidence.
    store.text_path(PORTLAND).write_text(TEXT.replace("line 4", "line four"), encoding="utf-8")

    assert store.tampered() == [PORTLAND]


# --- drift ------------------------------------------------------------


def test_an_unchanged_source_does_not_invalidate(store: ProvenanceStore) -> None:
    [result] = check_drift(store, lambda url: TEXT)

    assert result.state == "unchanged"
    assert not result.invalidates


def test_a_changed_source_invalidates(store: ProvenanceStore) -> None:
    [result] = check_drift(store, lambda url: TEXT + "\nline 11, as amended")

    assert result.state == "changed"
    assert result.invalidates
    assert result.stored_sha != result.fetched_sha


def test_an_unreachable_source_is_reported_but_does_not_invalidate(
    store: ProvenanceStore,
) -> None:
    # The load-bearing one. A timeout is not evidence the law changed, and
    # demoting a whole county because a website was down would be an outage we
    # inflicted on ourselves. It is still reported, so the gap stays visible.
    def boom(url: str) -> str:
        raise TimeoutError("connection timed out")

    [result] = check_drift(store, boom)

    assert result.state == "unreachable"
    assert not result.invalidates
    assert "TimeoutError" in result.detail


def test_a_source_that_vanished_from_the_store_invalidates(store: ProvenanceStore) -> None:
    results = check_drift(store, lambda url: TEXT, paths=["or/multnomah/gone.txt"])

    assert [r.state for r in results] == ["missing"]
    assert results[0].invalidates


def test_paths_restricts_the_check(store: ProvenanceStore) -> None:
    store.save("or/multnomah/gresham/10.0400.txt", url="https://y", text="x", retrieved=RETRIEVED)

    results = check_drift(store, lambda url: TEXT, paths=[PORTLAND])

    assert [r.path for r in results] == [PORTLAND]


# --- staleness --------------------------------------------------------


def test_a_verified_value_citing_a_changed_document_goes_stale() -> None:
    layers = layer(
        setback_front_ft=value("setback_front_ft", 10, status=Status.verified, quote="a.txt#L4-L6")
    )

    out, report = apply_staleness(layers, ["a.txt"], require_quote=False)

    assert r5(out).status is Status.stale
    assert r5(out).value == 10, "demotion changes trust, never the number"
    assert [(r.zone, r.field, r.reason) for r in report] == [
        ("R5", "setback_front_ft", SOURCE_CHANGED)
    ]


def test_an_unchanged_document_leaves_everything_alone() -> None:
    layers = layer(
        setback_front_ft=value("setback_front_ft", 10, status=Status.verified, quote="a.txt#L4-L6")
    )

    out, report = apply_staleness(layers, ["b.txt"], require_quote=False)

    assert r5(out).status is Status.verified
    assert report == []


def test_a_draft_is_not_demoted() -> None:
    # It was never trusted. Marking it stale would blur why it is untrusted and
    # bury it in a queue meant for values that used to be good.
    layers = layer(setback_front_ft=value("setback_front_ft", 10, quote="a.txt#L4-L6"))

    out, report = apply_staleness(layers, ["a.txt"])

    assert r5(out).status is Status.draft
    assert report == []


def test_verified_without_a_quote_is_not_really_verified() -> None:
    # A verification nobody can re-check is an assertion. Six months later
    # nobody can tell the difference between that and a guess.
    layers = layer(setback_front_ft=value("setback_front_ft", 10, status=Status.verified))

    out, report = apply_staleness(layers)

    assert r5(out).status is Status.stale
    assert [r.reason for r in report] == [EVIDENCE_MISSING]


def test_the_quote_requirement_can_be_relaxed() -> None:
    # Needed while the store is still being backfilled; the coverage ledger is
    # what keeps the exemption from becoming permanent.
    layers = layer(setback_front_ft=value("setback_front_ft", 10, status=Status.verified))

    out, report = apply_staleness(layers, require_quote=False)

    assert r5(out).status is Status.verified
    assert report == []


def test_a_quote_that_does_not_resolve_in_the_store_is_evidence_missing(
    store: ProvenanceStore,
) -> None:
    layers = layer(
        setback_front_ft=value(
            "setback_front_ft", 10, status=Status.verified, quote="or/nowhere/99.txt#L1"
        )
    )

    _, report = apply_staleness(layers, store=store)

    assert [r.reason for r in report] == [EVIDENCE_MISSING]
    assert "fetch it before citing it" in report[0].detail


def test_a_resolvable_quote_survives_the_store_check(store: ProvenanceStore) -> None:
    layers = layer(
        setback_front_ft=value(
            "setback_front_ft", 10, status=Status.verified, quote=f"{PORTLAND}#L2-L3"
        )
    )

    _, report = apply_staleness(layers, store=store)

    assert report == []


def test_layer_defaults_are_demoted_too() -> None:
    # State preemption lives in defaults. A stale parking cap there is exactly
    # the value that must not be trusted silently.
    layers = {
        "or": Layer(
            layer="or",
            kind="state",
            label="Oregon",
            defaults={
                "parking_min_per_unit": value(
                    "parking_min_per_unit", 1.0, status=Status.verified, quote="oar.txt#L9"
                )
            },
        )
    }

    out, report = apply_staleness(layers, ["oar.txt"], require_quote=False)

    assert out["or"].defaults["parking_min_per_unit"].status is Status.stale
    assert [(r.layer, r.zone, r.field) for r in report] == [
        ("or", "defaults", "parking_min_per_unit")
    ]


def test_the_input_layers_are_left_untouched() -> None:
    # Staleness is derived on every load. If it mutated in place, a second call
    # would see a different world than the first and the answer would depend on
    # call order.
    layers = layer(
        setback_front_ft=value("setback_front_ft", 10, status=Status.verified, quote="a.txt#L4-L6")
    )

    apply_staleness(layers, ["a.txt"], require_quote=False)

    assert r5(layers).status is Status.verified


def test_the_report_is_ordered_for_a_review_queue() -> None:
    layers = {
        "or/multnomah/portland": Layer(
            layer="or/multnomah/portland",
            kind="city",
            label="Portland",
            zones={
                "R5": Zone(
                    zone="R5",
                    values={
                        "setback_side_ft": value(
                            "setback_side_ft", 5, status=Status.verified, quote="a.txt#L1"
                        ),
                        "setback_front_ft": value(
                            "setback_front_ft", 10, status=Status.verified, quote="a.txt#L2"
                        ),
                    },
                ),
                "R2.5": Zone(
                    zone="R2.5",
                    values={
                        "max_height_ft": value(
                            "max_height_ft", 35, status=Status.verified, quote="a.txt#L3"
                        )
                    },
                ),
            },
        )
    }

    _, report = apply_staleness(layers, ["a.txt"], require_quote=False)

    assert [(r.zone, r.field) for r in report] == [
        ("R2.5", "max_height_ft"),
        ("R5", "setback_front_ft"),
        ("R5", "setback_side_ft"),
    ]


def test_drift_and_staleness_compose(store: ProvenanceStore) -> None:
    # The whole loop, as the loader will run it: re-fetch, keep the results that
    # invalidate, demote whatever cited them.
    layers = layer(
        setback_front_ft=value(
            "setback_front_ft", 10, status=Status.verified, quote=f"{PORTLAND}#L2"
        )
    )

    drift = check_drift(store, lambda url: TEXT + "\nas amended 2026")
    out, report = apply_staleness(layers, [d.path for d in drift if d.invalidates], store=store)

    assert r5(out).status is Status.stale
    assert [r.reason for r in report] == [SOURCE_CHANGED]


def test_a_citation_cannot_reach_outside_the_store(tmp_path) -> None:
    # A quote reference is text an encoder wrote, and since the review pages
    # it is also text a browser sent. Joining it onto the store root is a
    # filesystem read, so the join is checked rather than trusted.
    from flats.provenance.store import ProvenanceError, ProvenanceStore

    store = ProvenanceStore(tmp_path)

    for escape in ("../secrets.txt", "or/../../secrets.txt", "/etc/passwd"):
        with pytest.raises(ProvenanceError):
            store.text_path(escape)

    assert store.text_path("or/multnomah/portland/33.110.txt").is_relative_to(tmp_path)
