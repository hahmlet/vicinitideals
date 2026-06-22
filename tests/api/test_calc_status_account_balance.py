"""Unit tests for the Account Balance factor in `_compute_calc_status`.

The factor reads `outputs.bank_account_proof` and modulates color by
Sources Gap (sources_uses status == 'fail') and Gap Adjustment presence
(passed through `data["has_gap_adjustment"]`).
"""
from __future__ import annotations

from types import SimpleNamespace as _SN

import pytest

from app.api.routers.ui_model_builder import _compute_calc_status


def _outputs(**overrides):
    base = dict(
        dscr=None,
        noi_stabilized=None,
        bank_account_proof=None,
    )
    base.update(overrides)
    return _SN(**base)


def _inputs(**overrides):
    base = dict(
        debt_terms={},
        debt_sizing_mode="",
        exit_cap_rate_pct=None,
    )
    base.update(overrides)
    return _SN(**base)


def _data(**overrides):
    base = dict(
        capital_total=1_000_000,
        uses_total=1_000_000,
        outputs=_outputs(),
        inputs=_inputs(),
        capital_modules=[],
        has_gap_adjustment=False,
    )
    base.update(overrides)
    return base


@pytest.mark.unit
def test_account_balance_ok_when_solvent_no_gap_no_adjustment():
    data = _data(outputs=_outputs(bank_account_proof={
        "is_solvent": True, "max_shortfall": "0",
        "months_simulated": 3, "proof_start": "stabilized",
    }))
    result = _compute_calc_status(data)
    ba = result["account_balance"]
    assert ba["status"] == "ok"
    assert ba["label"] == "Solvent"
    assert ba["meta"]["is_solvent"] is True


@pytest.mark.unit
def test_account_balance_warn_when_solvent_but_sources_gap_open():
    """Solvent proof on a deal with Sources < Uses → yellow."""
    data = _data(
        capital_total=800_000,
        uses_total=1_000_000,  # 200k gap
        outputs=_outputs(bank_account_proof={
            "is_solvent": True, "max_shortfall": "0",
            "months_simulated": 6, "proof_start": "co",
        }),
    )
    result = _compute_calc_status(data)
    assert result["sources_uses"]["status"] == "fail"
    ba = result["account_balance"]
    assert ba["status"] == "warn"
    assert "Sources Gap" in ba["detail"]


@pytest.mark.unit
def test_account_balance_warn_when_solvent_but_gap_adjustment_active():
    """Solvent proof on a deal masking gap with adjustments → yellow."""
    data = _data(
        has_gap_adjustment=True,
        outputs=_outputs(bank_account_proof={
            "is_solvent": True, "max_shortfall": "0",
            "months_simulated": 9, "proof_start": "co",
        }),
    )
    result = _compute_calc_status(data)
    ba = result["account_balance"]
    assert ba["status"] == "warn"
    assert "Gap Adjustment" in ba["detail"]


@pytest.mark.unit
def test_account_balance_fail_when_insolvent():
    """Insolvent proof → red (engine bug, not user-actionable)."""
    data = _data(outputs=_outputs(bank_account_proof={
        "is_solvent": False, "max_shortfall": "25000",
        "months_simulated": 6, "proof_start": "co",
    }))
    result = _compute_calc_status(data)
    ba = result["account_balance"]
    assert ba["status"] == "fail"
    assert "Insolvent" in ba["label"]
    assert "25,000" in ba["label"]
    assert ba["meta"]["max_shortfall"] == 25000.0


@pytest.mark.unit
def test_account_balance_na_when_no_proof():
    """No bank_account_proof JSON → grayed-out na status."""
    data = _data()  # outputs.bank_account_proof = None by default
    result = _compute_calc_status(data)
    ba = result["account_balance"]
    assert ba["status"] == "na"
    assert "not computed" in ba["label"].lower()


@pytest.mark.unit
def test_account_balance_contributes_to_failing_count_and_overall():
    """Insolvent factor should flip overall to warn even if other factors ok."""
    data = _data(outputs=_outputs(bank_account_proof={
        "is_solvent": False, "max_shortfall": "10000",
        "months_simulated": 3, "proof_start": "stabilized",
    }))
    result = _compute_calc_status(data)
    assert result["failing_count"] >= 1
    assert result["overall"] == "warn"
