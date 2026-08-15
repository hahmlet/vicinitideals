"""The source PDF itself, cached, so a reviewer can look at the page.

The store keeps the *text* a number was read from, which is what makes an
encoding auditable. It is not what makes it fast to check. Reading a setback off
a table means seeing the table — its column headings, its footnote markers, the
rule printed above it that says the whole thing applies "unless a master plan
provides otherwise". Extraction flattens all of that into lines, and a reviewer
who has to reconstruct a grid from flattened lines is doing the work twice.

So the book is fetched once and kept beside the text, and the review page shows
the actual page. What the reviewer compares against stops being a paragraph of
extracted lines and becomes the sheet a planner would open.

Two things make that safe rather than merely convenient:

*The bytes are checked.* The page map records the SHA-256 of the PDF it was
built from. A book fetched now and hashing differently is a different book, and
its page 239 is not the page the map points at — so it is refused, not shown.
Showing the wrong page under a citation is worse than showing no page, because
it looks like corroboration.

*The cache is not the record.* These files are large and reproducible, so they
live under ``data/`` rather than in the repository, and a missing one is fetched
again rather than being an error. Nothing is encoded from them; the text remains
the thing that is quoted and hashed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from flats.provenance.store import ProvenanceError, ProvenanceStore

#: Where cached books live. Under ``data/`` because they are large, reproducible
#: and derived — the same reasons the parcel corpus is not in the repository.
CACHE = Path(__file__).resolve().parents[2] / "data" / "flats" / "books"

#: What a PDF starts with. A codifier serving an HTML error page with a 200 is
#: ordinary, and caching it would turn one bad fetch into a permanent one.
_MAGIC = b"%PDF-"


class BookError(Exception):
    """The book cannot be shown, and the reason is not the reviewer's fault."""


def fingerprint(data: bytes) -> str:
    """SHA-256 of the file as fetched. Bytes, not text: this identifies the book."""
    return hashlib.sha256(data).hexdigest()


def cache_path(url: str) -> Path:
    """Where a URL's book is kept.

    Named for the URL rather than the document, because several documents are
    read out of one book — Portland's 33.110 is cited by two jurisdictions, and
    Troutdale's two chapters are two slices of a single publication. One file.
    """
    return CACHE / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]}.pdf"


def expected(store: ProvenanceStore, path: str) -> str:
    """The SHA-256 of the book this document's page map was built from.

    Empty when the map predates the field or the document has no map. Callers
    must treat that as "cannot verify" and refuse rather than guess: a page
    number is a claim about a specific book.
    """
    from flats.provenance import pages as page_map

    sidecar = page_map.sidecar(store, path)
    if not sidecar.is_file():
        return ""
    try:
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if raw.get("sha256") != store.load(path).sha256:
        # The text has moved on since the map was built, so the map's line
        # numbers point into a document that no longer exists. Its book hash
        # is about a different edition of the answer.
        return ""
    return raw.get("source_sha256", "")


def save(url: str, data: bytes) -> Path:
    """Put a fetched book in the cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = cache_path(url)
    target.write_bytes(data)
    return target


def ensure(
    store: ProvenanceStore, path: str, *, get: Callable[[str], bytes] | None = None
) -> Path:
    """The cached book for a stored document, fetching it once if need be.

    Raises rather than returning None, and says which of the several different
    failures happened: a document with no map, a book that has changed under the
    encoding, and a codifier that is down are three different problems and only
    one of them is fixed by trying again.
    """
    try:
        document = store.load(path)
    except ProvenanceError as exc:
        raise BookError(str(exc)) from exc

    want = expected(store, path)
    if not want:
        raise BookError(
            f"{path}: no page map ties this text to a book — run "
            "`python -m flats.provenance.pages` before showing pages from it"
        )

    cached = cache_path(document.url)
    if cached.is_file():
        if fingerprint(cached.read_bytes()) == want:
            return cached
        # A cache that disagrees with the map is a cache from before the book
        # was re-published. Drop it and fetch, rather than serving pages out of
        # an edition nothing was read from.
        cached.unlink()

    if get is None:
        from flats.provenance.fetch import fetch_source

        def get(url: str) -> bytes:  # noqa: E306 — local default, not a policy
            return fetch_source(url).content

    try:
        data = get(document.url)
    except Exception as exc:  # noqa: BLE001 — every fetch failure reads the same here
        raise BookError(f"{path}: could not fetch the book — {exc}") from exc

    if data[:5] != _MAGIC:
        raise BookError(f"{path}: what came back is not a PDF")
    if fingerprint(data) != want:
        raise BookError(
            f"{path}: the published book has changed since the page map was built. "
            "Its pages are no longer the pages this encoding cites — re-fetch the "
            "text and rebuild the map before trusting a page number from it"
        )
    return save(document.url, data)
