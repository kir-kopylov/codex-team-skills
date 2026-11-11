#!/usr/bin/env python3
"""Сверяет строки отчёта и заявки eHous по подтверждённым источникам."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
import json
from pathlib import Path
import re
import sys

from check_ledger import LedgerError, amount_text, day, money, require, string, unique_object


DIMENSIONS = dict(object="объект", currency="валюта", channel="канал", status="статус",
                  arrival="дата заезда", departure="дата выезда", nights="число ночей")
METRICS = ("before_commission", "after_commission", "confirmed_payouts", "report_comparable", "report_minus_after")
OTHER = {"advance", "deposit", "refund", "penalty", "other"}
ROUNDING = {"half_up": ROUND_HALF_UP, "half_even": ROUND_HALF_EVEN}


def shape(row, required, optional, label):
    require(isinstance(row, dict), f"{label} — нужен объект")
    require(set(required.split()) <= row.keys() <= set((required + " " + optional).split()),
            f"{label} — неверный набор полей")
    return row


def items(value, label):
    require(isinstance(value, list), f"{label} — нужен список")
    return value


def timestamp(value, label):
    string(value, label)
    require(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value) is not None,
            f"{label} — нужна дата со временем")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError(f"{label} — неверная дата или время") from exc


def currency(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Z]{3}", value) is not None,
            "currency — нужен трёхбуквенный код валюты")


def amount(value, label):
    result = money(value, label)
    require(result is not None, f"{label} — нужна сумма")
    return result


def read_amount(entry, label):
    shape(entry, "amount basis source", "", label)
    require(entry["basis"] in ("gross", "net", None), f"{label} — неизвестный вид суммы")
    string(entry["source"], label + ".source")
    return money(entry["amount"], label + ".amount"), entry["basis"]


def rounding_rule(places, mode):
    require(type(places) is int and 0 <= places <= 6, "decimals — от 0 до 6 знаков")
    require(isinstance(mode, str) and mode in ROUNDING, "Неизвестное правило округления")
    return Decimal(1).scaleb(-places), ROUNDING[mode]


def read_rows(rows, is_booking):
    groups = defaultdict(list)
    for row in items(rows, "rows"):
        shape(
            row, "id object currency source " + ("eligible full" if is_booking else "amount basis period"),
            "channel status arrival departure nights " +
            ("history edited_at accrual nightly commission payout_coverage_source other_charges rounding" if is_booking else ""),
            "заявка" if is_booking else "строка отчёта",
        )
        for key in ("id", "object", "source"):
            string(row[key], key)
        currency(row["currency"])
        for key in ("arrival", "departure"):
            day(row.get(key), key)
        for key in ("channel", "status"):
            string(row.get(key), key, nullable=True)
        nights = row.get("nights")
        require(nights is None or type(nights) is int and nights >= 0, "nights — нужно целое число ночей или null")
        if is_booking:
            require(row["eligible"] is None or type(row["eligible"]) is bool,
                    "eligible — нужно true, false или null")
            for key in ("full", "accrual"):
                if row.get(key) is not None:
                    read_amount(row[key], key)
            string(row.get("payout_coverage_source"), "payout_coverage_source", nullable=True)
            for charge_row in items(row.get("other_charges", []), "other_charges"):
                shape(charge_row, "kind amount source", "date", "прочее начисление")
                require(isinstance(charge_row["kind"], str) and charge_row["kind"] in OTHER,
                        "Неизвестный вид прочего начисления")
                money(charge_row["amount"], "other_charges.amount")
                string(charge_row["source"], "other_charges.source")
                day(charge_row.get("date"), "other_charges.date")
        else:
            read_amount({key: row[key] for key in ("amount", "basis", "source")}, "сумма отчёта")
            require(row["period"] in ("scope", "full", None), "period — нужен scope, full или null")
        groups[row["id"]].append(row)
    return groups


def dated(row, through, snapshot_dated):
    history = row.get("history")
    if history is not None:
        shape(history, "date source", "", "history")
        string(history["source"], "history.source")
        if day(history["date"], "history.date", nullable=False) == through:
            return True
    edited = row.get("edited_at")
    return snapshot_dated and (edited is None or timestamp(edited, "edited_at").date() <= through)


def period_amount(row, arrival, first, stop, whole):
    if row.get("accrual") is not None:
        value, basis = read_amount(row["accrual"], "accrual")
        return value, basis, row["accrual"]["source"]
    if whole and row["full"] is not None:
        value, basis = read_amount(row["full"], "full")
        if value is not None and basis is not None:
            return value, basis, row["full"]["source"]
    nightly = row.get("nightly")
    if nightly is None or first is None:
        return None, None, None

    shape(nightly, "basis source dates", "", "nightly")
    string(nightly["source"], "nightly.source")
    require(nightly["basis"] in ("gross", "net"), "nightly.basis — нужен gross или net")
    require(isinstance(nightly["dates"], dict), "nightly.dates — нужны суммы по датам")
    prices = {day(key, "дата ночи", nullable=False): money(value, "цена ночи")
              for key, value in nightly["dates"].items()}
    # Нужна подтверждённая цена каждой ночи в окне. Будущая часть остаётся отдельно.
    if first < arrival or stop <= first:
        return None, None, None
    in_scope = [value for key, value in prices.items() if first <= key < stop]
    if len(in_scope) != (stop - first).days or None in in_scope:
        return None, None, None
    return sum(in_scope, Decimal(0)), nightly["basis"], nightly["source"]


def charge(entry, gross, quant, rounding):
    if entry is None:
        return None
    shape(entry, "kind value source", "unit", "commission")
    string(entry["source"], "commission.source")
    value = money(entry["value"], "commission.value")
    require(entry["kind"] in ("amount", "rate"), "commission.kind — нужен amount или rate")
    if value is None:
        return None
    if entry["kind"] == "rate":
        unit = entry.get("unit")
        if unit not in ("percent", "fraction") or gross is None:
            return None
        rate = value / 100 if unit == "percent" else value
        require(rate <= 1, "Ставка комиссии больше 100 процентов")
        value = gross * rate
    return value.quantize(quant, rounding=rounding)


def empty_accrual(included=None):
    return dict(included=included, included_nights=None, future_nights=None, whole=False,
                amount_source=None, before_commission=None, commission=None, after_commission=None)


def compute_booking(row, objects, first_day, through, snapshot_dated, quant, rounding, issues):
    result = empty_accrual()
    if not dated(row, through, snapshot_dated):
        issues.append("Состояние заявки на дату среза не подтверждено.")
        return result
    if row["object"] not in objects or row["eligible"] is False:
        return empty_accrual(included=False)
    start, end = day(row.get("arrival"), "arrival"), day(row.get("departure"), "departure")
    if start is not None and end is not None and start <= end:
        before_scope = first_day is not None and (end < first_day or start < end == first_day)
        if start > through or before_scope:
            return empty_accrual(included=False)
    if (row["eligible"] is None or start is None or end is None or end < start
            or (end == start and row.get("accrual") is None)
            or (row.get("nights") is not None and row["nights"] != (end - start).days)):
        issues.append("Статус проживания, даты или число ночей требуют проверки.")
        return result

    first = None if first_day is None else max(first_day, start)
    stop = min(end, through + timedelta(days=1))
    whole = first == start and stop == end
    result.update(included=True, whole=whole, included_nights=None if first is None else (stop - first).days,
                  future_nights=(end - stop).days)
    value, basis, source = period_amount(row, start, first, stop, whole)
    if value is None or basis is None:
        issues.append("Начисление за нужный период или вид суммы не подтверждены.")
        return result
    value = value.quantize(quant, rounding=rounding)
    fee = charge(row.get("commission"), value if basis == "gross" else None, quant, rounding)
    result.update(amount_source=source, commission=fee)
    if basis == "net":
        # Документированная чистая сумма уже учитывает комиссию.
        result["after_commission"] = value
        if fee is not None:
            result["before_commission"] = value + fee
    else:
        result["before_commission"] = value
        if fee is None:
            issues.append("Размер комиссии, единицы ставки или её применимость не подтверждены.")
        elif fee > value:
            issues.append("Комиссия больше начисления за период.")
        else:
            result["after_commission"] = value - fee
    return result


def payout_index(payments, through):
    confirmed = defaultdict(list)
    disputed = set()
    later = []
    separate = []
    unresolved = []
    seen = Counter()
    for doc in items(payments, "payments"):
        shape(doc, "id date recipient currency amount source kind allocations", "", "платёж")
        for field in ("id", "recipient", "source"):
            string(doc[field], "payments." + field)
        seen[doc["id"]] += 1
    for doc in payments:
        value = amount(doc["amount"], "payments.amount")
        currency(doc["currency"])
        when = day(doc["date"], "payments.date", nullable=False)
        require(isinstance(doc["kind"], str) and doc["kind"] in OTHER | {"rent"}, "Неизвестный вид платежа")
        allocations = items(doc["allocations"], "payments.allocations")
        if doc["kind"] != "rent":
            separate.append(doc)
            continue
        if when > through:
            later.append(doc)
            continue
        split = {}
        for allocation in allocations:
            shape(allocation, "booking_id object amount source", "", "часть платежа")
            for field in ("booking_id", "object", "source"):
                string(allocation[field], "allocations." + field)
            key = allocation["booking_id"], allocation["object"], doc["currency"]
            require(key not in split, "Повтор привязки части одного платежа к заявке")
            split[key] = amount(allocation["amount"], "allocations.amount"), allocation["source"]
        assigned = sum((paid for paid, _ in split.values()), Decimal(0))
        require(assigned <= value, "Распределено больше, чем подтверждено платёжным документом")
        if seen[doc["id"]] > 1:
            unresolved.append({"payment": doc, "reason": "Повтор идентификатора платежа."})
            disputed.update(split)
            continue
        if assigned < value or not split:
            unresolved.append({"payment": doc, "reason": "Часть платежа не связана с арендой в периоде."})
        for key, (paid, source) in split.items():
            confirmed[key].append({
                "payment_id": doc["id"], "date": doc["date"], "recipient": doc["recipient"],
                "amount": paid, "source": doc["source"], "allocation_source": source,
            })
    return confirmed, later, separate, unresolved, disputed


def metric(rows, name, covered):
    known = [row[name] for row in rows if row[name] is not None]
    unknown = len(rows) - len(known)
    complete = covered and unknown == 0
    total = sum(known, Decimal(0)) if known or complete else None
    return dict(amount=total if complete else None, known_amount=total, unknown_rows=unknown, complete=complete)


def summarize(rows, inventory_complete, report_complete, payouts_complete):
    by_currency = defaultdict(list)
    by_object = defaultdict(list)
    for row in rows:
        if row["included"] is not False and row["object"] is not None:
            by_currency[row["currency"]].append(row)
            by_object[(row["object"], row["currency"])].append(row)

    def totals(group):
        coverage = {
            "confirmed_payouts": payouts_complete and all(row["payout_coverage_source"] for row in group),
            "report_comparable": report_complete,
            "report_minus_after": report_complete,
        }
        return {name: metric(group, name, inventory_complete and coverage.get(name, True)) for name in METRICS}

    return ([dict(currency=code, **totals(group)) for code, group in sorted(by_currency.items())],
            [dict(object=obj, currency=code, **totals(group)) for (obj, code), group in sorted(by_object.items())])


def reconcile(packet):
    shape(packet, "schema_version scope ehous report payments", "", "пакет сверки")
    require(type(packet["schema_version"]) is int and packet["schema_version"] == 1, "Нужна версия входа 1")
    scope = shape(packet["scope"], "objects from through timezone decimals rounding", "", "scope")
    objects = set(string(obj, "scope.objects") for obj in items(scope["objects"], "scope.objects"))
    require(bool(objects), "Укажите хотя бы один объект")
    first = day(scope["from"], "scope.from")
    through = day(scope["through"], "scope.through", nullable=False)
    require(through < date.max and (first is None or first <= through), "Недопустимый период сверки")
    string(scope["timezone"], "scope.timezone")
    default_quant, default_rounding = rounding_rule(scope["decimals"], scope["rounding"])
    ehous = shape(packet["ehous"], "source read_at as_of coverage_source rows", "", "ehous")
    report = shape(packet["report"], "source coverage_source rows", "limitations", "report")
    for data in (ehous, report):
        string(data["source"], "source")
        string(data["coverage_source"], "coverage_source", nullable=True)
    string(report.get("limitations"), "report.limitations", nullable=True)
    observed = timestamp(ehous["read_at"], "ehous.read_at")
    as_of = day(ehous["as_of"], "ehous.as_of")
    require(as_of is None or as_of <= observed.date(), "Дата снимка eHous позже времени его чтения")
    snapshot_dated = (as_of or observed.date()) == through
    inventory_complete = first is not None and snapshot_dated and ehous["coverage_source"] is not None
    report_complete = report["coverage_source"] is not None
    bookings = read_rows(ehous["rows"], is_booking=True)
    statements = read_rows(report["rows"], is_booking=False)
    payouts, later, separate, unresolved, disputed_payouts = payout_index(packet["payments"], through)

    rows = []
    counts = dict(matched=0, partially_matched=0, missing_in_report=0, missing_in_ehous=0,
                  extra_in_report=0, disputed=0)
    for booking_id in sorted(bookings.keys() | statements.keys()):
        db_matches, report_matches = bookings.get(booking_id, []), statements.get(booking_id, [])
        if first is None and not report_matches:
            continue
        if all(row["object"] not in objects for row in db_matches + report_matches):
            continue

        db = db_matches[0] if len(db_matches) == 1 else None
        entry = report_matches[0] if len(report_matches) == 1 else None
        issues = []
        if len(db_matches) > 1:
            issues.append("В eHous несколько записей с этим номером, включая возможный дубль в архиве.")
        if len(report_matches) > 1:
            issues.append("В отчёте несколько строк с этим номером.")
        if not db_matches:
            counts["missing_in_ehous"] += 1
            issues.append("Номер из отчёта не найден в проверенных данных eHous.")

        result = empty_accrual()
        quant, rounding = default_quant, default_rounding
        if db is not None:
            if db.get("rounding") is not None:
                rule = shape(db["rounding"], "decimals mode source", "", "rounding")
                string(rule["source"], "rounding.source")
                quant, rounding = rounding_rule(rule["decimals"], rule["mode"])
            result = compute_booking(db, objects, first, through, snapshot_dated, quant, rounding, issues)
        if result["included"] is None:
            inventory_complete = False
        if result["included"] is False and report_matches:
            counts["extra_in_report"] += 1
            issues.append("Строка отчёта относится к исключённой заявке или лежит вне периода и объектов.")
        if result["included"] is True and not report_matches:
            counts["missing_in_report"] += 1
            issues.append("Подтверждённая заявка eHous отсутствует в отчёте.")

        # Датированная запись eHous задаёт объект для начислений. При спорном снимке
        # оставляем видимым объект отчёта для сопоставления независимой выписки.
        chosen = db if db is not None and (result["included"] is not None or entry is None) else entry
        obj = chosen["object"] if chosen is not None and chosen["object"] in objects else None
        code = chosen["currency"] if obj is not None else None
        payout_key = booking_id, obj, code
        docs = payouts.pop(payout_key, []) if result["included"] is not False else []
        same_booking = db is not None and db["object"] == obj and db["currency"] == code
        coverage_allowed = same_booking and result["included"] is not False and payout_key not in disputed_payouts
        paid_coverage = db.get("payout_coverage_source") if coverage_allowed else None
        if payout_key in disputed_payouts:
            issues.append("Есть спорный платёж по заявке.")
        paid = sum((doc["amount"] for doc in docs), Decimal(0)) if docs or paid_coverage else None
        stated_delta = None
        net_delta = None
        comparable = None
        if db is not None and entry is not None and result["included"] is not False:
            different = [label for key, label in DIMENSIONS.items() if entry.get(key) is not None
                         and db.get(key) is not None and db[key] != entry[key]]
            unknown = [label for key, label in DIMENSIONS.items() if entry.get(key) is None or db.get(key) is None]
            if different:
                issues.append("Различаются поля отчёта и eHous — " + ", ".join(different) + ".")
            elif result["included"] is True:
                counts["partially_matched" if unknown else "matched"] += 1
                if unknown:
                    issues.append("Не сверены поля — " + ", ".join(unknown) + ".")
                value, basis = money(entry["amount"], "сумма отчёта"), entry["basis"]
                compatible = entry["period"] == "scope" or (entry["period"] == "full" and result["whole"])
                if value is None or basis is None or not compatible:
                    issues.append("Сумма отчёта, её вид или период не подтверждены для сравнения.")
                else:
                    corresponding = result["before_commission"] if basis == "gross" else result["after_commission"]
                    value = value.quantize(quant, rounding=rounding)
                    comparable = value
                    if corresponding is not None:
                        stated_delta = value - corresponding
                        if stated_delta:
                            issues.append("Сумма отчёта отличается от начисления на том же основании.")
                    if result["after_commission"] is not None:
                        net_delta = value - result["after_commission"]
                    if basis == "gross":
                        issues.append("Сумма отчёта дана до комиссии.")
        if issues:
            counts["disputed"] += 1
        rows.append(dict(
            booking_id=booking_id, object=obj, currency=code, **result,
            ehous_rows=db_matches, report_rows=report_matches, confirmed_payouts=paid, payout_documents=docs,
            payout_coverage_source=paid_coverage, report_minus_stated_basis=stated_delta, report_comparable=comparable,
            report_minus_after=net_delta, other_charges=db.get("other_charges", []) if same_booking else [], issues=issues,
        ))

    for (booking_id, obj, code), docs in payouts.items():
        unresolved.append(dict(booking_id=booking_id, object=obj, currency=code, documents=docs,
                               reason="Платёж не сопоставлен с заявкой и объектом в периоде."))
    by_currency, by_object = summarize(rows, inventory_complete,
                                       report_complete and not counts["extra_in_report"], not unresolved)
    return dict(
        scope=scope, ehous={key: value for key, value in ehous.items() if key != "rows"},
        report={key: value for key, value in report.items() if key != "rows"},
        ehous_coverage_complete=inventory_complete, counts=counts, rows=rows,
        totals_by_currency=by_currency, totals_by_object=by_object,
        later_payments=later, other_payments=separate, unresolved_payments=unresolved,
    )


def encode(value):
    if isinstance(value, Decimal):
        return amount_text(value if value else Decimal(0))
    raise TypeError("Неподдерживаемый тип результата")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Абсолютный путь к подготовленному JSON")
    args = parser.parse_args()
    try:
        require(args.input.is_absolute(), "Нужен абсолютный путь входа")
        packet = json.loads(args.input.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
        with localcontext() as ctx:
            ctx.prec = 60
            result = reconcile(packet)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=encode))
    except (LedgerError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
