"""What the Lots pages say about the county copy: the failure-state warning.

Steph's condition on keeping the county map in the app's database (HUMAN_TODO
20): "I don't trust an automated connection unless there's a failure state
warning." The warning is computed here from rows already in the database --
the snapshots registered, the last monthly probe -- and never from a live
request, so a dead service or a dead analysis box cannot silence it. The
absence of a warning is also said out loud (:func:`footer`), so silence is
never mistaken for health.

Red means the copy in use should not be trusted without a look, or the next
refresh will fail; amber means something is waiting or unchecked. The rules:

* red ``none``     -- no copy has been registered at all.
* red ``stale``    -- the copy in use is older than :data:`STALE_DAYS` (one
  missed quarter).
* red ``failed``   -- the newest snapshot attempt failed outright.
* red ``incomplete`` -- the newest snapshot has a refused or failed dataset,
  or features it could not fetch. Deferred (terrain) and retired do not count.
* red ``source_changed`` -- the newest probe found a layer moved, a field
  gone, a count outside tolerance, or the registry edited since the copy.
* red/amber ``unreachable`` -- a layer did not answer the probe: amber once,
  red when the probe before it could not reach the same layer either. A site
  being down is not evidence its data changed.
* amber ``new_release`` -- the probe saw a new RLIS archive on the portal and
  no snapshot has been taken since.
* amber ``waiting``  -- a candidate has sat unreviewed for more than
  :data:`CANDIDATE_WAIT_DAYS`.
* amber ``unchecked`` -- no probe in the last :data:`PROBE_GAP_DAYS`.

Everything is plain data (:class:`Snapshot`, :class:`Probe`) so the page can
build it from ORM rows and the tests from literals.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from flats.ingest.probe import CHANGED

STALE_DAYS = 120
CANDIDATE_WAIT_DAYS = 14
PROBE_GAP_DAYS = 45

#: Manifest statuses that leave a hole in the copy.
_HOLES = ("refused", "failed")


@dataclass(frozen=True)
class Snapshot:
    id: int
    snapshot_date: dt.date
    status: str  # candidate | current | retired | failed
    registered_at: dt.date
    rlis_release: str | None = None
    manifest: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass(frozen=True)
class Probe:
    ran_at: dt.date
    status: str  # ok | warn | failed
    findings: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class Notice:
    level: str  # red | amber
    code: str
    text: str


def holes(manifest: dict[str, Any]) -> list[str]:
    """Datasets the snapshot does not hold as declared: ``key (status)``."""
    out = []
    for key, entry in sorted((manifest.get("datasets") or {}).items()):
        status = entry.get("status")
        if status in _HOLES:
            out.append(f"{key} ({status})")
        elif entry.get("unfetched_ids"):
            out.append(f"{key} ({len(entry['unfetched_ids'])} features unfetched)")
    return out


def assess(
    *,
    current: Snapshot | None,
    latest: Snapshot | None,
    candidates: list[Snapshot],
    probes: list[Probe],
    today: dt.date,
) -> list[Notice]:
    """The notices the banner shows, red first.

    ``latest`` is the newest snapshot by date whatever its status; ``probes``
    are the newest first (two are enough).
    """
    red: list[Notice] = []
    amber: list[Notice] = []

    if current is None:
        red.append(Notice("red", "none", "No county map copy has been recorded. The lots shown come from nowhere the app can name."))
    else:
        age = (today - current.snapshot_date).days
        if age > STALE_DAYS:
            red.append(
                Notice(
                    "red",
                    "stale",
                    f"The county map copy is {age} days old (taken {current.snapshot_date.isoformat()}). A refresh is due.",
                )
            )

    if latest is not None and (current is None or latest.id != current.id):
        in_use = f" The copy in use is from {current.snapshot_date.isoformat()}." if current else ""
        if latest.status == "failed":
            red.append(
                Notice(
                    "red",
                    "failed",
                    f"The last county download ({latest.snapshot_date.isoformat()}) failed.{in_use}",
                )
            )
    if latest is not None:
        gaps = holes(latest.manifest)
        if gaps:
            shown = ", ".join(gaps[:4]) + (f" and {len(gaps) - 4} more" if len(gaps) > 4 else "")
            same = current is not None and latest.id == current.id
            tail = "" if same or current is None else f" The copy in use is from {current.snapshot_date.isoformat()}."
            red.append(
                Notice(
                    "red",
                    "incomplete",
                    f"The {'copy in use' if same else 'last county download'} ({latest.snapshot_date.isoformat()}) "
                    f"did not complete: {shown}.{tail}",
                )
            )

    # A check that did not complete is not a check: it neither clears the
    # "unchecked" clock nor counts as a month the sources answered.
    if probes and probes[0].status == "failed":
        why = next((f.get("detail") for f in probes[0].findings if f.get("detail")), "")
        amber.append(
            Notice(
                "amber",
                "check_failed",
                f"The monthly source check on {probes[0].ran_at.isoformat()} did not complete"
                + (f": {why}." if why else "."),
            )
        )
    probes = _completed(probes)
    newest = probes[0] if probes else None
    if newest is not None:
        changed = [f for f in newest.findings if f.get("finding") in CHANGED and f.get("finding") != "registry_changed"]
        if changed:
            keys = sorted({f["key"] for f in changed})
            shown = ", ".join(keys[:3]) + (f" and {len(keys) - 3} more" if len(keys) > 3 else "")
            red.append(
                Notice(
                    "red",
                    "source_changed",
                    f"A county source changed on its own side ({shown}; checked {newest.ran_at.isoformat()}). "
                    "The copy in use is unaffected, but the next refresh will need attention.",
                )
            )
        # Our side, not the county's: the registry no longer describes the copy.
        edited = sorted({f["key"] for f in newest.findings if f.get("finding") == "registry_changed"})
        if edited:
            shown = ", ".join(edited[:3]) + (f" and {len(edited) - 3} more" if len(edited) > 3 else "")
            red.append(
                Notice(
                    "red",
                    "registry_changed",
                    f"The list of county sources was changed after the copy was taken ({shown}; "
                    f"checked {newest.ran_at.isoformat()}). The copy in use does not hold them; the next refresh will.",
                )
            )
        down = sorted({f["key"] for f in newest.findings if f.get("finding") == "unreachable"})
        if down:
            before = probes[1] if len(probes) > 1 else None
            twice = before is not None and any(
                f.get("finding") == "unreachable" and f.get("key") in down for f in before.findings
            )
            shown = ", ".join(down[:3]) + (f" and {len(down) - 3} more" if len(down) > 3 else "")
            (red if twice else amber).append(
                Notice(
                    "red" if twice else "amber",
                    "unreachable",
                    f"{shown} did not answer the {'last two monthly checks' if twice else 'monthly check'} "
                    f"({newest.ran_at.isoformat()}). The copy in use is unaffected.",
                )
            )
        fresh = [f for f in newest.findings if f.get("finding") == "new_release"]
        if fresh and not any(s.snapshot_date >= newest.ran_at for s in candidates):
            amber.append(
                Notice(
                    "amber",
                    "new_release",
                    "Metro has published a new quarterly RLIS release since the copy was taken "
                    f"(seen {newest.ran_at.isoformat()}). A refresh can start.",
                )
            )
        if (today - newest.ran_at).days > PROBE_GAP_DAYS:
            amber.append(
                Notice(
                    "amber",
                    "unchecked",
                    f"The monthly source check has not run since {newest.ran_at.isoformat()}.",
                )
            )
    else:
        amber.append(Notice("amber", "unchecked", "The monthly source check has not run yet."))

    for cand in sorted(candidates, key=lambda s: s.registered_at):
        waited = (today - cand.registered_at).days
        if waited > CANDIDATE_WAIT_DAYS:
            amber.append(
                Notice(
                    "amber",
                    "waiting",
                    f"A refreshed copy from {cand.snapshot_date.isoformat()} has been waiting for review for {waited} days.",
                )
            )
    return red + amber


def _completed(probes: list[Probe]) -> list[Probe]:
    return [p for p in probes if p.status != "failed"]


def footer(current: Snapshot | None, probes: list[Probe]) -> str:
    """The one line that is always shown, so 'no warning' is a statement."""
    if current is None:
        return "County map copy: none recorded."
    release = f"RLIS {current.rlis_release}" if current.rlis_release else "RLIS"
    text = f"County map copy: {release} + ArcGIS layers, taken {current.snapshot_date.isoformat()}"
    probes = _completed(probes)
    if probes:
        text += f"; sources checked {probes[0].ran_at.isoformat()}"
    return text + "."
