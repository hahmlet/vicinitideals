"""A county's certified tax rates by code area, from ``flats/config/tax/``."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from flats.tax.oregon import Levy

CONFIG = Path(__file__).resolve().parents[1] / "config" / "tax"


@dataclass(frozen=True)
class Rates:
    tax_year: str
    county: str
    cpr_residential: Decimal
    city: str
    code_areas: dict[str, tuple[Levy, ...]]
    sources: dict[str, str]
    path: Path

    def levies(self, code: str | None) -> tuple[Levy, ...] | None:
        """The levies of one code area, or None for a code the file does not hold."""
        if not code:
            return None
        return self.code_areas.get(code.strip().zfill(3))


def load(path: Path) -> Rates:
    doc: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    areas = {
        str(code).zfill(3): tuple(
            Levy(
                district=lv["district"],
                kind=lv["kind"],
                category=lv["category"],
                rate=Decimal(str(lv["rate"])),
            )
            for lv in area["levies"]
        )
        for code, area in doc["code_areas"].items()
    }
    for code, area in doc["code_areas"].items():
        total = sum((lv.rate for lv in areas[str(code).zfill(3)]), Decimal("0"))
        if total != Decimal(str(area["total_rate"])):
            raise ValueError(f"{path.name}: code area {code} levies sum to {total}, not {area['total_rate']}")
    return Rates(
        tax_year=str(doc["tax_year"]),
        county=doc["county"],
        cpr_residential=Decimal(str(doc["cpr"]["residential"])),
        city=doc["city"],
        code_areas=areas,
        sources=dict(doc.get("sources") or {}),
        path=path,
    )


def for_county(county: str, tax_year: str) -> Rates:
    """``for_county("multnomah", "2025-26")`` -> ``flats/config/tax/or/multnomah/2025-26.yaml``."""
    return load(CONFIG / "or" / county / f"{tax_year}.yaml")
