from __future__ import annotations

import importlib.util
from decimal import Decimal

import pytest

from conftest import ROOT


SCRIPT = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "reconcile-utility-payments"
    / "scripts"
    / "reconcile.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("reconcile_utility_payments", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MOD = _load_module()


def test_parse_amount_accepts_russian_money_format() -> None:
    assert MOD.parse_amount("8 153,34 ₽", "amount") == Decimal("8153.34")


def test_reconcile_without_opening_marks_period_only() -> None:
    result = MOD.reconcile(
        {
            "rows": [
                {"period": "2026-01", "charged": "100,10", "paid": "90,00"},
                {"period": "2026-02", "charged": "50,20", "paid": "10,00"},
            ]
        }
    )
    assert result["basis"] == "shown_period_only"
    assert result["closing_difference"] == "50.30"
    assert result["status"] == "underpayment"


def test_explicit_opening_credit_can_settle_balance() -> None:
    result = MOD.reconcile(
        {
            "opening_balance": "-100,00",
            "rows": [{"period": "2026-01", "charged": "150,00", "paid": "50,00"}],
        }
    )
    assert result["basis"] == "account_balance"
    assert result["closing_difference"] == "0.00"
    assert result["status"] == "settled"


def test_duplicate_period_is_rejected() -> None:
    with pytest.raises(ValueError, match="повторяющийся период"):
        MOD.reconcile(
            {
                "rows": [
                    {"period": "2026-01", "charged": "100", "paid": "0"},
                    {"period": "2026-01", "charged": "100", "paid": "0"},
                ]
            }
        )


def test_negative_charged_or_paid_is_rejected() -> None:
    with pytest.raises(ValueError, match="не могут быть отрицательными"):
        MOD.reconcile(
            {"rows": [{"period": "2026-01", "charged": "-1", "paid": "0"}]}
        )
