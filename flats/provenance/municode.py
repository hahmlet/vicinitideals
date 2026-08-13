"""Reading the ten Oregon jurisdictions that publish through Municode.

Municode was the largest hole in the corpus: its library renders in JavaScript,
so a plain fetch sees a 6,095-byte frame and nothing else. Two facts, both
measured rather than reasoned out, close it.

**The library URL answers nothing.** `library.municode.com/or/<anything>/codes/...`
returns that same frame whether the city is a client or not — the "not found"
renders client-side. So membership is asked of the client registry instead, which
is plain JSON and public.

**The official PDF is public.** The library's own content API needs an OIDC token,
but the *publication download* endpoint does not: given a publication id it returns
a signed blob URL for the adopted code as a single PDF. That is a better artifact
than the rendered HTML anyway — it is the document the city adopted, which is what
a citation promises a reader can go and check.

So the chain is three public calls::

    Clients/stateAbbr?stateAbbr=OR   -> ClientID      (is this city here at all?)
    ClientContent/{ClientID}         -> publicationId (which code, last updated when)
    PublicationPdfDownload/{pubId}   -> signed URL    (the adopted PDF)

A declared `code:` entry holds the **third URL, unsigned** —
`https://api.municode.com/PublicationPdfDownload/1951`. It is stable, it is
official, and the signature on the blob URL expires in minutes, so storing the
signed one would produce a citation that stops working by the time anybody follows
it. :func:`flats.provenance.sources.fetch` follows the hop.

Run::

    python -m flats.provenance.municode --layer or/clackamas/wilsonville
    python -m flats.provenance.municode --all
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

from flats.provenance.sources import FetchFailed, fetch

API = "https://api.municode.com"
CLIENTS = API + "/Clients/stateAbbr?stateAbbr={state}"
CLIENT_CONTENT = API + "/ClientContent/{client_id}"
PDF_DOWNLOAD = API + "/PublicationPdfDownload/{publication_id}"
LIBRARY = "https://library.municode.com/{state_lower}/{snake}/codes/code_of_ordinances"

#: The one URL shape whose body is another URL rather than a document. Named
#: here so :mod:`flats.provenance.sources` can follow it without knowing why.
INDIRECT = re.compile(r"^https://api\.municode\.com/PublicationPdfDownload/\d+/?$")

_PUNCT = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class Publication:
    """One jurisdiction's adopted code, as Municode holds it."""

    client: str
    client_id: int
    product: str
    product_id: int
    publication_id: int
    updated: str = ""

    @property
    def url(self) -> str:
        """The stable, unsigned URL that resolves to the PDF."""
        return PDF_DOWNLOAD.format(publication_id=self.publication_id)

    @property
    def doc_id(self) -> str:
        """Store filename stem: the product's name, slugged.

        Not a constant — Troutdale and Tualatin each publish a Code of
        Ordinances *and* a Development Code as separate products, and one
        fixed id would file both under the same name.
        """
        return _PUNCT.sub("-", self.product.lower()).strip("-") or "municode-code"


def key(name: str) -> str:
    return _PUNCT.sub("", name.lower())


def aliases(label: str) -> tuple[str, ...]:
    """Other names a codifier might file this jurisdiction under.

    Unincorporated county land is its own jurisdiction because that is how the
    zoning works, and the county's name to everybody else.
    """
    lowered = label.lower()
    if "unincorporated" in lowered:
        county = lowered.replace("unincorporated", "").strip()
        return (f"{county} county", county)
    return ()


@lru_cache(maxsize=8)
def clients(state: str = "OR") -> tuple[tuple[str, int], ...] | None:
    """Every jurisdiction Municode publishes in one state.

    ``None`` means the registry could not be read — distinct from an empty
    list, which would mean the platform publishes nobody here. Those are
    opposite conclusions and the second must never stand in for the first.
    """
    try:
        got = fetch(CLIENTS.format(state=state.upper()), strategies=("plain",))
        listed = json.loads(got.content)
    except (FetchFailed, ValueError):
        return None
    return tuple(
        (str(entry.get("ClientName", "")), int(entry.get("ClientID", 0)))
        for entry in listed
        if entry.get("ClientName")
    )


def client_for(label: str, *, state: str = "OR") -> tuple[str, int] | None:
    """The registry entry for this jurisdiction, or None if it is not one."""
    listed = clients(state)
    if not listed:
        return None
    wanted = {key(label)} | {key(alias) for alias in aliases(label)}
    return next((entry for entry in listed if key(entry[0]) in wanted), None)


#: Product names that carry zoning standards when a client publishes several.
#: Measured, not assumed: Troutdale and Tualatin both list a Code of
#: Ordinances first and keep their setbacks in a separately-published
#: Development Code — their own rule-file citations say so.
_ZONING_PRODUCT_WORDS = ("development", "zoning", "land use", "land development")


def publications(label: str, *, state: str = "OR") -> tuple[Publication, ...]:
    """Every adopted publication Municode holds for this jurisdiction."""
    entry = client_for(label, state=state)
    if entry is None:
        return ()
    name, client_id = entry
    try:
        got = fetch(CLIENT_CONTENT.format(client_id=client_id), strategies=("plain",))
        content = json.loads(got.content)
    except (FetchFailed, ValueError):
        return ()
    return tuple(
        Publication(
            client=name,
            client_id=client_id,
            product=str(code.get("productName", "")),
            product_id=int(code.get("productId", 0)),
            publication_id=int(code["publicationId"]),
            updated=str(code.get("latestUpdatedDate", "")),
        )
        for code in content.get("codes") or []
        if code.get("publicationId")
    )


def publication(label: str, *, state: str = "OR") -> Publication | None:
    """The publication most likely to state this jurisdiction's zoning standards.

    A development code when the client publishes one, otherwise the first
    product. Two of the three Municode cities in this corpus keep their
    setbacks outside the code of ordinances, so "first listed" was quietly
    handing back a charter.
    """
    found = publications(label, state=state)
    for pub in found:
        if any(word in pub.product.lower() for word in _ZONING_PRODUCT_WORDS):
            return pub
    return found[0] if found else None


def resolve(url: str, body: bytes) -> str | None:
    """The real document URL, when what came back was a URL rather than a document.

    Returns None for anything else, so the caller can stay ignorant of Municode.
    """
    if not INDIRECT.match(url.strip()):
        return None
    try:
        target = json.loads(body)
    except ValueError:
        return None
    return target if isinstance(target, str) and target.startswith("https://") else None


def code_block(pub: Publication) -> str:
    """The `code:` entry to paste into a layer file."""
    return (
        "code:\n"
        f"  # Municode client {pub.client_id}, publication {pub.publication_id}"
        f" (updated {pub.updated[:10]}).\n"
        "  # The library renders in JavaScript; this endpoint returns the adopted PDF.\n"
        f'  - id: "{pub.doc_id}"\n'
        f"    url: {pub.url}\n"
        f'    title: "{pub.client} {pub.product}"\n'
    )


def main(argv: Sequence[str] | None = None) -> int:
    from flats.rules.loader import CONFIG_ROOT, load_rules

    parser = argparse.ArgumentParser(
        prog="flats-municode",
        description="Find the adopted-code PDF for jurisdictions Municode publishes.",
    )
    parser.add_argument("--layer", default="", help="one jurisdiction, or a prefix")
    parser.add_argument("--all", action="store_true", help="every jurisdiction with no code declared")
    parser.add_argument("--state", default="OR")
    parser.add_argument("--rules", type=Path, default=CONFIG_ROOT)
    args = parser.parse_args(argv)

    if not args.layer and not args.all:
        parser.error("give --layer or --all")

    layers = load_rules(args.rules, strict=False)
    targets = [
        (layer_id, layer.label)
        for layer_id, layer in sorted(layers.items())
        if layer.zones
        and (args.all or layer_id.startswith(args.layer))
        and (not layer.code or not args.all)
    ]
    if not targets:
        print("no matching jurisdiction", file=sys.stderr)
        return 1

    found = 0
    for layer_id, label in targets:
        held = publications(label, state=args.state)
        pub = publication(label, state=args.state)
        if pub is None:
            print(f"{layer_id:38} not a Municode jurisdiction")
            continue
        found += 1
        print(f"{layer_id:38} {pub.client} - {pub.product} (updated {pub.updated[:10]})")
        for other in held:
            if other.publication_id != pub.publication_id:
                print(f"{'':38} also publishes: {other.product} (publication {other.publication_id})")
        print(code_block(pub))
    print(f"{found}/{len(targets)} jurisdiction(s) publish through Municode")
    return 0


__all__ = [
    "API",
    "INDIRECT",
    "Publication",
    "aliases",
    "client_for",
    "clients",
    "code_block",
    "key",
    "main",
    "publication",
    "publications",
    "resolve",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
