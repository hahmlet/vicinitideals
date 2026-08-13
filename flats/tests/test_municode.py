"""The platform that answers every question the same way until you ask a better one.

Municode was two thirds of the remaining corpus and unreadable: the library
renders in JavaScript, so a plain fetch sees a 6KB frame whatever it asks for. The
way out is two measurements — membership lives in a public client registry, and
the adopted code is a public PDF behind a publication id — and the tests here
defend the parts of that where being wrong is silent.

No network. A test that depends on Municode being up tests Municode.
"""

from __future__ import annotations

import json

import pytest

from flats.provenance import municode as mod
from flats.provenance.municode import Publication, aliases, code_block, publication, resolve
from flats.provenance.sources import Authority, FetchFailed, Fetched

pytestmark = pytest.mark.unit

CLIENTS = json.dumps(
    [
        {"ClientName": "Wilsonville", "ClientID": 4976},
        {"ClientName": "Washington County", "ClientID": 4800},
    ]
).encode()

CONTENT = json.dumps(
    {
        "codes": [
            {
                "productName": "Code of Ordinances",
                "productId": 15875,
                "publicationId": 1951,
                "latestUpdatedDate": "2026-03-05T13:33:54",
            }
        ]
    }
).encode()


@pytest.fixture(autouse=True)
def _no_cached_registry():
    mod.clients.cache_clear()
    yield
    mod.clients.cache_clear()


def _api(monkeypatch, **routes: bytes | None) -> None:
    def fake(url: str, **kw):
        for fragment, body in routes.items():
            if fragment.replace("_", "/") in url or fragment in url:
                if body is None:
                    raise FetchFailed("nope", (("plain", 503),))
                return Fetched(body, "plain", 200, Authority.official)
        raise FetchFailed("nope", (("plain", 404),))

    monkeypatch.setattr(mod, "fetch", fake)


# --- membership is asked, not guessed ----------------------------------


def test_a_client_resolves_to_its_publication(monkeypatch) -> None:
    _api(monkeypatch, Clients=CLIENTS, ClientContent=CONTENT)

    pub = publication("Wilsonville")

    assert pub is not None
    assert pub.publication_id == 1951
    assert pub.url == "https://api.municode.com/PublicationPdfDownload/1951"


def test_a_city_the_registry_does_not_list_has_no_publication(monkeypatch) -> None:
    # Gresham's library URL answers 200 with the same frame as everyone else's.
    # Only the registry can say it is not a client.
    _api(monkeypatch, Clients=CLIENTS, ClientContent=CONTENT)

    assert publication("Gresham") is None


def test_an_unreadable_registry_is_not_an_empty_one(monkeypatch) -> None:
    _api(monkeypatch, Clients=None)

    assert mod.clients("OR") is None


def test_unincorporated_land_is_filed_under_its_county() -> None:
    assert "washington county" in aliases("Washington Unincorporated")


def test_a_client_with_no_publication_yields_nothing(monkeypatch) -> None:
    # Listed, and its code is not published as a downloadable publication.
    # Returning the client anyway would declare a URL that serves nothing.
    _api(monkeypatch, Clients=CLIENTS, ClientContent=json.dumps({"codes": []}).encode())

    assert publication("Wilsonville") is None


# --- the hop -----------------------------------------------------------


def test_a_publication_endpoint_resolves_to_the_signed_blob() -> None:
    body = b'"https://mcclibrary.blob.core.usgovcloudapi.net/x/1951/Final.pdf?sig=abc"'

    assert resolve("https://api.municode.com/PublicationPdfDownload/1951", body).endswith("sig=abc")


def test_any_other_url_is_not_this_module_s_business() -> None:
    # sources.fetch asks about every URL it handles. Claiming one that is not
    # Municode's would swallow a real document.
    assert resolve("https://www.portland.gov/code/33.110.pdf", b'"https://elsewhere"') is None


def test_a_body_that_is_not_a_url_is_not_followed() -> None:
    assert resolve("https://api.municode.com/PublicationPdfDownload/1951", b"<html>") is None
    assert resolve("https://api.municode.com/PublicationPdfDownload/1951", b'"ftp://x"') is None


def test_the_declared_url_is_the_stable_one_not_the_signed_one() -> None:
    # The blob signature expires in minutes. A citation pointing at it would
    # stop working before anybody followed it.
    pub = Publication("Wilsonville", 4976, "Code of Ordinances", 15875, 1951, "2026-03-05")

    assert "?" not in pub.url
    assert pub.url.startswith("https://api.municode.com/")


# --- what gets pasted into a layer file --------------------------------


def test_the_code_block_is_valid_yaml_naming_the_document() -> None:
    import yaml

    pub = Publication("Wilsonville", 4976, "Code of Ordinances", 15875, 1951, "2026-03-05T13:33")
    parsed = yaml.safe_load(code_block(pub))

    assert parsed["code"][0]["url"] == pub.url
    assert parsed["code"][0]["id"] == "municode-code"


def test_the_code_block_records_why_the_url_is_that_one() -> None:
    # The comment is the knowledge: the obvious URL — the library page — is a
    # JavaScript frame, and nothing else in the repo would say so.
    pub = Publication("Wilsonville", 4976, "Code of Ordinances", 15875, 1951, "2026-03-05")

    assert "renders in JavaScript" in code_block(pub)
