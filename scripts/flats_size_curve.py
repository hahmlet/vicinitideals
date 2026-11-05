"""Check whether an existing run contains the fit frontier needed for a size curve.

This command intentionally refuses to approximate or re-screen when the
design-independent frontier is absent.
"""

from __future__ import annotations

import argparse
from pathlib import Path


class FrontierUnavailable(RuntimeError):
    """The stored run cannot answer a design-independent fit query."""


def frontier_status(assign_dir: Path, bridge_dir: Path) -> str:
    import pyarrow.parquet as pq

    assign_path = assign_dir / "lots.parquet"
    bridge_path = bridge_dir / "lots.parquet"
    missing = [str(path) for path in (assign_path, bridge_path) if not path.is_file()]
    if missing:
        raise FrontierUnavailable(f"Missing required parquet file(s): {', '.join(missing)}")

    assign_columns = set(pq.read_schema(assign_path).names)
    bridge_columns = set(pq.read_schema(bridge_path).names)
    frontier_columns = sorted(
        name
        for name in assign_columns | bridge_columns
        if "frontier" in name.casefold() or "max_depth_by_width" in name.casefold()
    )
    if frontier_columns:
        raise FrontierUnavailable(
            "Frontier-like columns are present but no stored-frontier format is "
            f"defined for this script: {frontier_columns}"
        )

    stored = sorted(
        name
        for name in (
            "fit_best_depth_ft",
            "fit_required_ft",
            "fit_across_ft",
            "fit_slack_ft",
            "fits",
            "envelope_sqft",
            "envelope_source",
            "drawing",
        )
        if name in assign_columns
    )
    return (
        "No design-independent fit frontier is stored. "
        f"{assign_path} contains these current-design fit/envelope fields: "
        f"{stored or 'none of the known fields'}. "
        f"{bridge_path} contains {sorted(bridge_columns)}. "
        "The per-design fit fields cannot answer new width/depth queries, and "
        "the bridge does not carry the buildable-envelope geometry. No curve "
        "was computed; this command did not re-screen or write files."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assign", type=Path, default=Path("/root/assign_pd2ab"))
    parser.add_argument("--bridge", type=Path, default=Path("/root/bridge_spliced_pd2ab"))
    args = parser.parse_args(argv)
    try:
        message = frontier_status(args.assign, args.bridge)
    except FrontierUnavailable as exc:
        parser.exit(2, f"flats_size_curve: {exc}\n")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
