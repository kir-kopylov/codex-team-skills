#!/usr/bin/env python3
"""Сверяет начисления и оплаты точной десятичной арифметикой."""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


CENT = Decimal("0.01")


def parse_amount(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field}: ожидалась сумма")
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    text = re.sub(r"[₽рРруб\.]*$", "", text, flags=re.IGNORECASE).strip()
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{field}: некорректная сумма {value!r}") from exc


def money(value: Decimal) -> str:
    return f"{value.quantize(CENT):.2f}"


def reconcile(data: dict) -> dict:
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("rows: ожидался непустой список")

    seen: set[str] = set()
    charged_total = Decimal("0")
    paid_total = Decimal("0")
    normalized_rows = []

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"rows[{index}]: ожидался объект")
        period = str(row.get("period", "")).strip()
        if not period:
            raise ValueError(f"rows[{index}].period: обязательное поле")
        if period in seen:
            raise ValueError(f"повторяющийся период: {period}")
        seen.add(period)

        charged = parse_amount(row.get("charged"), f"rows[{index}].charged")
        paid = parse_amount(row.get("paid"), f"rows[{index}].paid")
        if charged < 0 or paid < 0:
            raise ValueError(f"rows[{index}]: начисление и оплата не могут быть отрицательными")
        charged_total += charged
        paid_total += paid
        normalized_rows.append(
            {"period": period, "charged": money(charged), "paid": money(paid)}
        )

    has_opening = "opening_balance" in data
    opening = parse_amount(data["opening_balance"], "opening_balance") if has_opening else Decimal("0")
    closing = opening + charged_total - paid_total
    if closing > 0:
        status = "underpayment"
    elif closing < 0:
        status = "overpayment"
    else:
        status = "settled"

    return {
        "basis": "account_balance" if has_opening else "shown_period_only",
        "opening_balance": money(opening) if has_opening else None,
        "charged_total": money(charged_total),
        "paid_total": money(paid_total),
        "closing_difference": money(closing),
        "absolute_difference": money(abs(closing)),
        "status": status,
        "period_from": normalized_rows[0]["period"],
        "period_to": normalized_rows[-1]["period"],
        "rows": normalized_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", help="Путь к JSON или - для stdin")
    args = parser.parse_args()
    try:
        if args.ledger == "-":
            data = json.load(sys.stdin)
        else:
            data = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
        result = reconcile(data)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
