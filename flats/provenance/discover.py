"""Finding the address of a jurisdiction's code, for the sixteen that have none.

The readiness ladder's loudest finding is that most jurisdictions are not
under-reviewed — they are **undeclared**. Sixteen of nineteen have zones encoded
and no `code:` block, which means nothing can fetch their text, so nothing can be
quoted, so nothing can ever be signed. That backlog does not move by reviewing
harder.

Hunting those URLs by hand is the same search sixteen times: Oregon cities publish
through a short list of codifiers, each with a URL shape that follows from the
city's name. This runs that search.

**A hit is a lead, not a source.** What comes back is a code *index* — the front
door of a city's municipal code — and a `code:` entry needs the chapter that
carries the zoning standards. Naming the platform and proving it answers is the
part that was costing an afternoon per city; picking the chapter still requires
reading the table of contents, and the module says so rather than guessing a
chapter number into a rule file.

Four verdicts, because they are four different next actions:

``index``    answered, and reads like a code index — the lead to follow
``shell``    answered with a JavaScript shell (Municode). The code is there and
             a plain fetch will never see it; needs a rendered fetch or the API
``missing``  answered 404, or the name guess was wrong
``blocked``  every impersonation strategy refused. A fetching problem, not a
             coverage one, and §15 exists because those look identical in a log

Run::

    python -m flats.provenance.discover --layer or/clackamas/happy-valley
    python -m flats.provenance.discover --all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from flats.provenance.sources import Authority, FetchFailed, authority_for, fetch
from flats.rules.loader import CONFIG_ROOT, load_rules

#: Where Oregon cities actually publish. Each entry is a URL shape and the name
#: form it wants — the same city is `WestLinn` to one codifier and `west_linn`
#: to another, and getting that wrong reads as "no code exists" rather than as a
#: bad guess.
PLATFORMS: tuple[tuple[str, str, str], ...] = (
    ("codepublishing", "https://www.codepublishing.com/OR/{camel}/", "camel"),
    ("amlegal", "https://codelibrary.amlegal.com/codes/{lower}/latest/overview", "lower"),
    ("qcode", "https://qcode.us/codes/{lower}/", "lower"),
)

#: Municode is asked a different question, and the reason is a measurement.
#: `library.municode.com/or/<anything>/codes/code_of_ordinances` returns the same
#: 6,095-byte frame whether the city is a client or not — the "not found" is
#: rendered in JavaScript. Probing the URL therefore reports a lead for every
#: city on earth. Its client registry is a plain JSON list and answers the
#: question the URL cannot: is this jurisdiction actually on this platform?
MUNICODE_CLIENTS = "https://api.municode.com/Clients/stateAbbr?stateAbbr={state}"
MUNICODE_LIBRARY = "https://library.municode.com/{state_lower}/{snake}/codes/code_of_ordinances"

#: Words a municipal code index has and a 404 page does not. Deliberately dull:
#: anything cleverer starts making judgements about content, and this is only
#: asked to tell a code index from an error page. "title" is absent on purpose —
#: every HTML page in the world carries a <title> tag, and matching it called
#: Municode's empty frame a code index.
_INDEX_WORDS = ("chapter", "municipal code", "ordinance", "zoning", "article i")

#: Municode serves an empty frame and renders in JavaScript. Recognising that
#: specifically matters — reported as `missing` it would look like a city with
#: no code, when in fact the code is there and the fetcher cannot see it.
_SHELL_MARKERS = ("ng-app", "municode", "__NEXT_DATA__", "app-root")

_PUNCT = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class Candidate:
    """One platform's answer about one jurisdiction."""

    layer: str
    platform: str
    url: str
    verdict: str
    status: int = 0
    strategy: str = ""
    authority: Authority = Authority.unknown
    size: int = 0
    #: Anything the reader needs that the URL does not carry — a client id, the
    #: fact that the content still needs a rendered fetch.
    note: str = ""

    @property
    def worth_following(self) -> bool:
        return self.verdict in ("index", "shell")

    def line(self) -> str:
        detail = self.note or (f"{self.strategy}, {self.size:,}b" if self.strategy else "")
        return f"  {self.verdict:8} {self.platform:15} {self.url}" + (f"  [{detail}]" if detail else "")


def name_forms(label: str) -> dict[str, str]:
    """The spellings a codifier might use for one city's name."""
    words = _PUNCT.sub(" ", label.lower()).split()
    return {
        "camel": "".join(w.capitalize() for w in words),
        "snake": "_".join(words),
        "lower": "".join(words),
        "dash": "-".join(words),
    }


def urls_for(label: str) -> list[tuple[str, str]]:
    """(platform, url) for every shape worth trying for this jurisdiction."""
    forms = name_forms(label)
    return [(platform, shape.format(**forms)) for platform, shape, _ in PLATFORMS]


def classify(body: bytes) -> str:
    """What kind of page answered."""
    text = body.decode("utf-8", errors="replace").lower()
    if any(marker in text for marker in _SHELL_MARKERS):
        # Checked first, and this order is the finding: a shell's <title> and
        # meta tags carry code words, so asking "does it mention chapters?"
        # first calls an empty JavaScript frame a code index — and a lead that
        # is not there costs more than no lead.
        return "shell"
    if any(word in text for word in _INDEX_WORDS):
        return "index"
    # Answered, and says nothing either way. A short body with no code words in
    # it is not a code index, whatever the status line claimed.
    return "shell" if len(body) < 4000 else "missing"


def probe(layer: str, platform: str, url: str) -> Candidate:
    """Ask one platform about one jurisdiction, and never raise."""
    try:
        got = fetch(url)
    except FetchFailed as failed:
        # A 404 says the guessed name is wrong; a 403 says the fetcher is. Both
        # end here, and calling them both "blocked" would send somebody hunting
        # for an impersonation fix for a city that simply uses another codifier.
        verdict = "missing" if 404 in failed.statuses else "blocked"
        return Candidate(
            layer,
            platform,
            url,
            verdict,
            status=next(iter(failed.statuses), 0),
            authority=authority_for(url),
        )
    return Candidate(
        layer,
        platform,
        url,
        classify(got.content),
        status=got.status,
        strategy=got.strategy,
        authority=got.authority,
        size=len(got.content),
    )


@lru_cache(maxsize=8)
def municode_clients(state: str = "OR") -> tuple[tuple[str, int], ...] | None:
    """Every jurisdiction Municode publishes in one state, from its own registry.

    Cached because a sweep asks once per city and the answer is one list.
    ``None`` means the registry could not be read — distinct from an empty list,
    which would mean the platform publishes nobody here. Those are opposite
    conclusions and the second must never stand in for the first.
    """
    try:
        got = fetch(MUNICODE_CLIENTS.format(state=state.upper()), strategies=("plain",))
        listed = json.loads(got.content)
    except (FetchFailed, ValueError):
        return None
    return tuple(
        (str(entry.get("ClientName", "")), int(entry.get("ClientID", 0)))
        for entry in listed
        if entry.get("ClientName")
    )


def _key(name: str) -> str:
    return _PUNCT.sub("", name.lower())


def municode(layer: str, label: str, *, state: str = "OR") -> Candidate:
    """Ask Municode's registry whether it publishes this jurisdiction."""
    clients = municode_clients(state)
    url = MUNICODE_LIBRARY.format(state_lower=state.lower(), **name_forms(label))
    if clients is None:
        return Candidate(layer, "municode", url, "blocked", authority=authority_for(url))
    wanted = {_key(label)} | {_key(alias) for alias in aliases(label)}
    for name, client_id in clients:
        if _key(name) in wanted:
            return Candidate(
                layer,
                "municode",
                MUNICODE_LIBRARY.format(state_lower=state.lower(), **name_forms(name)),
                "index",
                status=200,
                strategy="registry",
                authority=authority_for(url),
                note=f"client {client_id}; content renders in JavaScript",
            )
    return Candidate(layer, "municode", url, "missing", authority=authority_for(url))


def aliases(label: str) -> tuple[str, ...]:
    """Other names a codifier might file this jurisdiction under.

    Unincorporated county land is encoded as its own jurisdiction because that
    is how the zoning works, but a codifier files it under the county's name.
    """
    lowered = label.lower()
    if "unincorporated" in lowered:
        county = lowered.replace("unincorporated", "").strip()
        return (f"{county} county", county)
    return ()


def discover(layer: str, label: str) -> list[Candidate]:
    """Every platform's answer, most useful first."""
    order = {"index": 0, "shell": 1, "blocked": 2, "missing": 3}
    out = [probe(layer, platform, url) for platform, url in urls_for(label)]
    out.append(municode(layer, label))
    out.sort(key=lambda c: (order[c.verdict], c.platform))
    return out


def undeclared(rules: Path) -> list[tuple[str, str]]:
    """(layer, label) for every jurisdiction with zones and no declared code."""
    layers = load_rules(rules, strict=False)
    return [
        (layer_id, layer.label)
        for layer_id, layer in sorted(layers.items())
        if layer.zones and not layer.code
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-discover",
        description="Find where a jurisdiction publishes its code.",
    )
    parser.add_argument("--layer", default="", help="one jurisdiction, or a prefix")
    parser.add_argument("--all", action="store_true", help="every jurisdiction with no code declared")
    parser.add_argument("--rules", type=Path, default=CONFIG_ROOT)
    args = parser.parse_args(argv)

    if not args.layer and not args.all:
        parser.error("give --layer or --all")

    targets = [
        (layer_id, label)
        for layer_id, label in undeclared(args.rules)
        if args.all or layer_id.startswith(args.layer)
    ]
    if not targets:
        print("nothing to discover — every matching jurisdiction declares its code", file=sys.stderr)
        return 1

    found = 0
    for layer_id, label in targets:
        print(f"{layer_id}  ({label})")
        results = discover(layer_id, label)
        for candidate in results:
            print(candidate.line())
        if any(c.worth_following for c in results):
            found += 1
        print()

    print(f"{found}/{len(targets)} jurisdiction(s) have a lead to follow")
    print("A lead is a code index, not a citation: pick the zoning chapter, then declare it under `code:`.")
    return 0


__all__ = [
    "MUNICODE_CLIENTS",
    "PLATFORMS",
    "aliases",
    "municode",
    "municode_clients",
    "Candidate",
    "classify",
    "discover",
    "main",
    "name_forms",
    "probe",
    "undeclared",
    "urls_for",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
