"""The promotion gate's numbers: what a refreshed county copy must pass before the agent may promote it.

Steph's rule (2026-09-19): *"Me, when clean; you, when warned."* This module
decides "clean" versus "warned" -- nothing else. It is pure: the loader
gathers the inputs from the database at the end of a candidate load and
stores the result on ``flats.snapshots.checks``; the promotion service reads
that column back. Every code is always present, tripped or not, so the page
can show the whole gate and not only the failures:

``layers_incomplete``
    A dataset the acquire stage refused or failed, or one with features it
    never fetched. The copy is not whole; nothing measured from it is trusted.
``count_drift``
    A dataset's feature count moved more than :data:`COUNT_DRIFT` (taxlots
    :data:`TAXLOT_DRIFT`) against the copy in use -- the shape a layer takes
    when the service behind it was replaced (Gladstone came back as the
    regional fabric).
``new_zones``
    Zone codes on the county map that nobody has ruled on: neither a zone
    block in the layer's rules (a forbidden use is a zone block too, with
    ``quadplex_allowed: false``) nor a ``zone_rulings`` entry (an alias, a
    pocket of another jurisdiction's zoning, an unholdable district, a use
    table still to read). Those lots screen ``unknown``. Steph's rule
    (2026-09-20): every code on the map is read and ruled once, with the
    reason written down, and after that the only thing worth a warning is a
    code no one has seen -- a city creating or renaming a district. So this
    trips on ANY unruled code, carried from the earlier copy or not; a code
    that stays unruled stays warned until somebody rules on it. The earlier
    copy's list is still read, so the detail can say which codes are new
    this quarter and which were already waiting. **It warns; it does not
    block** -- see :data:`WARN_ONLY`.
``lots_drift``
    The measured lot count moved more than :data:`TAXLOT_DRIFT` against the
    run in use.
``zone_changes``
    More than :data:`ZONE_CHANGE_SHARE` of one jurisdiction's lots changed
    zone between the two copies (a rezoning, or a zoning layer that moved).
``rlis_agreement``
    Metro's own change list and our delta disagree: recall under
    :data:`RLIS_AGREEMENT` on either side in either county.

A threshold is a warning, never a verdict on the data: a tripped check means
a person reads the report before the copy is promoted.

One check warns without holding the copy back. Steph, 2026-09-22 (HUMAN_TODO
22): *"when a city invents a zone code, only those lots sit while the rest go
live."* A code nobody has ruled on says nothing about the rest of the county,
and its own lots are already safe -- they screen ``unknown`` with the reason
``ZONE_NOT_ENCODED``, never green and never red, until the code is read. So
:data:`WARN_ONLY` names it: :func:`tripped` still reports it, the page and the
banner still name the code and count its lots, and :func:`blocking` -- what
the promotion gate reads -- leaves it out.
"""

from __future__ import annotations

from typing import Any

#: A dataset's feature count may move this much before it is a warning.
COUNT_DRIFT = 0.05
#: The taxlot fabric, and the measured lot count, are held tighter.
TAXLOT_DRIFT = 0.02
#: The share of one jurisdiction's lots that may change zone quietly.
ZONE_CHANGE_SHARE = 0.10
#: The smallest jurisdiction the zone-change share is read on.
ZONE_CHANGE_FLOOR = 20
#: Recall of Metro's added / deleted lists below this is a disagreement.
RLIS_AGREEMENT = 0.80
#: The dataset the tighter drift applies to.
TAXLOTS = "rlis_taxlots"
#: Manifest statuses that leave a dataset whole (deferred and retired are on purpose).
WHOLE = ("acquired", "present", "deferred", "retired")
#: The statuses under which a dataset has a file, and so a feature count worth comparing.
FETCHED = ("acquired", "present")

CODES = ("layers_incomplete", "count_drift", "new_zones", "lots_drift", "zone_changes", "rlis_agreement")
#: Codes that are shown and counted but never hold a copy back (Steph, 2026-09-22).
WARN_ONLY = ("new_zones",)


def _pct(new: float, old: float) -> float:
    return abs(new - old) / old if old else (1.0 if new else 0.0)


def _check(tripped: bool, detail: str) -> dict[str, Any]:
    return {"tripped": bool(tripped), "detail": detail}


def snapshot_checks(
    *,
    datasets: dict[str, dict[str, Any]],
    baseline_datasets: dict[str, dict[str, Any]] | None,
    new_zones: dict[str, dict[str, int]] | None,
    baseline_new_zones: dict[str, dict[str, int]] | None,
    measured: int,
    baseline_measured: int | None,
    zone_changes: dict[str, tuple[int, int]],
    crosscheck: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Every promotion check, tripped or not.

    ``datasets`` / ``baseline_datasets`` are ``snapshots.counts["datasets"]``
    (``{key: {status, features, unfetched}}``) for the copy being loaded and
    the copy in use; ``zone_changes`` is ``{jurisdiction: (changed, total)}``
    over the lots both copies hold; ``crosscheck`` is the delta's
    ``report["delta"]["crosscheck"]``.
    """
    out: dict[str, dict[str, Any]] = {}

    broken = []
    for key, d in sorted(datasets.items()):
        status = d.get("status")
        unfetched = int(d.get("unfetched") or 0)
        if status not in WHOLE:
            broken.append(f"{key}: {status}")
        elif unfetched:
            broken.append(f"{key}: {unfetched} features never fetched")
    out["layers_incomplete"] = _check(
        bool(broken),
        "; ".join(broken) if broken else f"every one of {len(datasets)} datasets whole",
    )

    moved = []
    compared = 0
    if baseline_datasets:
        for key, d in sorted(datasets.items()):
            before = baseline_datasets.get(key) or {}
            if d.get("status") not in FETCHED or before.get("status") not in FETCHED:
                continue  # a layer that is not whole is layers_incomplete's finding, not this one's
            old, new = before.get("features"), d.get("features")
            if old is None or new is None:
                continue
            compared += 1
            limit = TAXLOT_DRIFT if key == TAXLOTS else COUNT_DRIFT
            if _pct(new, old) > limit:
                moved.append(f"{key}: {old:,} -> {new:,} ({_pct(new, old):+.1%})")
    out["count_drift"] = _check(
        bool(moved),
        "; ".join(moved)
        if moved
        else (f"{compared} datasets within tolerance" if compared else "no earlier copy holds feature counts; nothing to compare"),
    )

    codes = []
    waiting = []
    for layer_id, by_code in sorted((new_zones or {}).items()):
        known = set((baseline_new_zones or {}).get(layer_id) or {})
        fresh = {c: n for c, n in by_code.items() if c not in known}
        old = {c: n for c, n in by_code.items() if c in known}
        if fresh:
            codes.append(f"{layer_id}: " + ", ".join(f"{c} ({n:,})" for c, n in sorted(fresh.items())))
        if old:
            waiting.append(f"{layer_id}: " + ", ".join(f"{c} ({n:,})" for c, n in sorted(old.items())))
    if codes and waiting:
        detail = "new this copy -- " + "; ".join(codes) + " -- and still unruled from the earlier copy -- " + "; ".join(waiting)
    elif codes:
        detail = "; ".join(codes)
    elif waiting:
        detail = "no new codes; still unruled from the earlier copy -- " + "; ".join(waiting)
    else:
        detail = "every zone code on the map is in the rules or ruled"
    out["new_zones"] = _check(bool(codes or waiting), detail)

    if baseline_measured:
        pct = _pct(measured, baseline_measured)
        out["lots_drift"] = _check(
            pct > TAXLOT_DRIFT,
            f"{baseline_measured:,} -> {measured:,} measured lots ({(measured - baseline_measured) / baseline_measured:+.1%})",
        )
    else:
        out["lots_drift"] = _check(False, f"{measured:,} measured lots; no earlier run to compare")

    shifted = []
    read = 0
    for juris, (changed, total) in sorted(zone_changes.items()):
        if total < ZONE_CHANGE_FLOOR:
            continue
        read += 1
        if changed / total > ZONE_CHANGE_SHARE:
            shifted.append(f"{juris}: {changed:,} of {total:,} ({changed / total:.0%})")
    if shifted:
        quiet = "; ".join(shifted)
    elif read:
        quiet = f"{read} jurisdictions within tolerance"
    elif zone_changes:
        quiet = f"{len(zone_changes)} jurisdictions share fewer than {ZONE_CHANGE_FLOOR} lots with the earlier copy"
    else:
        quiet = "no lots shared with an earlier copy"
    out["zone_changes"] = _check(bool(shifted), quiet)

    if crosscheck and crosscheck.get("counties"):
        low = []
        for county, sides in sorted(crosscheck["counties"].items()):
            for side in ("added", "deleted"):
                recall = (sides.get(side) or {}).get("recall")
                if recall is not None and recall < RLIS_AGREEMENT:
                    low.append(f"{county} {side}: recall {recall:.0%}")
        out["rlis_agreement"] = _check(
            bool(low),
            "; ".join(low) if low else f"min recall {crosscheck.get('min_recall')} against Metro's change list",
        )
    else:
        out["rlis_agreement"] = _check(False, "no delta cross-check stored for this copy")

    return out


def tripped(checks: dict[str, dict[str, Any]] | None) -> list[str]:
    """Every check that found something, in the gate's order -- warn-only ones included."""
    checks = checks or {}
    return [c for c in CODES if (checks.get(c) or {}).get("tripped")]


def blocking(checks: dict[str, dict[str, Any]] | None) -> list[str]:
    """The codes that keep an agent from promoting: :func:`tripped` less :data:`WARN_ONLY`."""
    return [c for c in tripped(checks) if c not in WARN_ONLY]


def warnings(checks: dict[str, dict[str, Any]] | None) -> list[str]:
    """The warn-only codes that stand: worth saying, never worth waiting on."""
    return [c for c in tripped(checks) if c in WARN_ONLY]
