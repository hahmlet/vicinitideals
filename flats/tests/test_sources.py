"""Where code text comes from, and whether it can back a signature.

Both halves were discovered the same way: six real fetches across five
codifiers produced one usable document, and the provenance store accepted all
six. Three of these tests encode a failure that actually happened.
"""

from __future__ import annotations

import pytest

from flats.provenance import sources
from flats.provenance.sources import (
    Authority,
    FetchFailed,
    authority_for,
    fetch,
    host_of,
)

pytestmark = pytest.mark.unit


# --- reading a host ----------------------------------------------------


def test_the_host_comes_out_bare() -> None:
    assert host_of("https://www.portland.gov/code/33/100s/110") == "portland.gov"
    assert host_of("http://example.gov:8080/x") == "example.gov"


def test_a_codifier_subdomain_still_resolves_to_the_codifier() -> None:
    # Municode serves every city from library.municode.com; matching only the
    # exact host would classify all of them as unknown.
    assert authority_for("https://library.municode.com/or/troutdale/codes") is Authority.official


# --- who may back a citation -------------------------------------------


def test_a_city_publishing_its_own_code_is_official() -> None:
    assert authority_for("https://www.greshamoregon.gov/dc-section-4.0100.pdf") is Authority.official


def test_a_contracted_codifier_is_official() -> None:
    # A city publishing through Code Publishing is publishing the ordinance.
    # The host is not the author, but it is the publisher of record.
    assert authority_for("https://www.codepublishing.com/OR/Fairview/") is Authority.official


def test_an_aggregator_is_a_lead_not_evidence() -> None:
    # Quadfit cited one of these for West Linn's standards. It is a third
    # party's reading of the code, and signing it would mean a reviewer
    # certified the law by reading somebody's summary of it.
    where = authority_for("https://www.zoneomics.com/code/west-linn-OR/chapter_10")

    assert where is Authority.aggregator
    assert not where.may_verify


def test_an_unrecognised_host_is_not_promoted_to_official() -> None:
    # A host earns official status by somebody naming it, on purpose.
    assert authority_for("https://randomblog.example/or-zoning") is Authority.unknown
    assert not Authority.unknown.may_verify


def test_only_official_sources_may_be_signed() -> None:
    assert Authority.official.may_verify
    assert not Authority.aggregator.may_verify


# --- the strategy ladder -----------------------------------------------


def test_the_cheapest_strategy_that_answers_wins(monkeypatch) -> None:
    monkeypatch.setattr(sources, "_plain", lambda _u: (b"<html>ok</html>", 200))
    got = fetch("https://portland.gov/x")

    assert got.strategy == "plain"
    assert not got.impersonated


def test_a_403_is_not_an_answer(monkeypatch) -> None:
    # Code Publishing and eCode360 both return 403 to a plain client. Treating
    # that as "unavailable" would quietly narrow the project to jurisdictions
    # with friendly web servers, and it would look like a coverage gap rather
    # than a fetching bug.
    monkeypatch.setattr(sources, "_plain", lambda _u: (b"denied", 403))
    monkeypatch.setattr(sources, "_impersonated", lambda _u, t: (b"<html>code</html>", 200))
    got = fetch("https://www.codepublishing.com/OR/Fairview/")

    assert got.impersonated
    assert got.content == b"<html>code</html>"


def test_a_transport_failure_is_one_more_strategy_down_not_the_end(monkeypatch) -> None:
    def explode(_url):
        raise ConnectionError("reset")

    monkeypatch.setattr(sources, "_plain", explode)
    monkeypatch.setattr(sources, "_impersonated", lambda _u, t: (b"<html>code</html>", 200))

    assert fetch("https://ecode360.com/43076426").impersonated


def test_an_empty_200_does_not_count_as_success(monkeypatch) -> None:
    # Municode answers 200 with nothing and renders in JavaScript. An empty
    # body was stored as "the code" before this.
    monkeypatch.setattr(sources, "_plain", lambda _u: (b"", 200))
    monkeypatch.setattr(sources, "_impersonated", lambda _u, t: (b"", 200))

    with pytest.raises(FetchFailed):
        fetch("https://library.municode.com/or/troutdale/codes")


def test_exhausting_the_ladder_names_what_was_tried(monkeypatch) -> None:
    monkeypatch.setattr(sources, "_plain", lambda _u: (b"denied", 403))
    monkeypatch.setattr(sources, "_impersonated", lambda _u, t: (b"denied", 403))

    with pytest.raises(FetchFailed, match="403"):
        fetch("https://example.gov/x")


def test_the_strategy_used_is_reported_not_hidden(monkeypatch) -> None:
    # A document that needed impersonation is a fact about the source worth
    # keeping: it is the first thing to check when a refresh starts failing.
    monkeypatch.setattr(sources, "_plain", lambda _u: (b"denied", 403))
    monkeypatch.setattr(sources, "_impersonated", lambda _u, t: (b"<html>x</html>", 200))
    got = fetch("https://example.gov/x", strategies=("plain", "chrome124"))

    assert got.strategy == "chrome124"
    assert got.status == 200
