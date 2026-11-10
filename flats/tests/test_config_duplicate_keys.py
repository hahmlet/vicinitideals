"""No YAML file under flats/config may repeat a key in one mapping.

PyYAML keeps the LAST of two equal keys without a word, so a second
``allow_thin:`` or ``notes:`` silently replaces the first. Both values were
true / prose when FOLLOWUPS 167 found them (Gresham 10.1100, the Gladstone
zoning layer), but the same slip on a standard would drop a reading with no
trace. This scan refuses any repeat, wherever it sits.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that records every key repeated within one mapping."""

    repeats: list[str]


def _mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False):
    seen: dict[object, int] = {}
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            hash(key)
        except TypeError:
            continue
        line = key_node.start_mark.line + 1
        if key in seen:
            loader.repeats.append(f"L{line}: {key!r} (first at L{seen[key]})")
        else:
            seen[key] = line
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _repeats(text: str) -> list[str]:
    loader = _StrictLoader(text)
    loader.repeats = []
    try:
        loader.get_single_data()
    finally:
        loader.dispose()
    return loader.repeats


def test_the_scan_catches_a_repeated_key() -> None:
    assert _repeats("a:\n  b: 1\n  b: 2\n") == ["L3: 'b' (first at L2)"]
    assert _repeats("- {x: 1}\n- {x: 2}\n") == []


@pytest.mark.parametrize(
    "path",
    sorted(CONFIG.rglob("*.y*ml")),
    ids=lambda p: p.relative_to(CONFIG).as_posix(),
)
def test_no_config_file_repeats_a_key(path: Path) -> None:
    assert _repeats(path.read_text(encoding="utf-8")) == []
