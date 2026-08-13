"""Where code text comes from, and whether that source can back a signature.

Two questions this answers, and they are not the same question.

**Can we get the text at all?** Half the codifiers serving Oregon municipal
code refuse a plain HTTP client. Code Publishing and eCode360 return 403 to
anything that does not look like a browser; Municode returns an empty shell and
renders in JavaScript. A fetcher that gives up on a 403 silently narrows the
project to the jurisdictions that happen to publish PDFs, which is a coverage
decision nobody made. So there is a ladder: cheapest first, browser
impersonation after, and a named failure at the end rather than a shrug.

**Should we believe it?** A citation is a promise that a human can go read the
same words. That promise is only as good as the host. A city's own site and its
contracted codifier publish the ordinance; a commercial aggregator publishes
*its reading* of the ordinance, which is a secondary source no matter how
accurate it usually is. Quadfit cited one of these for West Linn's standards.
Nothing here deletes such a document — it is still a lead — but it may not
stand behind a verified value, because signing it would mean a reviewer
certified the code by reading someone's summary of it.

Unknown hosts are `unknown`, not `official`. A host earns official status by
being named here, which is a one-line change somebody makes deliberately.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Sequence

#: Impersonation targets, cheapest first. The plain client covers most PDFs and
#: every well-behaved site; the rest exist because specific hosts reject
#: specific fingerprints. Code Publishing takes chrome124 and refuses chrome131,
#: which is not a fact anybody could have reasoned out — it was measured.
STRATEGIES: tuple[str, ...] = ("plain", "chrome124", "chrome", "safari17_0", "firefox133")

#: Sent with impersonated requests. A referer from the same host is what
#: separates a browser from a scraper on several of these platforms.
BROWSER_HEADERS = {"Accept-Language": "en-US,en;q=0.9"}

TIMEOUT = 60.0


class Authority(str, enum.Enum):
    """How close this source is to the ordinance itself."""

    #: The jurisdiction's own site, its contracted codifier, or the state.
    #: These publish the adopted text.
    official = "official"
    #: A third party restating the code. Useful for finding things, never
    #: sufficient to certify one.
    aggregator = "aggregator"
    #: Not classified. Treated as an aggregator for trust purposes, because
    #: assuming otherwise is how a summary becomes a citation.
    unknown = "unknown"

    @property
    def may_verify(self) -> bool:
        """Whether a reviewer may sign a value citing this source."""
        return self is Authority.official


#: Registrable domains that publish adopted municipal or state code. Codifiers
#: are here because a city contracting Municode is publishing through Municode
#: — the text on those hosts is the ordinance, not a description of it.
OFFICIAL: frozenset[str] = frozenset(
    {
        # Oregon jurisdictions
        "portland.gov",
        "portlandoregon.gov",
        "greshamoregon.gov",
        "multco.us",
        "clackamas.us",
        "happyvalleyor.gov",
        "ci.oswego.or.us",
        "cityoffairview-or.gov",
        "troutdaleoregon.gov",
        "ci.wood-village.or.us",
        "milwaukieoregon.gov",
        "orcity.org",
        "westlinnoregon.gov",
        "wilsonvilleoregon.gov",
        "tualatinoregon.gov",
        "ci.gladstone.or.us",
        "rivergroveoregon.gov",
        # State
        "oregonlegislature.gov",
        "sos.state.or.us",
        "oregon.gov",
        # Codifiers publishing on a jurisdiction's behalf
        "codepublishing.com",
        "municode.com",
        "ecode360.com",
        "amlegal.com",
        "qcode.us",
        "sterlingcodifiers.com",
        "generalcode.com",
    }
)

#: Third parties that restate code. Not banned — just not evidence.
AGGREGATOR: frozenset[str] = frozenset(
    {
        "zoneomics.com",
        "zoninghub.com",
        "municipalcodes.com",
        "law.justia.com",
        "casetext.com",
    }
)


def host_of(url: str) -> str:
    """The bare host of a URL, lowercased, without port or credentials."""
    rest = url.split("://", 1)[-1]
    host = rest.split("/", 1)[0].split("@")[-1].split(":", 1)[0].lower()
    return host[4:] if host.startswith("www.") else host


def _registrable(host: str) -> list[str]:
    """Candidate parent domains, longest first — ``library.municode.com`` matches ``municode.com``."""
    parts = host.split(".")
    return [".".join(parts[i:]) for i in range(len(parts) - 1)]


def authority_for(url: str) -> Authority:
    """How much a value citing this URL may claim."""
    for domain in _registrable(host_of(url)):
        if domain in OFFICIAL:
            return Authority.official
        if domain in AGGREGATOR:
            return Authority.aggregator
    return Authority.unknown


@dataclass(frozen=True, slots=True)
class Fetched:
    """Bytes off the wire, and what it took to get them."""

    content: bytes
    strategy: str
    status: int
    authority: Authority

    @property
    def impersonated(self) -> bool:
        return self.strategy != "plain"


class FetchFailed(RuntimeError):
    """Every strategy was tried and none returned the document."""


def _plain(url: str) -> tuple[bytes, int]:
    import httpx

    response = httpx.get(url, follow_redirects=True, timeout=TIMEOUT, headers=BROWSER_HEADERS)
    return response.content, response.status_code


def _impersonated(url: str, target: str) -> tuple[bytes, int]:
    from curl_cffi import requests as curl

    headers = dict(BROWSER_HEADERS)
    headers["Referer"] = f"https://{host_of(url)}/"
    response = curl.get(url, impersonate=target, timeout=TIMEOUT, headers=headers)
    return response.content, response.status_code


def fetch(url: str, *, strategies: Sequence[str] = STRATEGIES) -> Fetched:
    """Try each strategy in turn, returning the first that actually answers.

    A 403 is not an answer, and neither is an exception. The ladder exists
    because the alternative — treating a blocked host as an unavailable one —
    quietly restricts the project to jurisdictions with friendly web servers,
    and that would look like a coverage gap rather than a fetching bug.
    """
    problems: list[str] = []
    for target in strategies:
        try:
            content, status = (
                _plain(url) if target == "plain" else _impersonated(url, target)
            )
        except Exception as exc:  # noqa: BLE001 — any transport failure is one more strategy down
            problems.append(f"{target}: {type(exc).__name__}")
            continue
        if status == 200 and content:
            return Fetched(content, target, status, authority_for(url))
        problems.append(f"{target}: HTTP {status}")
    raise FetchFailed(f"{url} — every strategy refused ({'; '.join(problems)})")


__all__ = [
    "AGGREGATOR",
    "OFFICIAL",
    "STRATEGIES",
    "Authority",
    "FetchFailed",
    "Fetched",
    "authority_for",
    "fetch",
    "host_of",
]
