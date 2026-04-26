"""Reserved line-item labels for the Gap Adjustment slider feature.

Three phantom line-item labels are protected by the API: users cannot create
new lines with these labels, rename existing lines into these labels, or
rename phantom lines out of them. The Gap Adjustment slider feature
materializes these rows in IncomeStream / OperatingExpenseLine / UseLine
when the user moves a slider; the rows persist (potentially negative) so
the model state survives across sessions and tells the story of what reach
was needed to make the deal pencil.

Identification convention: exact string match on ``label``. The slider
feature looks up phantom rows by these names; downstream UI checks the
same names to apply yellow highlighting and the "balanced with adjustments"
pill state.

Single source of truth: schemas, routers, templates, and the slider
endpoint all import from this module so a future rename happens in one
place.
"""

from __future__ import annotations

from typing import Final

REVENUE_ADJUSTMENT_LABEL: Final[str] = "Gap Adjustment — Revenue"
"""Reserved IncomeStream.label for the slider's revenue-side phantom row."""

OPEX_ADJUSTMENT_LABEL: Final[str] = "Gap Adjustment — OpEx"
"""Reserved OperatingExpenseLine.label for the slider's opex-side phantom row."""

PURCHASE_PRICE_ADJUSTMENT_LABEL: Final[str] = "Gap Adjustment — Purchase Price"
"""Reserved UseLine.label for the slider's PP-side phantom row.

Lives in the acquisition phase, sits directly below the actual Purchase Price
use line. Negative amounts are allowed and effectively reduce total Uses.
"""

ALL_RESERVED_LABELS: Final[frozenset[str]] = frozenset(
    {
        REVENUE_ADJUSTMENT_LABEL,
        OPEX_ADJUSTMENT_LABEL,
        PURCHASE_PRICE_ADJUSTMENT_LABEL,
    }
)


def is_reserved_label(label: str | None) -> bool:
    """True iff ``label`` exactly matches a reserved Gap Adjustment label.

    Comparison is case-sensitive and whitespace-sensitive; reserved labels
    are protected as exact strings only. Surrounding the same characters with
    different whitespace would NOT collide and is allowed.
    """
    return label in ALL_RESERVED_LABELS
