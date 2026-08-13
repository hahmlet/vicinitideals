"""Writing found standards into a rule file without writing anything false.

A writer is the most dangerous tool in this subsystem: it is the only one that
can put a number in front of a reviewer with no human having chosen it. Every
test here is a refusal — what it will not write, and what it leaves exactly as
it found it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from flats.encode.corroborate import Finding, Verdict
from flats.encode.draft import apply, layer_path, main, plan
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

DOC = "or/multnomah/portland/33.110.txt"
LAYER = "or/multnomah/portland"

CITE = {
    "cite": "PCC 33.110.220, Table 110-4",
    "url": "https://www.portland.gov/code/33/100s/110",
    "retrieved": "2026-08-12",
}

TEXT = """33.110.220 Setbacks
Table 110-4
Standard                      RF          R5          R2.5
- Front building              20 ft.      10 ft.      10 ft.
 setback
Maximum Height                30 ft.      30 ft. [3]  35 ft.
- Garage entrance             18 ft.      18 ft.      18 ft.
 setback
[3] Additional height may be allowed. See 33.110.265.F.
"""

FILE = {
    "label": "Portland",
    "kind": "city",
    "eligible": True,
    "zones": {
        "R5": {"cite_default": CITE, "setback_front_ft": 10},
        "R2.5": {"cite_default": CITE, "setback_front_ft": 10},
    },
}


def finding(zone: str, field: str, *values: float, notes: tuple[str, ...] = ()) -> Finding:
    return Finding(
        layer=LAYER,
        zone=zone,
        field=field,
        verdict=Verdict.unencoded,
        encoded=None,
        found=tuple(values),
        quote=f"{DOC}#L6",
        notes=notes,
    )


@pytest.fixture()
def rules(tmp_path: Path) -> Path:
    root = tmp_path / "jurisdictions" / "or" / "multnomah"
    root.mkdir(parents=True)
    (root.parent / "_state.yaml").write_text(
        yaml.safe_dump({"label": "Oregon", "kind": "state", "zones": {}}), encoding="utf-8"
    )
    (root / "portland.yaml").write_text(yaml.safe_dump(FILE), encoding="utf-8")
    return tmp_path / "jurisdictions"


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    ProvenanceStore(root).save(DOC, url=CITE["url"], text=TEXT, retrieved=date(2026, 8, 12))
    return root


def run(rules: Path, store: Path, *extra: str) -> int:
    return main(["--doc", DOC, "--rules", str(rules), "--docs", str(store), LAYER, *extra])


def loaded(rules: Path) -> dict:
    return yaml.safe_load((rules / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8"))


# --- what it will write ------------------------------------------------


def test_a_standard_the_file_lacks_is_planned() -> None:
    additions, skipped = plan([finding("R5", "max_height_ft", 30)], {"R5": {"setback_front_ft"}})

    assert [(a.zone, a.field, a.value) for a in additions] == [("R5", "max_height_ft", 30)]
    assert skipped == []


def test_a_written_value_carries_the_line_it_came_from(rules: Path, store: Path) -> None:
    run(rules, store, "--apply")

    written = loaded(rules)["zones"]["R5"]["setback_garage_entrance_ft"]
    assert written["value"] == 18
    assert written["quote"].startswith(f"{DOC}#L")


def test_a_written_value_is_unsigned(rules: Path, store: Path) -> None:
    # Writing a number is not knowing it is right. The queue grows by exactly
    # what was added, and a signature is still the only thing that promotes.
    run(rules, store, "--apply")
    written = loaded(rules)["zones"]["R5"]["setback_garage_entrance_ft"]

    assert "status" not in written
    assert "reviewer" not in written


def test_the_rest_of_the_file_survives(rules: Path, store: Path) -> None:
    run(rules, store, "--apply")
    after = loaded(rules)

    assert after["label"] == "Portland"
    assert after["zones"]["R5"]["setback_front_ft"] == 10
    assert after["zones"]["R5"]["cite_default"]["cite"] == CITE["cite"]


# --- what it refuses ---------------------------------------------------


def test_it_never_overwrites_a_value_the_file_carries() -> None:
    additions, skipped = plan(
        [finding("R5", "setback_front_ft", 15)], {"R5": {"setback_front_ft"}}
    )

    assert additions == []
    assert [s.reason for s in skipped] == ["already encoded"]


def test_a_disagreement_is_not_a_gap_to_fill() -> None:
    # Only `unencoded` is writable. A value the document contradicts is a
    # reading question, and answering it mechanically picks a side.
    disagreement = Finding(LAYER, "R5", "setback_front_ft", Verdict.differs, 12, (10,), "")

    assert plan([disagreement], {}) == ([], [])


def test_two_numbers_for_one_field_are_left_alone() -> None:
    additions, skipped = plan([finding("R5", "max_height_ft", 30, 35)], {})

    assert additions == []
    assert "more than one value" in skipped[0].reason


def test_a_footnoted_number_is_never_written_as_a_standard(rules: Path, store: Path) -> None:
    # "30 ft. [3]" with "[3] Additional height may be allowed" is a base case
    # with an exit. Encoded as 30 ft. flat, a taller-but-legal building fails a
    # limit the code does not impose, and that lot goes red for good.
    additions, skipped = plan(
        [finding("R5", "max_height_ft", 30, notes=("Additional height may be allowed.",))], {}
    )

    assert additions == []
    assert "conditional" in skipped[0].reason


def test_the_conditional_height_stays_out_of_the_file(rules: Path, store: Path) -> None:
    run(rules, store, "--apply")
    after = loaded(rules)

    assert "max_height_ft" not in after["zones"]["R5"], "R5's 30 ft. carries footnote 3"
    assert after["zones"]["R2.5"]["max_height_ft"]["value"] == 35, "R2.5's 35 ft. has no exit"


def test_a_zone_with_nothing_to_inherit_is_refused() -> None:
    raw = {"zones": {"R5": {}}}
    updated, refused = apply(raw, [plan([finding("R5", "max_height_ft", 30)], {})[0][0]])

    assert "max_height_ft" not in updated["zones"]["R5"]
    assert "cite_default" in refused[0].reason


# --- the command -------------------------------------------------------


def test_it_reports_before_it_writes(rules: Path, store: Path, capsys) -> None:
    before = (rules / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8")
    code = run(rules, store)
    out = capsys.readouterr().out

    assert code == 0
    assert "--apply" in out
    assert (rules / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8") == before


def test_it_says_what_it_skipped_and_why(rules: Path, store: Path, capsys) -> None:
    run(rules, store)

    assert "conditional" in capsys.readouterr().out


def test_a_second_run_adds_nothing(rules: Path, store: Path, capsys) -> None:
    run(rules, store, "--apply")
    after_first = loaded(rules)
    capsys.readouterr()

    run(rules, store, "--apply")

    assert loaded(rules) == after_first


def test_an_unknown_layer_writes_nothing(rules: Path, store: Path) -> None:
    code = main(["--doc", DOC, "--rules", str(rules), "--docs", str(store), "or/nowhere"])

    assert code == 2


def test_the_layer_file_is_found_from_its_id(rules: Path) -> None:
    assert layer_path(rules, LAYER).name == "portland.yaml"
    assert layer_path(rules, "or").name == "_state.yaml"
