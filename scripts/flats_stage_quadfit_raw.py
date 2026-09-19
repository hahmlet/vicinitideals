"""Point quadfit's measurement stages at a dated county-map snapshot.

quadfit (``Lot Analysis/quadfit``) reads its inputs from ``<data dir>/raw/<key>.geojson``
and writes every stage file beside them. The FLATS acquire stage writes the same
GeoJSON, keyed the same way but for four names, into ``data/flats/sources/<date>/``
with a checksummed manifest. This script builds a quadfit data tree for one
snapshot -- links, not copies -- so that a re-measurement from a newer copy of the
county:

* reads every layer from the snapshot it is named after (the manifest is the
  provenance; ``raw/SOURCE.json`` records which one), and
* never touches the tree the live run was measured from (``data/quadfit``, the
  July copy). One tree per snapshot; ``QUADFIT_DATA_DIR`` selects it.

What it does, in order:

1. Refuses unless every layer the snapshot holds is ``acquired`` / ``present`` in
   the manifest and every key quadfit's July tree had is in the snapshot (a
   layer the registry lost would otherwise silently drop out of the screen).
2. Links ``<snapshot>/<key>.geojson`` to ``<tree>/raw/<quadfit key>.geojson``
   with the four renames (``rlis_taxlots`` -> ``taxlots``, ``rlis_streets`` ->
   ``streets``, ``rlis_zoning_metro`` -> ``zoning_metro``, ``ugb_metro`` ->
   ``ugb``). ``rlis_taxlot_change`` is the delta's, not quadfit's, and is skipped.
3. Links the elevation tiles (``dem``, ``dem10``, ``dem10_utm``) from the July
   tree -- terrain does not change quarterly and the tiles are 7 GB.
4. Derives ``overlay_fema_floodway`` / ``overlay_fema_sfha`` from the fetched
   NFHL layer the way quadfit's s0 does (same function).
5. Writes ``raw/SOURCE.json`` and prints the environment line for the run.

Then, on the analysis host::

    QUADFIT_DATA_DIR=data/quadfit_2026-09-18 .venv/bin/python "Lot Analysis/quadfit/run_all.py" --stage s1 --force

Usage::

    python scripts/flats_stage_quadfit_raw.py --snapshot 2026-09-18
    python scripts/flats_stage_quadfit_raw.py --snapshot 2026-09-18 --data-dir /srv/quadfit_sep
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
QUADFIT_DIR = REPO_ROOT / "Lot Analysis" / "quadfit"
sys.path.insert(0, str(QUADFIT_DIR))

from flats.ingest.acquire import SNAPSHOTS, read_manifest, snapshot_dir  # noqa: E402

#: Snapshot key -> quadfit raw key. Everything else keeps its name.
RENAMES = {
    "rlis_taxlots": "taxlots",
    "rlis_streets": "streets",
    "rlis_zoning_metro": "zoning_metro",
    "ugb_metro": "ugb",
}
#: In the snapshot for the delta, never read by a measurement stage.
NOT_QUADFIT = {"rlis_taxlot_change"}
#: The four files a run cannot start without.
CORE = ("taxlots", "streets", "zoning_metro", "ugb")
#: Elevation tiles, shared across snapshots.
DEM_DIRS = ("dem", "dem10", "dem10_utm")
#: quadfit derives these two from ``overlay_fema_flood``; they are never fetched.
DERIVED = ("overlay_fema_floodway", "overlay_fema_sfha")
SOURCE_FILE = "SOURCE.json"


def quadfit_key(snapshot_key: str) -> str:
    return RENAMES.get(snapshot_key, snapshot_key)


def link(src: Path, dst: Path) -> str:
    """Link ``dst`` to ``src``: a symlink, a hard link where symlinks are refused, a copy last.

    Returns which one was made. An existing ``dst`` is replaced, so re-staging
    the same snapshot is idempotent.
    """
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        shutil.rmtree(dst)
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
        return "symlink"
    except (OSError, NotImplementedError):
        pass
    if src.is_dir():
        shutil.copytree(src, dst)
        return "copy"
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def check(manifest: dict[str, Any], snapshot: Path, july_raw: Path | None) -> list[str]:
    """Reasons not to stage; empty when the snapshot is fit to measure from."""
    problems: list[str] = []
    datasets = manifest.get("datasets", {})
    for key, entry in sorted(datasets.items()):
        status = entry.get("status")
        if status in ("retired", "deferred"):
            continue
        if status not in ("acquired", "present"):
            problems.append(f"{key}: {status} -- {entry.get('error', '')}".rstrip(" -"))
            continue
        if entry.get("unfetched_ids"):
            problems.append(
                f"{key}: {len(entry['unfetched_ids'])} features never fetched"
            )
        if not (snapshot / str(entry.get("file") or f"{key}.geojson")).is_file():
            problems.append(
                f"{key}: manifest says {status} but the file is not in the snapshot"
            )
    have = {
        quadfit_key(k)
        for k, e in datasets.items()
        if e.get("status") in ("acquired", "present")
    }
    for key in CORE:
        if key not in have:
            problems.append(
                f"{key}: not in the snapshot; a measurement run cannot start without it"
            )
    if july_raw is not None and july_raw.is_dir():
        july = {p.stem for p in july_raw.glob("*.geojson")} - set(DERIVED)
        for key in sorted(july - have):
            problems.append(
                f"{key}: quadfit's tree has it, the snapshot does not -- register it or retire it on purpose"
            )
    return problems


def stage(
    snapshot: Path,
    data_dir: Path,
    *,
    july_raw: Path | None = None,
    force_fema: bool = True,
) -> dict[str, Any]:
    """Build ``data_dir/raw`` from ``snapshot``; returns what ``SOURCE.json`` records."""
    from s0_acquire import derive_fema_split  # noqa: PLC0415 -- quadfit's, on its own path

    manifest = read_manifest(snapshot)
    problems = check(manifest, snapshot, july_raw)
    if problems:
        raise SystemExit("not staged:\n  " + "\n  ".join(problems))

    raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    linked: dict[str, dict[str, str]] = {}
    for key, entry in sorted(manifest["datasets"].items()):
        if key in NOT_QUADFIT or entry.get("status") not in ("acquired", "present"):
            continue
        src = snapshot / str(entry.get("file") or f"{key}.geojson")
        dst = raw / f"{quadfit_key(key)}.geojson"
        how = link(src.resolve(), dst)
        linked[quadfit_key(key)] = {
            "from": key,
            "file": str(src),
            "how": how,
            "sha256": entry.get("sha256"),
        }
    dems: dict[str, str] = {}
    if july_raw is not None:
        for name in DEM_DIRS:
            src = july_raw / name
            if src.is_dir():
                dems[name] = link(src.resolve(), raw / name)
    derive_fema_split(force_fema, raw_dir=raw)
    derived = [d for d in DERIVED if (raw / f"{d}.geojson").is_file()]

    doc = {
        "snapshot": snapshot.name,
        "snapshot_dir": str(snapshot.resolve()),
        "working_srid": manifest.get("working_srid"),
        "staged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "layers": linked,
        "dem": dems,
        "derived": derived,
        "renames": RENAMES,
    }
    (raw / SOURCE_FILE).write_text(
        json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8"
    )
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument(
        "--snapshot", required=True, help="YYYY-MM-DD under data/flats/sources"
    )
    ap.add_argument("--root", type=Path, default=SNAPSHOTS, help="where snapshots live")
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="quadfit tree to build (default: data/quadfit_<snapshot>)",
    )
    ap.add_argument(
        "--dem-from",
        type=Path,
        default=REPO_ROOT / "data" / "quadfit" / "raw",
        help="raw dir whose elevation tiles are linked in, and whose key set the snapshot must cover",
    )
    args = ap.parse_args(argv)
    snapshot = snapshot_dir(args.snapshot, args.root)
    if not snapshot.is_dir():
        raise SystemExit(f"no snapshot at {snapshot}")
    data_dir = args.data_dir or REPO_ROOT / "data" / f"quadfit_{args.snapshot}"
    doc = stage(
        snapshot, data_dir, july_raw=args.dem_from if args.dem_from.is_dir() else None
    )
    print(
        f"staged {len(doc['layers'])} layers + {len(doc['derived'])} derived, dem {sorted(doc['dem'])} -> {data_dir / 'raw'}"
    )
    print(f"export QUADFIT_DATA_DIR={data_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
