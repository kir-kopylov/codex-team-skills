from __future__ import annotations

import importlib.util
import json
from decimal import Decimal

import pytest

from conftest import ROOT


SCRIPT = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "sverka-kommunalnyh-nachisleniy"
    / "scripts"
    / "reconcile.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("sverka_kommunalnyh_nachisleniy", SCRIPT)
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


@pytest.mark.parametrize("value", ["NaN", "nan", "-NaN", "sNaN", "Infinity", "-inf"])
def test_non_finite_amount_is_rejected_as_value_error(value: str) -> None:
    with pytest.raises(ValueError, match="некорректная сумма"):
        MOD.parse_amount(value, "amount")


def test_non_finite_amount_does_not_leak_decimal_error_from_reconcile() -> None:
    with pytest.raises(ValueError, match="некорректная сумма"):
        MOD.reconcile(
            {"rows": [{"period": "2026-01", "charged": "NaN", "paid": "100"}]}
        )


def test_non_finite_opening_balance_is_rejected() -> None:
    with pytest.raises(ValueError, match="некорректная сумма"):
        MOD.reconcile(
            {
                "opening_balance": float("nan"),
                "rows": [{"period": "2026-01", "charged": "100", "paid": "100"}],
            }
        )


@pytest.mark.parametrize("data", [[], None, 5, "rows", ()])
def test_non_object_root_is_rejected_as_value_error(data: object) -> None:
    with pytest.raises(ValueError, match="корень данных"):
        MOD.reconcile(data)


@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        "null",
        "5",
        '{"rows":[{"period":"2026-01","charged":"NaN","paid":"100"}]}',
        '{"rows":[{"period":"2026-01","charged":NaN,"paid":"100"}]}',
    ],
)
def test_cli_reports_structured_error_instead_of_traceback(
    payload: str, tmp_path, capsys, monkeypatch
) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(payload, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["reconcile.py", str(ledger)])
    assert MOD.main() == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error"]
    assert captured.out == ""
