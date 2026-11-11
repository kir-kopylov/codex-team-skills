"""Проверки сверки выручки на вымышленных источниках."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


SKILL = Path(__file__).resolve().parents[1] / "plugins/team-skills/skills/sverka-rashodov-po-istochnikam"
SCRIPT = SKILL / "scripts/reconcile_ehous_revenue.py"
EXAMPLE = SKILL / "assets/ehous/revenue-example.json"


@pytest.fixture
def packet():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def invoke(source):
    return subprocess.run([sys.executable, str(SCRIPT), str(source)], capture_output=True,
                          text=True, encoding="utf-8", timeout=15)


def run(tmp_path, packet):
    source = tmp_path / "revenue.json"
    source.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    result = invoke(source)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_documented_example_has_three_independent_totals():
    original = EXAMPLE.read_bytes()
    result = invoke(EXAMPLE)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    totals = output["totals_by_currency"][0]
    assert totals["currency"] == "KZT"
    assert totals["before_commission"]["amount"] == "130000"
    assert totals["after_commission"]["amount"] == "109600"
    assert totals["confirmed_payouts"] == {
        "amount": None, "known_amount": "85000", "unknown_rows": 1, "complete": False,
    }
    assert totals["report_comparable"]["amount"] == "125500"
    assert totals["report_minus_after"]["amount"] == "15900"
    first, second = output["rows"]
    assert first["report_minus_stated_basis"] == "0"
    assert (first["report_minus_after"], second["report_minus_after"]) == ("15000", "900")
    assert second["ehous_rows"][0]["full"]["amount"] == "90000"
    assert (second["included_nights"], second["future_nights"]) == (2, 2)
    assert second["before_commission"] == "30000"  # Цены двух ночей различаются.
    assert second["confirmed_payouts"] is None
    assert second["other_charges"][0]["amount"] == "4000"
    assert output["totals_by_object"][1]["after_commission"]["amount"] == "24600"
    assert EXAMPLE.read_bytes() == original


def test_missing_and_extra_rows_are_checked_in_both_directions(tmp_path, packet):
    booking = packet["ehous"]["rows"][0]
    statement = packet["report"]["rows"][0]
    packet["report"]["rows"].append(dict(statement, id="100003"))  # Отчёт без записи в базе.
    packet["ehous"]["rows"].append(dict(booking, id="100004"))  # Запись базы без строки отчёта.
    packet["report"]["rows"].append(dict(statement, id="100005", status="Отмена"))
    packet["ehous"]["rows"].append(dict(booking, id="100005", status="Отмена", eligible=False))
    output = run(tmp_path, packet)
    assert output["counts"]["missing_in_ehous"] == 1
    assert output["counts"]["missing_in_report"] == 1
    assert output["counts"]["extra_in_report"] == 1
    assert not output["ehous_coverage_complete"]
    total = output["totals_by_currency"][0]
    assert total["before_commission"]["amount"] is None
    assert total["before_commission"]["known_amount"] == "230000"
    assert total["report_minus_after"]["amount"] is None
    assert output["rows"][-1]["included"] is False


def test_duplicates_and_metadata_mismatches_block_the_dependent_totals(tmp_path, packet):
    booking = packet["ehous"]["rows"][0]
    packet["ehous"]["rows"].append(dict(booking, source="Учебный архив, тот же номер"))
    packet["report"]["rows"][1]["channel"] = "Другой учебный канал"
    output = run(tmp_path, packet)
    first, second = output["rows"]
    assert len(first["ehous_rows"]) == 2
    assert first["before_commission"] is None
    assert first["confirmed_payouts"] == "85000"  # Выписка связана с номером и объектом отчёта.
    assert second["report_minus_after"] is None
    assert "канал" in " ".join(second["issues"])
    assert output["totals_by_currency"][0]["before_commission"]["known_amount"] == "30000"


def test_historical_cutoff_requires_a_dated_source(tmp_path, packet):
    packet["ehous"]["as_of"] = None
    first, second = packet["ehous"]["rows"]
    first["history"] = {"date": "2030-06-20", "source": "Учебная выгрузка первой заявки на срез"}
    second["edited_at"] = "2030-06-22T10:00:00"
    output = run(tmp_path, packet)
    assert not output["ehous_coverage_complete"]
    assert output["rows"][0]["after_commission"] == "85000"
    assert output["rows"][1]["after_commission"] is None
    assert output["rows"][0]["confirmed_payouts"] == "85000"
    assert "дату среза" in " ".join(output["rows"][1]["issues"])

    second["history"] = {"date": "2030-06-20", "source": "Учебная восстановленная запись на срез"}
    recovered = run(tmp_path, packet)
    assert recovered["rows"][1]["after_commission"] == "24600"
    assert recovered["totals_by_currency"][0]["after_commission"]["amount"] is None


@pytest.mark.parametrize(("unit", "value", "expected"), [
    ("percent", "15", "85000"),
    ("fraction", "0.15", "85000"),
    (None, "0.15", None),
])
def test_rate_units_are_explicit(tmp_path, packet, unit, value, expected):
    packet["ehous"]["rows"][0]["commission"] = {
        "kind": "rate", "value": value, "unit": unit, "source": "Учебное подтверждение ставки",
    }
    row = run(tmp_path, packet)["rows"][0]
    assert row["before_commission"] == "100000"
    assert row["after_commission"] == expected
    assert row["confirmed_payouts"] == "85000"


def test_rounding_per_booking_and_no_second_deduction(tmp_path, packet):
    first, second = packet["ehous"]["rows"]
    first["full"].update(basis="net", amount="85000")
    second["accrual"] = {"basis": "gross", "amount": "100.50", "source": "Учебное начисление на дату"}
    second["commission"] = {"kind": "rate", "value": "1", "unit": "percent", "source": "Учебная ставка"}
    second["rounding"] = {"decimals": 2, "mode": "half_even", "source": "Учебное правило округления"}
    first_result, second_result = run(tmp_path, packet)["rows"]
    assert (first_result["before_commission"], first_result["after_commission"]) == ("100000", "85000")
    assert (second_result["commission"], second_result["after_commission"]) == ("1", "99.5")


def test_missing_night_or_unknown_report_basis_is_not_inferred(tmp_path, packet):
    del packet["ehous"]["rows"][1]["nightly"]["dates"]["2030-06-20"]
    packet["report"]["rows"][0].update(basis=None, amount="85000")
    packet["report"]["rows"][1].update(period="full", amount="90000")
    first, second = run(tmp_path, packet)["rows"]
    assert first["after_commission"] == "85000"
    assert first["report_minus_after"] is None  # Совпадение чисел не устанавливает основание.
    assert second["before_commission"] is None  # Сумма всей брони не делится по умолчанию.
    assert second["report_minus_after"] is None


def test_unknown_period_start_only_reconciles_listed_bookings(tmp_path, packet):
    packet["scope"]["from"] = None
    first, second = packet["ehous"]["rows"]
    first["accrual"] = copy.deepcopy(first["full"])
    second["accrual"] = {"amount": "30000", "basis": "gross", "source": "Учебное начисление на дату"}
    packet["ehous"]["rows"].append(dict(first, id="100003"))
    output = run(tmp_path, packet)
    assert [row["booking_id"] for row in output["rows"]] == ["100001", "100002"]
    assert not output["ehous_coverage_complete"]
    gross = output["totals_by_currency"][0]["before_commission"]
    assert gross["amount"] is None
    assert gross["known_amount"] == "130000"


def test_receipt_group_is_allocated_once_and_later_and_other_payments_stay_separate(tmp_path, packet):
    doc = packet["payments"][0]
    doc["amount"] = "90000"
    doc["allocations"].append(dict(booking_id="100002", object="Учебная Б", amount="5000", source="Учебная разбивка"))
    packet["payments"].append(dict(doc, id="поздний", date="2030-06-21"))
    packet["payments"].append(dict(doc, id="залог", kind="deposit", allocations=[]))
    output = run(tmp_path, packet)
    assert output["totals_by_currency"][0]["confirmed_payouts"]["known_amount"] == "90000"
    assert output["totals_by_currency"][0]["confirmed_payouts"]["amount"] is None
    assert [row["confirmed_payouts"] for row in output["rows"]] == ["85000", "5000"]
    assert [row["id"] for row in output["later_payments"]] == ["поздний"]
    assert [row["id"] for row in output["other_payments"]] == ["залог"]


def test_duplicate_receipt_is_disputed_and_does_not_double_count(tmp_path, packet):
    packet["payments"].append(copy.deepcopy(packet["payments"][0]))
    output = run(tmp_path, packet)
    assert output["totals_by_currency"][0]["confirmed_payouts"]["amount"] is None
    assert len(output["unresolved_payments"]) == 2
    assert all(not row["payout_documents"] for row in output["rows"])
    assert output["rows"][0]["confirmed_payouts"] is None
    assert output["totals_by_currency"][0]["after_commission"]["amount"] == "109600"


def test_invalid_amount_is_reported_without_a_result(tmp_path, packet):
    packet["ehous"]["rows"][0]["full"]["amount"] = 100000
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps(packet), encoding="utf-8")
    result = invoke(source)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "десятичная строка" in json.loads(result.stderr)["error"]


@pytest.mark.skipif(not shutil.which("pwsh"), reason="Для проверки считывателя нужен PowerShell 7")
@pytest.mark.parametrize(("args", "reason"), [
    ([], "Без начала периода укажите номера заявок"),
    (["-From", "2030-06-01"], "Для проверки периода укажите номера объектов"),
])
def test_reader_requires_an_explicit_read_scope(args, reason):
    reader = SKILL / "scripts/read-ehous-revenue.ps1"
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(reader), "-Through", "2030-06-20", *args,
         "-ConfigPath", "absent-profile.json"],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode != 0
    assert reason in result.stderr
    assert "Resolve-Path" not in result.stderr
