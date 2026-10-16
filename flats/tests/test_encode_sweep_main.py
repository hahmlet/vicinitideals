"""A sweep CLI smoke test over a temporary, offline provenance corpus."""

from __future__ import annotations

import json
from datetime import date

from flats.encode.sweep import __main__ as sweep_cli
from flats.provenance.store import ProvenanceStore
from flats.rules.model import CodeDocument, Layer


def test_main_sweeps_a_temporary_document_without_network_or_model(tmp_path, monkeypatch, capsys):
    layer = Layer(
        layer="or/test",
        kind="city",
        label="Test",
        code=(CodeDocument(id="chapter", url="https://example.test/code"),),
    )
    monkeypatch.setattr(sweep_cli, "load_rules", lambda *_args, **_kwargs: {"or/test": layer})

    class _Model:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.context = kwargs["context"]

        def ready(self):
            return ""

        def __call__(self, _prompt):
            return '{"found": []}'

    monkeypatch.setattr(sweep_cli, "Ollama", _Model)
    docs = tmp_path / "docs"
    ProvenanceStore(docs).save(
        "or/test/chapter.txt",
        url="https://example.test/code",
        text="A temporary zoning provision.\n",
        retrieved=date(2026, 10, 16),
    )
    out = tmp_path / "reports"

    assert sweep_cli.main(
        ["or/test", "--docs", str(docs), "--out", str(out), "--rules", str(tmp_path / "rules")]
    ) == 0

    report = json.loads((out / "or_test.json").read_text(encoding="utf-8"))
    assert report["layer"] == "or/test"
    assert report["documents"] == ["or/test/chapter.txt"]
    assert "or/test: 0 finding(s) across 1 document(s)" in capsys.readouterr().out
