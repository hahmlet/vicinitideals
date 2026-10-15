"""Fetch DLCD amendment notices and write the new FLATS reading list."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flats.watch.dlcd import (
    Kind,
    fetch,
    load_jurisdictions,
    load_ledger,
    new_notices,
    parse,
    render_markdown,
)


def _kinds(value: str) -> tuple[Kind, ...]:
    values = tuple(part.strip() for part in value.split(",") if part.strip())
    allowed = {"adopted", "proposed"}
    if not values or len(set(values)) != len(values) or set(values) - allowed:
        raise argparse.ArgumentTypeError(
            "kinds must be a comma-separated list of adopted and/or proposed"
        )
    return cast(tuple[Kind, ...], values)


def main() -> None:
    """Run both report fetches, filter the ledger, and write the reading list."""
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        default=today - timedelta(days=21),
        help="first received date, YYYY-MM-DD (default: 21 days ago)",
    )
    parser.add_argument(
        "--kinds",
        type=_kinds,
        default=("adopted", "proposed"),
        help="comma-separated adopted,proposed report kinds",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "flats" / "dlcd" / today.isoformat(),
        help="output directory",
    )
    args = parser.parse_args()
    if args.since > today:
        parser.error("--since cannot be after today")

    args.out.mkdir(parents=True, exist_ok=True)
    notices = []
    per_kind: dict[str, int] = {}
    mapping = load_jurisdictions()
    for kind in args.kinds:
        csv_path = fetch(kind, args.since, today, args.out / f"{kind}.csv")
        parsed = parse(csv_path)
        per_kind[kind] = sum(notice.jurisdiction in mapping for notice in parsed)
        notices.extend(parsed)

    fresh = new_notices(notices, load_ledger())
    payload = []
    for notice in fresh:
        record = asdict(notice)
        record["id"] = notice.id
        record["link"] = notice.link
        record["jurisdiction_slug"] = mapping[notice.jurisdiction]
        payload.append(record)

    (args.out / "new.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out / "new.md").write_text(
        render_markdown(fresh, mapping),
        encoding="utf-8",
    )
    counts = " ".join(f"{kind}={count}" for kind, count in per_kind.items())
    print(f"DLCD watch: {counts} new={len(fresh)} out={args.out}")


if __name__ == "__main__":
    main()
