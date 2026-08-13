"""Test helper: stand in for the human who reads the code text.

Trust is a signature over a value, so a test that needs a verified rule set
cannot get one by typing ``status: verified`` in a fixture file — the loader
refuses it, which is the whole point. Instead a fixture marks values
``encoded`` (meaning "written, awaiting review") and this promotes exactly
those, as a reviewer working the queue would.

Deliberately not production code. A function that signs whatever it is handed
is the forgery this design exists to prevent; it belongs where its only caller
is a test.
"""

from __future__ import annotations

from datetime import date

from flats.encode.verify import VerificationLog, apply_verifications, sign
from flats.rules.model import Layer, Status

REVIEWER = "sjk"
REVIEWED = date(2026, 8, 14)


def sign_encoded(
    layers: dict[str, Layer], *, reviewer: str = REVIEWER, reviewed: date = REVIEWED
) -> dict[str, Layer]:
    """Promote every ``encoded`` value; leave drafts alone."""
    entries = []
    for layer_id, layer in layers.items():
        blocks = [("defaults", layer.defaults)]
        blocks += [(code, zone.values) for code, zone in layer.zones.items()]
        for zone_name, values in blocks:
            for name, value in values.items():
                if value.status is Status.encoded:
                    entries.append(
                        sign(layer_id, zone_name, name, value, reviewer=reviewer, reviewed=reviewed)
                    )
    promoted, _ = apply_verifications(layers, VerificationLog(entries))
    return promoted
