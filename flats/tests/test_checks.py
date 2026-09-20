"""``flats.ingest.checks`` -- the promotion gate's thresholds, tripped both ways.

Each check must trip on the shape it names and stay quiet on the shape it does
not; and every code is present in the answer whether or not it tripped, so a
page can show a clean gate as six named passes rather than an empty list.
"""

from __future__ import annotations

from flats.ingest.checks import CODES, snapshot_checks, tripped

DATASETS = {
    "rlis_taxlots": {"status": "acquired", "features": 453_000, "unfetched": 0},
    "zoning_portland": {"status": "acquired", "features": 10_000, "unfetched": 0},
    "overlay_gone": {"status": "retired", "features": 0, "unfetched": 0},
    "dem": {"status": "deferred", "features": 0, "unfetched": 0},
}
CROSSCHECK = {
    "min_recall": 0.9,
    "agrees": True,
    "counties": {
        "clackamas": {"added": {"recall": 0.95, "precision": 0.4}, "deleted": {"recall": 0.9, "precision": 0.5}},
        "multnomah": {"added": {"recall": 0.9, "precision": 0.6}, "deleted": {"recall": None, "precision": None}},
    },
}


def _clean(**over):
    args = dict(
        datasets=DATASETS,
        baseline_datasets=DATASETS,
        new_zones={},
        baseline_new_zones=None,
        measured=290_000,
        baseline_measured=289_845,
        zone_changes={"or/multnomah/portland": (100, 150_000), "or/clackamas/tiny": (5, 6)},
        crosscheck=CROSSCHECK,
    )
    args.update(over)
    return snapshot_checks(**args)


def test_a_clean_copy_passes_every_check_by_name() -> None:
    checks = _clean()
    assert tuple(checks) == CODES
    assert tripped(checks) == []
    assert checks["layers_incomplete"]["detail"] == "every one of 4 datasets whole"
    assert checks["count_drift"]["detail"] == "2 datasets within tolerance"
    assert checks["lots_drift"]["detail"] == "289,845 -> 290,000 measured lots (+0.1%)"
    assert checks["zone_changes"]["detail"] == "1 jurisdictions within tolerance", "a six-lot city is below the floor"
    assert checks["rlis_agreement"]["detail"].startswith("min recall 0.9")


def test_a_layer_that_is_not_whole_trips() -> None:
    broken = {
        **DATASETS,
        "zoning_portland": {"status": "failed", "features": 0, "unfetched": 0},
        "ugb_metro": {"status": "acquired", "features": 1, "unfetched": 3},
    }
    checks = _clean(datasets=broken)
    assert tripped(checks) == ["layers_incomplete"]
    assert checks["layers_incomplete"]["detail"] == "ugb_metro: 3 features never fetched; zoning_portland: failed"


def test_feature_counts_that_moved_trip_taxlots_tighter_than_the_rest() -> None:
    moved = {
        **DATASETS,
        "rlis_taxlots": {"status": "acquired", "features": 453_000 + 12_000, "unfetched": 0},  # +2.6 %
        "zoning_portland": {"status": "acquired", "features": 10_400, "unfetched": 0},  # +4 %
    }
    checks = _clean(datasets=moved)
    assert tripped(checks) == ["count_drift"]
    assert checks["count_drift"]["detail"] == "rlis_taxlots: 453,000 -> 465,000 (+2.6%)"
    quiet = _clean(baseline_datasets=None)
    assert quiet["count_drift"] == {"tripped": False, "detail": "no earlier copy holds feature counts; nothing to compare"}


def test_new_zone_codes_trip_and_are_listed_by_layer() -> None:
    checks = _clean(new_zones={"or/multnomah/portland": {"RM9": 40, "CM0": 2}, "or/clackamas": {"XYZ": 1}})
    assert tripped(checks) == ["new_zones"]
    assert checks["new_zones"]["detail"] == "or/clackamas: XYZ (1); or/multnomah/portland: CM0 (2), RM9 (40)"


def test_an_unruled_code_the_copy_in_use_already_had_still_trips_until_ruled() -> None:
    """Steph 2026-09-20: a code is ruled once and never asked about again --
    so a code NOBODY ruled on is warned about every quarter until somebody
    does, whether or not the earlier copy carried it. The detail tells the
    two apart."""
    known = {"or/clackamas": {"C3": 447, "EFU": 149}, "or/multnomah/portland": {"CM0": 2}}
    same = _clean(new_zones={"or/clackamas": {"C3": 450, "EFU": 149}}, baseline_new_zones=known)
    assert tripped(same) == ["new_zones"]
    assert same["new_zones"]["detail"] == "no new codes; still unruled from the earlier copy -- or/clackamas: C3 (450), EFU (149)"
    one_new = _clean(new_zones={"or/clackamas": {"C3": 450, "RMX": 3}}, baseline_new_zones=known)
    assert tripped(one_new) == ["new_zones"]
    assert one_new["new_zones"]["detail"] == (
        "new this copy -- or/clackamas: RMX (3) -- and still unruled from the earlier copy -- or/clackamas: C3 (450)"
    )
    ruled = _clean(new_zones={}, baseline_new_zones=known)
    assert tripped(ruled) == []
    assert ruled["new_zones"]["detail"] == "every zone code on the map is in the rules or ruled"


def test_the_measured_lot_count_moving_trips_and_no_baseline_stays_quiet() -> None:
    checks = _clean(measured=280_000)
    assert tripped(checks) == ["lots_drift"]
    assert checks["lots_drift"]["detail"] == "289,845 -> 280,000 measured lots (-3.4%)"
    assert _clean(baseline_measured=None)["lots_drift"] == {"tripped": False, "detail": "290,000 measured lots; no earlier run to compare"}


def test_a_jurisdiction_whose_zones_moved_trips_above_the_floor_only() -> None:
    checks = _clean(zone_changes={"or/multnomah/gresham": (3_000, 20_000), "or/clackamas/tiny": (6, 6)})
    assert tripped(checks) == ["zone_changes"]
    assert checks["zone_changes"]["detail"] == "or/multnomah/gresham: 3,000 of 20,000 (15%)"
    assert _clean(zone_changes={})["zone_changes"]["detail"] == "no lots shared with an earlier copy"


def test_metro_disagreeing_with_our_delta_trips_on_recall_not_precision() -> None:
    low = {
        **CROSSCHECK,
        "counties": {
            **CROSSCHECK["counties"],
            "multnomah": {"added": {"recall": 0.5, "precision": 0.1}, "deleted": {"recall": 0.95, "precision": 0.1}},
        },
    }
    checks = _clean(crosscheck=low)
    assert tripped(checks) == ["rlis_agreement"]
    assert checks["rlis_agreement"]["detail"] == "multnomah added: recall 50%"
    assert _clean(crosscheck=None)["rlis_agreement"] == {"tripped": False, "detail": "no delta cross-check stored for this copy"}


def test_tripped_reads_a_missing_or_partial_gate_as_open() -> None:
    assert tripped(None) == []
    assert tripped({"new_zones": {"tripped": True, "detail": "x"}, "junk": {"tripped": True}}) == ["new_zones"]
