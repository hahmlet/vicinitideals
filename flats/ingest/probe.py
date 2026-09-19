"""Ask each county source whether it is still what the copy was taken from.

The monthly check behind the failure-state warning (HUMAN_TODO 20, Steph:
"I don't trust an automated connection unless there's a failure state
warning"). It downloads nothing and changes nothing: one metadata request and
one count request per ArcGIS layer, one item request per RLIS archive, each
compared with what the snapshot's manifest recorded when the copy was taken.
The result is a list of findings; the page turns them into a banner.

What it can find, per dataset:

* ``moved`` -- the service no longer answers as a layer ("Invalid URL", a
  404, a portal error). The copy is unaffected; the next refresh is not.
* ``fields_missing`` -- a field the registry declares is no longer published.
  The next acquire would refuse the layer, so say so now.
* ``count_drift`` -- the feature count under the registry's ``where`` moved
  more than the tolerance (5 %, 2 % for the lot fabric). A rezoning is a few
  polygons; a layer replaced by a different product is a different order of
  magnitude, and that is the case this catches (Gladstone, 2026-09).
* ``registry_changed`` -- the registry entry was edited since the copy was
  taken, or added after it. Not the county's doing, but the copy no longer
  matches the registry that describes it.
* ``new_release`` -- the RLIS archive on the portal is not the one the copy
  was read from (its modified date or size changed).
* ``unreachable`` -- the request did not complete. Deliberately not the same
  finding as ``moved``: a site being down is not evidence its data changed,
  the same rule :mod:`flats.provenance.store` applies to the code documents.
* ``ok`` -- checked, nothing to report; the detail says what was compared.

Nothing here raises for a source's sake. A probe that cannot reach anything
returns forty ``unreachable`` findings, and the page says so.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable

import httpx

from flats.ingest.acquire import _spec_sha
from flats.ingest.sources import Dataset, Kind, Pipeline, Provides

#: Findings that mean the county's side changed, or ours did.
CHANGED = frozenset({"moved", "fields_missing", "count_drift", "registry_changed"})
#: Findings that mean nothing is known to have changed.
SOFT = frozenset({"unreachable", "new_release"})

#: Feature-count tolerance before a layer is said to have drifted.
TOLERANCE = 0.05
#: The lot fabric is large and stable; a 2 % move is thousands of lots.
LOTS_TOLERANCE = 0.02
#: One request must not hold the month's check hostage.
TIMEOUT_S = 20.0
_USER_AGENT = "flats-probe/1.0"


@dataclass(frozen=True)
class Finding:
    key: str
    finding: str
    detail: str

    @property
    def changed(self) -> bool:
        return self.finding in CHANGED

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _tolerance(ds: Dataset) -> float:
    return LOTS_TOLERANCE if ds.provides is Provides.lots else TOLERANCE


def _drifted(before: int, after: int, tolerance: float) -> bool:
    if before == after:
        return False
    if before == 0:
        return True
    return abs(after - before) / before > tolerance


def _get(client: httpx.Client, url: str, params: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    """(document, None) on a JSON answer; (None, why) when the request did not
    complete or the answer was not JSON. An HTTP 4xx is an answer, returned as
    a document with an ``error`` key so the caller can call it ``moved``."""
    try:
        resp = client.get(url, params=params, timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if resp.status_code >= 500:
        return None, f"HTTP {resp.status_code}"
    if resp.status_code >= 400:
        return {"error": {"code": resp.status_code, "message": f"HTTP {resp.status_code}"}}, None
    try:
        doc = resp.json()
    except ValueError:
        return None, "not JSON"
    if not isinstance(doc, dict):
        return None, "not a JSON object"
    return doc, None


def _error_text(doc: dict[str, Any]) -> str:
    err = doc.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or err)
    return str(err)


def probe_arcgis(client: httpx.Client, ds: Dataset, entry: dict[str, Any]) -> list[Finding]:
    """The layer's metadata and its count under the registry's ``where``."""
    meta, why = _get(client, ds.url, {"f": "json"})
    if meta is None:
        return [Finding(ds.key, "unreachable", f"metadata: {why}")]
    if "error" in meta:
        return [Finding(ds.key, "moved", f"the service answered: {_error_text(meta)}")]
    out: list[Finding] = []
    names = [f["name"] for f in meta.get("fields", []) if isinstance(f, dict) and "name" in f]
    if names:
        lower = {n.lower() for n in names}
        wanted = list(ds.fields) + ([ds.zone_field] if ds.zone_field else [])
        missing = [f for f in wanted if f.lower() not in lower]
        if missing:
            out.append(Finding(ds.key, "fields_missing", f"no longer published: {', '.join(missing)}"))
    count_doc, why = _get(
        client, f"{ds.url}/query", {"where": ds.where or "1=1", "returnCountOnly": "true", "f": "json"}
    )
    if count_doc is None:
        out.append(Finding(ds.key, "unreachable", f"count: {why}"))
        return out
    if "error" in count_doc:
        out.append(Finding(ds.key, "moved", f"the count query answered: {_error_text(count_doc)}"))
        return out
    now = int(count_doc.get("count") or 0)
    then = int(entry.get("features") or 0) + len(entry.get("unfetched_ids") or [])
    if _drifted(then, now, _tolerance(ds)):
        out.append(Finding(ds.key, "count_drift", f"{then:,} features when the copy was taken, {now:,} now"))
    if not out:
        out.append(Finding(ds.key, "ok", f"{now:,} features, {len(names)} fields"))
    return out


def probe_archive(client: httpx.Client, url: str, recorded: dict[str, Any] | None) -> Finding:
    """Is the RLIS archive on the portal the one the copy was read from?"""
    item = re.sub(r"/data/?$", "", url)
    if item == url:
        return Finding(url, "ok", "not a portal item; nothing to compare")
    if not recorded:
        return Finding(url, "ok", "the copy recorded no archive identity to compare (taken before 2026-09-19)")
    meta, why = _get(client, item, {"f": "json"})
    if meta is None:
        return Finding(url, "unreachable", f"portal item: {why}")
    if "error" in meta:
        return Finding(url, "moved", f"the portal answered: {_error_text(meta)}")
    modified = None
    if meta.get("modified"):
        modified = dt.datetime.fromtimestamp(int(meta["modified"]) / 1000, tz=dt.UTC).date().isoformat()
    size = int(meta.get("size") or 0)
    was_modified = recorded.get("modified")
    was_size = int(recorded.get("item_size") or recorded.get("size") or 0)
    if (was_modified and modified and modified != was_modified) or (was_size and size and size != was_size):
        return Finding(
            url,
            "new_release",
            f"the archive changed on the portal: modified {was_modified or '?'} -> {modified or '?'}, "
            f"{was_size / 1e9:.2f} -> {size / 1e9:.2f} GB (the copy is release {recorded.get('release') or '?'})",
        )
    return Finding(url, "ok", f"release {recorded.get('release') or '?'}, modified {modified or '?'}")


def probe(
    pipeline: Pipeline,
    manifest: dict[str, Any],
    client: httpx.Client | None = None,
    *,
    log: Callable[[str], None] | None = None,
) -> list[Finding]:
    """Every dataset in the registry against the manifest of the copy in use."""
    own = client is None
    client = client or httpx.Client(
        timeout=httpx.Timeout(TIMEOUT_S), follow_redirects=True, headers={"User-Agent": _USER_AGENT}
    )
    datasets = manifest.get("datasets") or {}
    archives = manifest.get("archives") or {}
    findings: list[Finding] = []
    seen_archives: set[str] = set()
    try:
        for key, ds in pipeline.datasets.items():
            entry = datasets.get(key)
            if entry is None:
                findings.append(Finding(key, "registry_changed", "added to the registry after the copy was taken"))
                continue
            if entry.get("status") not in ("acquired", "present"):
                findings.append(Finding(key, "ok", f"{entry.get('status')} in the copy; nothing to compare"))
                continue
            if entry.get("spec_sha256") != _spec_sha(ds):
                findings.append(Finding(key, "registry_changed", "the registry entry was edited after the copy was taken"))
            if ds.kind is Kind.arcgis:
                findings.extend(probe_arcgis(client, ds, entry))
            elif ds.kind is Kind.rlis_zip:
                if ds.url not in seen_archives:
                    seen_archives.add(ds.url)
                    findings.append(probe_archive(client, ds.url, archives.get(ds.url)))
            if log:
                log(f"{key}: {', '.join(f.finding for f in findings if f.key == key) or 'ok'}")
    finally:
        if own:
            client.close()
    return findings


def summarize(findings: list[Finding]) -> str:
    """One status word for the probe row: ok | warn."""
    return "warn" if any(f.finding != "ok" for f in findings) else "ok"
