#!/usr/bin/env python3
"""Проверяет заданные связи операций; читает JSON и выводит результат без записи."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

KINDS = {"payment", "funding", "refund", "reimbursement"}
MONEY = re.compile(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,6})?\Z")


class LedgerError(ValueError):
    """Нарушение структуры или противоречащие друг другу связи."""


def require(condition, message):
    if not condition:
        raise LedgerError(message)


def fields(row, required, where):
    require(isinstance(row, dict), f"{where}: нужен объект")
    require(set(row) == set(required.split()), f"{where}: неверный набор полей")


def string(value, where, nullable=False):
    require((nullable and value is None) or
            (isinstance(value, str) and bool(value.strip())),
            f"{where}: нужна непустая строка" + (" или null" if nullable else ""))
    return value


def boolean(value, where):
    require(type(value) is bool, f"{where}: нужно true или false")
    return value


def money(value, where):
    if value is None:
        return None
    require(isinstance(value, str) and MONEY.fullmatch(value) is not None,
            f"{where}: сумма — неотрицательная десятичная строка или null")
    return Decimal(value)


def day(value, where, nullable=True):
    if nullable and value is None:
        return None
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
            f"{where}: дата должна иметь вид ГГГГ-ММ-ДД")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError(f"{where}: несуществующая дата") from exc


def amount_text(value):
    if value is None:
        return None
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def refs(value, available, where, nonempty=False):
    require(isinstance(value, list), f"{where}: нужен список")
    require(all(isinstance(item, str) for item in value), f"{where}: ссылки должны быть строками")
    require(len(value) == len(set(value)), f"{where}: повтор ссылки")
    require(not nonempty or bool(value), f"{where}: нет подтверждающего источника")
    require(all(item in available for item in value), f"{where}: отсутствующая ссылка")
    return value


def records(items, required, label, seen):
    require(isinstance(items, list), f"{label}: нужен список")
    result = {}
    for item in items:
        fields(item, required, label)
        key = string(item["id"], f"{label}.id")
        require(key not in seen, f"{label}: повтор ID {key}")
        seen.add(key)
        result[key] = item
    return result


def total(rows, cutoff=None):
    """Известная часть и полнота; неопределённая дата не скрывает факт расхода."""
    groups = defaultdict(lambda: {"known": Decimal(0), "unknown_count": 0})
    unknown_currency, unknown_date, after_cutoff, unconfirmed = [], [], [], []
    for row in rows:
        when = day(row["date"], row["id"])
        if cutoff is not None and when is not None and when > cutoff:
            after_cutoff.append(row["id"])
            continue
        currency = row["currency"]
        if currency is None:
            unknown_currency.append(row["id"])
        if cutoff is not None and when is None:
            unknown_date.append(row["id"])
        if not row["confirmed"]:
            unconfirmed.append(row["id"])
            if currency is not None:
                groups[currency]["unknown_count"] += 1
            continue
        if currency is None:
            continue
        value = money(row["amount"], row["id"])
        group = groups[currency]
        if value is None or (cutoff is not None and when is None):
            group["unknown_count"] += 1
        else:
            group["known"] += value
    return {
        "by_currency": {
            currency: {"known_amount": amount_text(group["known"]),
                       "amount": None if group["unknown_count"] else amount_text(group["known"]),
                       "unknown_count": group["unknown_count"]}
            for currency, group in sorted(groups.items())
        },
        "incomplete": bool(unknown_currency or unknown_date or unconfirmed or
                           any(g["unknown_count"] for g in groups.values())),
        "unknown_currency_ids": unknown_currency,
        "unknown_date_ids": unknown_date,
        "after_cutoff_ids": after_cutoff,
        "unconfirmed_ids": unconfirmed,
    }


def validate(data):
    """Возвращает расчёт по переданным утверждениям, не доказательство их смысла."""
    with localcontext() as context:
        context.prec = 50
        return _validate(data)


def _validate(data):
    fields(data, "schema_version cutoff parties sources expenses movements allocations claims", "реестр")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1,
            "Неизвестная версия схемы")
    cutoff = day(data["cutoff"], "cutoff", nullable=False)
    parties = data["parties"]
    require(isinstance(parties, list) and all(isinstance(p, str) and p.strip() for p in parties),
            "parties: нужен список непустых ID сторон")
    require(len(parties) == len(set(parties)), "parties: повтор ID")
    seen = set(parties)
    sources = records(data["sources"], "id locator", "sources", seen)
    for row in sources.values():
        string(row["locator"], f"{row['id']}.locator")
    expenses = records(data["expenses"],
                       "id object date amount currency confirmed source_ids", "expenses", seen)
    movements = records(data["movements"],
                        "id date amount currency kind payer payee funds_owner transaction_key confirmed source_ids",
                        "movements", seen)
    allocations = records(data["allocations"],
                          "id movement_id expense_id amount confirmed source_ids", "allocations", seen)
    claims = records(data["claims"],
                     "id expense_id applicable debtor creditor proposed_amount agreed_amount agreement_source_ids "
                     "payments_complete refunds_complete reimbursements_complete coverage_source_ids "
                     "payment_allocation_ids refund_allocation_ids reimbursement_allocation_ids", "claims", seen)

    def party(value, where):
        require(value is None or value in parties, f"{where}: неизвестная сторона")

    transactions = set()
    for row in [*expenses.values(), *movements.values()]:
        key = row["id"]
        day(row["date"], f"{key}.date")
        money(row["amount"], f"{key}.amount")
        currency = row["currency"]
        require(currency is None or (isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency)),
                f"{key}.currency: нужен трёхбуквенный код или null")
        boolean(row["confirmed"], f"{key}.confirmed")
        refs(row["source_ids"], sources, f"{key}.source_ids", row["confirmed"])
        if key in expenses:
            string(row["object"], f"{key}.object", nullable=True)
            continue
        require(isinstance(row["kind"], str) and row["kind"] in KINDS, f"{key}: неизвестный вид движения")
        for role in ("payer", "payee", "funds_owner"):
            party(row[role], f"{key}.{role}")
        transaction = string(row["transaction_key"], f"{key}.transaction_key", nullable=True)
        if transaction is not None:
            require(transaction not in transactions, f"{key}: повтор transaction_key; объедините подтверждения")
            transactions.add(transaction)

    allocated = defaultdict(Decimal)
    uncertain_allocated = set()
    for key, row in allocations.items():
        string(row["movement_id"], f"{key}.movement_id")
        string(row["expense_id"], f"{key}.expense_id")
        require(row["movement_id"] in movements, f"{key}: отсутствует движение")
        require(row["expense_id"] in expenses, f"{key}: отсутствует расход")
        boolean(row["confirmed"], f"{key}.confirmed")
        refs(row["source_ids"], sources, f"{key}.source_ids", row["confirmed"])
        value = money(row["amount"], f"{key}.amount")
        movement, expense = movements[row["movement_id"]], expenses[row["expense_id"]]
        require(movement["kind"] != "funding", f"{key}: финансирование нельзя распределять как расход или возмещение")
        require(movement["currency"] is None or expense["currency"] is None or
                movement["currency"] == expense["currency"], f"{key}: несовпадающие валюты")
        if value is not None:
            allocated[row["movement_id"]] += value
        else:
            uncertain_allocated.add(row["movement_id"])
    for key, value in allocated.items():
        movement_amount = money(movements[key]["amount"], key)
        require(movement_amount is None or value <= movement_amount,
                f"{key}: распределено больше суммы движения")

    claimed_expenses, used_allocations, outcomes = set(), set(), []
    for key, claim in claims.items():
        expense_id = claim["expense_id"]
        string(expense_id, f"{key}.expense_id")
        require(expense_id in expenses, f"{key}: отсутствует расход")
        require(expense_id not in claimed_expenses, f"{key}: несколько требований на один расход; нужна обоснованная разбивка")
        claimed_expenses.add(expense_id)
        expense = expenses[expense_id]
        applicable = boolean(claim["applicable"], f"{key}.applicable")
        for role in ("debtor", "creditor"):
            party(claim[role], f"{key}.{role}")
        proposed, agreed = (money(claim[field], f"{key}.{field}") for field in ("proposed_amount", "agreed_amount"))
        refs(claim["agreement_source_ids"], sources, f"{key}.agreement_source_ids")
        refs(claim["coverage_source_ids"], sources, f"{key}.coverage_source_ids")
        for flag in ("payments_complete", "refunds_complete", "reimbursements_complete"):
            boolean(claim[flag], f"{key}.{flag}")
        reason = []
        sums = {}
        for kind in ("payment", "refund", "reimbursement"):
            ids = refs(claim[f"{kind}_allocation_ids"], allocations, f"{key}.{kind}_allocation_ids")
            value_sum = Decimal(0)
            for allocation_id in ids:
                require(allocation_id not in used_allocations, f"{key}: распределение уже использовано другим требованием")
                used_allocations.add(allocation_id)
                allocation = allocations[allocation_id]
                movement = movements[allocation["movement_id"]]
                require(allocation["expense_id"] == expense_id and movement["kind"] == kind,
                        f"{key}: распределение не соответствует расходу или виду движения")
                when = day(movement["date"], movement["id"])
                if when is not None and when > cutoff:
                    continue
                value = money(allocation["amount"], allocation_id)
                if not allocation["confirmed"] or not movement["confirmed"]:
                    reason.append(f"{allocation_id}: связь или оплата не подтверждена")
                elif when is None or value is None or movement["amount"] is None or movement["currency"] is None:
                    reason.append(f"{allocation_id}: неизвестны дата, сумма или валюта")
                elif movement["id"] in uncertain_allocated:
                    reason.append(f"{allocation_id}: предел распределений движения не установлен")
                elif None in (movement["payer"], movement["payee"]):
                    reason.append(f"{allocation_id}: не установлены плательщик или получатель")
                elif kind == "payment" and (movement["funds_owner"] != claim["creditor"] or movement["funds_owner"] is None):
                    reason.append(f"{allocation_id}: принадлежность средств кредитору не установлена")
                elif kind == "refund" and (movement["payee"] != claim["creditor"] or movement["payee"] is None):
                    reason.append(f"{allocation_id}: возврат кредитору не установлен")
                elif kind == "reimbursement" and (movement["funds_owner"] != claim["debtor"] or movement["payee"] != claim["creditor"] or movement["funds_owner"] is None):
                    reason.append(f"{allocation_id}: направление возмещения не установлено")
                else:
                    value_sum += value
            sums[kind] = value_sum
        output = {"id": key, "expense_id": expense_id, "debtor": claim["debtor"],
                  "creditor": claim["creditor"], "currency": expense["currency"],
                  "proposed_amount": amount_text(proposed), "agreed_amount": amount_text(agreed),
                  "remaining_amount": None, "status": "unknown", "reasons": []}
        if not applicable:
            require(proposed is None and agreed is None and not claim["agreement_source_ids"] and
                    not any(claim[f"{kind}_allocation_ids"] for kind in ("payment", "refund", "reimbursement")),
                    f"{key}: неприменимое удержание содержит сумму или распределения")
            output["status"] = "not_applicable"
            outcomes.append(output)
            continue
        if None in (claim["debtor"], claim["creditor"]):
            reason.append("Не установлены стороны обязательства")
        elif claim["debtor"] == claim["creditor"]:
            reason.append("Должник совпадает с кредитором")
        if agreed is None or not claim["agreement_source_ids"]:
            reason.append("Не установлена согласованная сумма с источником")
        expense_amount = money(expense["amount"], expense_id)
        if not expense["confirmed"] or expense_amount is None or expense["currency"] is None:
            reason.append("Факт, сумма или валюта расхода не подтверждены")
        expense_date = day(expense["date"], expense_id)
        if expense_date is None or expense_date > cutoff:
            reason.append("Расход не отнесён к дате среза")
        for flag in ("payments_complete", "refunds_complete", "reimbursements_complete"):
            if not claim[flag]:
                reason.append(f"Не сверено: {flag}")
        if not claim["coverage_source_ids"]:
            reason.append("Нет источника полноты сверки на дату")
        if agreed is not None and expense_amount is not None:
            require(agreed <= expense_amount, f"{key}: согласовано больше расхода; выделите другое основание отдельно")
            if sums["payment"] < agreed:
                reason.append("Подтверждённая оплата из средств кредитора меньше согласованной суммы")
        output["reasons"] = list(dict.fromkeys(reason))
        if not reason:
            remaining = agreed - sums["refund"] - sums["reimbursement"]
            output["remaining_amount"] = amount_text(remaining)
            output["status"] = "overpaid" if remaining < 0 else "calculated"
        outcomes.append(output)
    return {"schema_version": 1, "cutoff": data["cutoff"],
            "expense_facts": total(expenses.values()),
            "expenses_as_of": total(expenses.values(), cutoff),
            "movements_as_of": {kind: total([row for row in movements.values() if row["kind"] == kind], cutoff)
                                for kind in sorted(KINDS)},
            "unconfirmed_ids": [row["id"] for row in [*expenses.values(), *movements.values(), *allocations.values()] if not row["confirmed"]],
            "claims": outcomes}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"JSON: повтор поля {key}")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Абсолютный путь к JSON в рабочем проекте")
    args = parser.parse_args()
    try:
        path = Path(args.input)
        require(path.is_absolute(), "Нужен абсолютный путь входа")
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        print(json.dumps(validate(data), ensure_ascii=False, indent=2))
    except (LedgerError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
