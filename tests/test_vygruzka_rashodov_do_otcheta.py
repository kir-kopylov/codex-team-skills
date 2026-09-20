# -*- coding: utf-8 -*-
"""Регресс-тесты нормализатора выгрузки 1С.

Инвариант: сумма берется по своему заголовку, а адрес квартиры сопоставляется
целым значением. Обе ошибки раньше молча портили данные — отчет выглядел
готовым, а числа и привязка к квартире были чужие.
"""
from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/team-skills/skills/vygruzka-rashodov-do-otcheta/scripts/normalize_1c_expenses.py"


@pytest.fixture(scope="module")
def normalizer():
    spec = importlib.util.spec_from_file_location("normalize_1c_expenses", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["normalize_1c_expenses"] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop("normalize_1c_expenses", None)


def test_amount_column_wins_over_category_header(normalizer):
    # `Статья расходов` содержит подстроку `расход`, но сумма лежит в `Сумма`.
    mapping = normalizer.map_columns(["Статья расходов", "Сумма", "Квартира"])
    assert mapping["amount"] == 1
    assert mapping["description"] == 0
    assert mapping["apartment"] == 2


def test_typical_turnover_headers_keep_their_columns(normalizer):
    headers = ["Период", "Счет Дт", "Счет Кт", "Контрагент", "Договор", "Документ", "Содержание", "Сумма", "Адрес"]
    mapping = normalizer.map_columns(headers)
    assert mapping == {
        "operation_date": 0,
        "account_debit": 1,
        "account_credit": 2,
        "counterparty": 3,
        "contract": 4,
        "document": 5,
        "description": 6,
        "amount": 7,
        "apartment": 8,
    }


def test_category_first_export_keeps_real_amounts(normalizer, tmp_path):
    source = tmp_path / "vygruzka.csv"
    source.write_text(
        "Статья расходов;Сумма;Квартира\nУборка;15000,00;Квартира 1\nИнтернет;3200,50;Квартира 2\n",
        encoding="utf-8",
    )
    rows, _ = normalizer.normalize_rows(normalizer.load_input(source), [])
    assert [row["amount"] for row in rows] == ["15000.00", "3200.50"]
    assert [row["apartment"] for row in rows] == ["Квартира 1", "Квартира 2"]


def test_address_prefix_does_not_steal_row(normalizer):
    addresses = ["Адрес 1", "Адрес 10"]
    assert normalizer.match_address("Уборка | 15000 | Адрес 10", addresses) == "Адрес 10"
    assert normalizer.match_address("Уборка | 15000 | Адрес 1", addresses) == "Адрес 1"
    # Порядок в списке адресов не должен менять результат.
    assert normalizer.match_address("Уборка | 15000 | Адрес 10", list(reversed(addresses))) == "Адрес 10"


def test_summary_keeps_apartment_totals_apart(normalizer, tmp_path):
    source = tmp_path / "vygruzka.csv"
    source.write_text(
        "Статья расходов;Сумма;Объект\nУборка;15000,00;Адрес 10\nУборка;2000,00;Адрес 1\n",
        encoding="utf-8",
    )
    rows, _ = normalizer.normalize_rows(normalizer.load_input(source), ["Адрес 1", "Адрес 10"])
    totals = {row["apartment"]: Decimal(row["amount"]) for row in normalizer.build_summary(rows)}
    assert totals == {"Адрес 10": Decimal("15000.00"), "Адрес 1": Decimal("2000.00")}
