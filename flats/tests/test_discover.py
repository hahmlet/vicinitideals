"""Telling "no code here" apart from "we could not read it".

Sixteen of nineteen jurisdictions are stuck because nobody has found the URL that
serves their ordinance. Discovery guesses those URLs from the city's name, and
the value of the guess is entirely in how the answer is reported: a 404 means the
name guess was wrong, a 403 means the fetcher is, and a JavaScript shell means
the code is there and invisible. Three different next actions, and a tool that
collapses them into "failed" sends the reader hunting for the wrong fix.

No network here. Every test drives the classifier or a stubbed fetch, because a
test that depends on a codifier being up tests the codifier.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from flats.provenance import discover as mod
from flats.provenance import municode as mc
from flats.provenance.discover import (
    Candidate,
    classify,
    main,
    name_forms,
    probe,
    undeclared,
    urls_for,
)
from flats.provenance.sources import Authority, FetchFailed, Fetched

pytestmark = pytest.mark.unit

INDEX = b"<html><body><h2>Title 19 Zoning</h2><p>Chapter 19.30</p></body></html>" + b"x" * 5000
SHELL = b'<html ng-app="mcc.library_desktop"><head><title>Municode Library</title></head></html>'


# --- the name is the guess ---------------------------------------------


def test_a_two_word_city_gets_every_spelling_a_codifier_might_use() -> None:
    # "WestLinn" to one codifier, "west_linn" to another. A wrong spelling
    # answers 404, which reads as "this city has no code" unless the shapes are
    # right.
    forms = name_forms("West Linn")

    assert forms["camel"] == "WestLinn"
    assert forms["snake"] == "west_linn"
    assert forms["lower"] == "westlinn"
    assert forms["dash"] == "west-linn"


def test_punctuation_in_a_label_does_not_reach_a_url() -> None:
    assert name_forms("St. Helens")["camel"] == "StHelens"


def test_every_platform_is_tried() -> None:
    platforms = [p for p, _ in urls_for("Gresham")]

    assert platforms == [name for name, _, _ in mod.PLATFORMS]


# --- what answered -----------------------------------------------------


def test_a_page_naming_chapters_is_an_index() -> None:
    assert classify(INDEX) == "index"


def test_a_javascript_shell_is_not_an_index() -> None:
    # The finding this encodes: Municode's empty frame carries "Municode
    # Library" in its <title>, so a classifier that asks about code words first
    # calls it a code index. A lead that is not there costs more than no lead.
    assert classify(SHELL) == "shell"


def test_a_shell_is_still_worth_following() -> None:
    # The code IS there. It needs a rendered fetch or the platform's API, which
    # is a different job than finding a URL — but it is not a dead end, and
    # reporting it as one would drop a real jurisdiction.
    assert Candidate("l", "municode", "u", "shell").worth_following


def test_a_short_empty_page_is_not_an_index() -> None:
    assert classify(b"<html><body></body></html>") == "shell"


# --- the two ways a fetch ends -----------------------------------------


def _fails(*attempts) -> FetchFailed:
    return FetchFailed("nope", attempts)


def test_a_404_means_the_guess_was_wrong_not_that_we_are_blocked(monkeypatch) -> None:
    monkeypatch.setattr(mod, "fetch", lambda url, **kw: (_ for _ in ()).throw(_fails(("plain", 404))))

    assert probe("l", "qcode", "https://qcode.us/codes/gresham/").verdict == "missing"


def test_a_403_everywhere_means_the_fetcher_is_the_problem(monkeypatch) -> None:
    # §15's whole point: a blocked host looks exactly like an absent one in a
    # log, and treating them the same quietly narrows the project to
    # jurisdictions with friendly web servers.
    monkeypatch.setattr(
        mod,
        "fetch",
        lambda url, **kw: (_ for _ in ()).throw(_fails(("plain", 403), ("chrome124", 403))),
    )

    assert probe("l", "codepublishing", "https://x.gov/").verdict == "blocked"


def test_a_transport_error_with_no_status_is_blocked_not_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        mod, "fetch", lambda url, **kw: (_ for _ in ()).throw(_fails(("plain", "ConnectTimeout")))
    )

    assert probe("l", "amlegal", "https://x.gov/").verdict == "blocked"


def test_a_probe_records_what_it_took_to_get_the_page(monkeypatch) -> None:
    monkeypatch.setattr(
        mod, "fetch", lambda url, **kw: Fetched(INDEX, "chrome124", 200, Authority.official)
    )

    got = probe("l", "codepublishing", "https://www.codepublishing.com/OR/Fairview/")

    assert got.verdict == "index"
    assert got.strategy == "chrome124"
    assert got.authority is Authority.official


def test_a_probe_never_raises(monkeypatch) -> None:
    # A sweep across sixteen cities that dies on the first blocked host reports
    # one city instead of sixteen.
    monkeypatch.setattr(mod, "fetch", lambda url, **kw: (_ for _ in ()).throw(_fails()))

    assert probe("l", "qcode", "https://x.gov/").verdict == "blocked"


# --- ordering and scope ------------------------------------------------


def test_leads_sort_ahead_of_dead_ends(monkeypatch) -> None:
    answers = {
        "codepublishing": _fails(("plain", 404)),
        "api.municode.com": Fetched(b"[]", "plain", 200, Authority.official),
        "amlegal": _fails(("plain", 403)),
        "qcode": Fetched(INDEX, "plain", 200, Authority.official),
    }

    def fake(url: str, **kw):
        for platform, answer in answers.items():
            if platform in url:
                if isinstance(answer, FetchFailed):
                    raise answer
                return answer
        raise AssertionError(url)

    monkeypatch.setattr(mod, "fetch", fake)

    # An empty registry is a real answer: Municode does not publish this city.
    assert [c.verdict for c in mod.discover("l", "Gresham")] == [
        "index",
        "blocked",
        "missing",
        "missing",
    ]


@pytest.fixture()
def rules(tmp_path: Path) -> Path:
    root = tmp_path / "jurisdictions" / "or" / "multnomah"
    root.mkdir(parents=True)
    (root.parent / "_state.yaml").write_text(
        yaml.safe_dump({"label": "Oregon", "kind": "state", "zones": {}}), encoding="utf-8"
    )
    (root / "gresham.yaml").write_text(
        yaml.safe_dump({"label": "Gresham", "kind": "city", "zones": {"LDR": {"max_units": 4}}}),
        encoding="utf-8",
    )
    (root / "portland.yaml").write_text(
        yaml.safe_dump(
            {
                "label": "Portland",
                "kind": "city",
                "code": [{"id": "33.110", "url": "https://www.portland.gov/code/33.110.pdf"}],
                "zones": {"R5": {"max_units": 4}},
            }
        ),
        encoding="utf-8",
    )
    (root / "empty.yaml").write_text(
        yaml.safe_dump({"label": "Empty", "kind": "city", "zones": {}}), encoding="utf-8"
    )
    return tmp_path / "jurisdictions"


def test_a_jurisdiction_that_declares_its_code_is_not_hunted_for(rules: Path) -> None:
    assert [layer for layer, _ in undeclared(rules)] == ["or/multnomah/gresham"]


def test_a_jurisdiction_with_no_zones_is_not_hunted_for_either(rules: Path) -> None:
    # Nothing to source yet. It is stuck one rung lower, and sending somebody
    # to find its code URL is work that cannot be used.
    assert "or/multnomah/empty" not in [layer for layer, _ in undeclared(rules)]


def test_the_sweep_says_how_many_have_a_lead(rules: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        mod, "fetch", lambda url, **kw: Fetched(INDEX, "plain", 200, Authority.official)
    )

    assert main(["--all", "--rules", str(rules)]) == 0
    assert "1/1 jurisdiction(s) have a lead to follow" in capsys.readouterr().out


def test_the_sweep_says_a_lead_is_not_a_citation(rules: Path, monkeypatch, capsys) -> None:
    # An index URL in a `code:` block would fetch the front door of the code and
    # quote lines from a table of contents.
    monkeypatch.setattr(
        mod, "fetch", lambda url, **kw: Fetched(INDEX, "plain", 200, Authority.official)
    )
    main(["--all", "--rules", str(rules)])

    assert "pick the zoning chapter" in capsys.readouterr().out


def test_nothing_to_discover_is_an_error_not_a_silent_zero(rules: Path) -> None:
    assert main(["--layer", "or/multnomah/portland", "--rules", str(rules)]) == 1


# --- Municode is asked, not probed -------------------------------------
#
# Membership and the document both live in flats.provenance.municode; what is
# defended here is only that discovery reports its answer honestly.


CLIENTS = json.dumps([{"ClientName": "Wilsonville", "ClientID": 4976}]).encode()
CONTENT = json.dumps(
    {"codes": [{"productName": "Code of Ordinances", "productId": 1, "publicationId": 1951}]}
).encode()


@pytest.fixture(autouse=True)
def _no_cached_registry():
    mc.clients.cache_clear()
    yield
    mc.clients.cache_clear()


def _registry(monkeypatch, body: bytes | None) -> None:
    def fake(url: str, **kw):
        if body is None:
            raise FetchFailed("nope", (("plain", 503),))
        if "ClientContent" in url:
            return Fetched(CONTENT, "plain", 200, Authority.official)
        if "api.municode.com" in url:
            return Fetched(body, "plain", 200, Authority.official)
        raise FetchFailed("nope", (("plain", 404),))

    monkeypatch.setattr(mc, "fetch", fake)
    monkeypatch.setattr(mod, "fetch", fake)


def test_a_city_on_the_registry_is_a_real_lead(monkeypatch) -> None:
    _registry(monkeypatch, CLIENTS)

    got = mod.municode("l", "Wilsonville")

    assert got.verdict == "index"
    assert got.url == "https://api.municode.com/PublicationPdfDownload/1951"


def test_a_city_not_on_the_registry_is_missing_not_a_shell(monkeypatch) -> None:
    # The measurement this defends: library.municode.com returns the same 6KB
    # frame for every path, client or not — the "not found" renders in
    # JavaScript. Probing the URL reported a Municode lead for Gresham, which
    # is not a Municode client at all.
    _registry(monkeypatch, CLIENTS)

    assert mod.municode("l", "Gresham").verdict == "missing"


def test_an_empty_registry_is_an_answer_not_a_failure(monkeypatch) -> None:
    _registry(monkeypatch, b"[]")

    assert mod.municode("l", "Wilsonville").verdict == "missing"


def test_an_unreadable_registry_is_blocked_not_an_empty_platform(monkeypatch) -> None:
    # "Municode publishes nobody here" and "we could not read the list" are
    # opposite conclusions, and the second must never be reported as the first.
    _registry(monkeypatch, None)

    assert mod.municode("l", "Wilsonville").verdict == "blocked"
