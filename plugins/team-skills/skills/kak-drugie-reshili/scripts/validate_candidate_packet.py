#!/usr/bin/env python3
"""Проверяет структуру и внутреннюю согласованность CandidatePacket v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml


SCHEMA_VERSION = 1
PASS_MESSAGE = "PASS подтверждает только форму пакета, но не истинность источника."

STATUSES = {
    "NO_USABLE_PRACTICE_FOUND",
    "DRAFT_EXTERNAL_PRACTICE_CANDIDATE",
    "NEEDS_MORE_EVIDENCE",
    "REVIEWED_EXTERNAL_PRACTICE_CANDIDATE",
    "REJECTED_CANDIDATE",
}
CANDIDATE_TYPES = {"atomic_mechanism", "reported_intervention_bundle"}
RELATIONS = {"original", "copy", "translation", "commentary"}
ACCESSIBILITY = {
    "full_text",
    "partial_text",
    "snippet_only",
    "unavailable",
    "paywalled",
    "auth_required",
}
REVIEWER_CLASSES = {"none", "fresh_context_same_model", "different_model", "human"}
INDEPENDENT_REVIEWER_CLASSES = REVIEWER_CLASSES - {"none"}
REVIEW_RESOLUTIONS = {"not_reviewed", "agree", "unresolved", "reject"}
CAUSAL_SUPPORT = {
    "not_applicable",
    "bundle_only",
    "single_change_reported",
    "controlled_isolation",
}
FAILURE_CODES = {
    "SOURCE_UNAVAILABLE",
    "SOURCE_CHANGED",
    "PAYWALL_OR_AUTH",
    "TRANSLATION_UNCERTAIN",
    "REVIEWER_UNAVAILABLE",
    "REVIEW_DISAGREEMENT",
    "BUDGET_EXHAUSTED",
    "BLOCKED_APPROVAL",
    "TOOL_FAILURE",
}
DISPOSITIONS = {"evidence", "duplicate", "rejected"}
QUERY_RECORD_KEYS = {
    "query_id",
    "query",
    "language",
    "rationale",
    "executed_at",
    "result_urls",
}
DISCOVERY_RECORD_KEYS = {"url", "method", "reference"}
DISCOVERY_METHODS = {
    "search_result",
    "user_provided_lead",
    "source_followup",
    "resume_lead",
}
ROOT_KEYS = {
    "schema_version",
    "run_id",
    "candidate_id",
    "input_fingerprint",
    "status",
    "candidate_type",
    "reported_problem",
    "reported_intervention",
    "reported_result",
    "local_status",
    "evidence_records",
    "evidence_basis",
    "applicability",
    "review",
    "run_metrics",
    "resume",
}
INPUT_CONTRACT_KEYS = {
    "outcome",
    "research_question",
    "current_context",
    "acceptance_evidence",
    "do_not_fixate_on",
    "must_preserve",
    "rejected_assumptions",
    "allowed_actions",
    "approval_required_actions",
    "research_budget",
    "contract_ref",
    "contract_sha256",
    "state_ref",
    "state_sha256",
    "observed_at",
}
INPUT_CONTRACT_OPTIONAL_KEYS = {"provided_leads", "resume_envelope"}
RESEARCH_BUDGET_KEYS = {
    "max_active_minutes",
    "max_queries",
    "max_opened_sources",
    "language_spaces",
    "max_fetch_attempts_per_source",
    "paid_access_allowed",
}
RESUME_ENVELOPE_KEYS = {"prior_run_id", "packet_sha256", "queued_leads"}
EVIDENCE_KEYS = {
    "origin_url",
    "canonical_origin_url",
    "canonical_origin_id",
    "relation",
    "accessed_at",
    "published_at",
    "language",
    "accessibility",
    "locator",
    "short_excerpt",
    "extract_sha256",
    "translation",
    "reported_context",
    "reported_change",
    "reported_result",
}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class PacketReadError(Exception):
    """Файл нельзя прочитать или разобрать."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalize_text(value: str) -> str:
    """Нормализация для синтаксически стабильного candidate_id."""

    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _canonicalize_input(value: Any) -> Any:
    """Канонизирует YAML-совместимый input-contract для fingerprint."""

    if isinstance(value, dict):
        return {str(key): _canonicalize_input(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, list):
        return [_canonicalize_input(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("input-contract содержит NaN или Infinity")
        return value
    raise ValueError(f"input-contract содержит неподдерживаемый тип: {type(value).__name__}")


def input_fingerprint(document: Any) -> str:
    canonical = json.dumps(
        _canonicalize_input(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "ifp-v1-" + hashlib.sha256(canonical).hexdigest()


def candidate_id(problem: str, components: list[str], result: str) -> str:
    payload = {
        "reported_intervention": sorted(normalize_text(component) for component in components),
        "reported_problem": normalize_text(problem),
        "reported_result": normalize_text(result),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "cph-v1-" + hashlib.sha256(canonical).hexdigest()


def excerpt_sha256(excerpt: str) -> str:
    return hashlib.sha256(excerpt.encode("utf-8")).hexdigest()


def canonicalize_url(raw_url: str) -> str:
    parts = urlsplit(raw_url.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError("ожидается абсолютный http(s) URL")
    hostname = (parts.hostname or "").lower()
    port = parts.port
    netloc = hostname
    if port and not ((parts.scheme.lower() == "http" and port == 80) or (parts.scheme.lower() == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    if parts.username or parts.password:
        raise ValueError("URL с реквизитами запрещён")
    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
            continue
        query_items.append((key, value))
    query_items.sort()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query_items), ""))


def canonical_origin_id(raw_url: str) -> str:
    canonical = canonicalize_url(raw_url).encode("utf-8")
    return "origin-v1-" + hashlib.sha256(canonical).hexdigest()


def _is_iso_date(value: Any) -> bool:
    if isinstance(value, (datetime, date)):
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
        return True
    except ValueError:
        try:
            date.fromisoformat(candidate)
            return True
        except ValueError:
            return False


def _check_exact_keys(
    value: Any,
    required: set[str],
    path: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path}: ожидается mapping")
        return None
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    for key in missing:
        errors.append(f"{path}.{key}: обязательное поле отсутствует")
    for key in unknown:
        errors.append(f"{path}.{key}: неизвестное поле")
    return value


def _check_string_list(value: Any, path: str, errors: list[str], *, unique: bool = False) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{path}: ожидается list")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not _nonempty_string(item):
            errors.append(f"{path}[{index}]: ожидается непустая строка")
        else:
            result.append(item)
    if unique and len(set(result)) != len(result):
        errors.append(f"{path}: значения должны быть уникальными")
    return result


def _check_nonnegative_number_or_unknown(value: Any, path: str, errors: list[str]) -> None:
    if value == "unknown":
        return
    if not _is_number(value) or value < 0:
        errors.append(f"{path}: ожидается неотрицательное число или unknown")


def _check_nonnegative_int(value: Any, path: str, errors: list[str]) -> None:
    if not _is_int(value) or value < 0:
        errors.append(f"{path}: ожидается целое число >= 0")


def _check_nonnegative_int_or_unknown(
    value: Any,
    path: str,
    errors: list[str],
) -> None:
    if value == "unknown":
        return
    _check_nonnegative_int(value, path, errors)


def read_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PacketReadError(f"не удалось прочитать {path}: {exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PacketReadError(f"некорректный YAML в {path}: {exc}") from exc


def _validate_input_contract(
    document: Any,
    errors: list[str],
) -> dict[str, Any] | None:
    if not isinstance(document, dict):
        errors.append("input_contract: ожидается mapping")
        return None
    missing = sorted(INPUT_CONTRACT_KEYS - set(document))
    unknown = sorted(
        set(document) - INPUT_CONTRACT_KEYS - INPUT_CONTRACT_OPTIONAL_KEYS
    )
    for key in missing:
        errors.append(f"input_contract.{key}: обязательное поле отсутствует")
    for key in unknown:
        errors.append(f"input_contract.{key}: неизвестное поле")

    for field in (
        "outcome",
        "research_question",
        "current_context",
        "contract_ref",
        "state_ref",
    ):
        if not _nonempty_string(document.get(field)):
            errors.append(f"input_contract.{field}: ожидается непустая строка")
    for field in (
        "acceptance_evidence",
        "do_not_fixate_on",
        "must_preserve",
        "rejected_assumptions",
        "allowed_actions",
        "approval_required_actions",
    ):
        _check_string_list(
            document.get(field),
            f"input_contract.{field}",
            errors,
            unique=True,
        )

    for field in ("contract_sha256", "state_sha256"):
        value = document.get(field)
        if not isinstance(value, str) or not SHA256_RE.match(value):
            errors.append(
                f"input_contract.{field}: ожидается 64 lowercase hex"
            )
    if not _is_iso_date(document.get("observed_at")):
        errors.append("input_contract.observed_at: ожидается ISO date/datetime")

    budget = _check_exact_keys(
        document.get("research_budget"),
        RESEARCH_BUDGET_KEYS,
        "input_contract.research_budget",
        errors,
    )
    if budget is None:
        return None
    active_limit = budget.get("max_active_minutes")
    if not _is_number(active_limit) or active_limit <= 0:
        errors.append(
            "input_contract.research_budget.max_active_minutes: "
            "ожидается число > 0"
        )
    for field in (
        "max_queries",
        "max_opened_sources",
        "max_fetch_attempts_per_source",
    ):
        value = budget.get(field)
        if not _is_int(value) or value <= 0:
            errors.append(
                f"input_contract.research_budget.{field}: "
                "ожидается целое число > 0"
            )
    languages = _check_string_list(
        budget.get("language_spaces"),
        "input_contract.research_budget.language_spaces",
        errors,
        unique=True,
    )
    if not languages:
        errors.append(
            "input_contract.research_budget.language_spaces: требуется хотя бы один язык"
        )
    for index, language in enumerate(languages):
        if not LANGUAGE_RE.match(language):
            errors.append(
                "input_contract.research_budget.language_spaces"
                f"[{index}]: ожидается языковой код вроде ru или en-US"
            )
    if not isinstance(budget.get("paid_access_allowed"), bool):
        errors.append(
            "input_contract.research_budget.paid_access_allowed: ожидается boolean"
        )
    if "provided_leads" in document:
        provided_leads = _check_string_list(
            document.get("provided_leads"),
            "input_contract.provided_leads",
            errors,
            unique=True,
        )
        for index, raw_url in enumerate(provided_leads):
            try:
                canonicalize_url(raw_url)
            except ValueError as exc:
                errors.append(f"input_contract.provided_leads[{index}]: {exc}")
    if "resume_envelope" in document:
        resume_envelope = _check_exact_keys(
            document.get("resume_envelope"),
            RESUME_ENVELOPE_KEYS,
            "input_contract.resume_envelope",
            errors,
        )
        if resume_envelope is not None:
            if not _nonempty_string(resume_envelope.get("prior_run_id")):
                errors.append(
                    "input_contract.resume_envelope.prior_run_id: "
                    "ожидается непустая строка"
                )
            packet_hash = resume_envelope.get("packet_sha256")
            if not isinstance(packet_hash, str) or not SHA256_RE.match(
                packet_hash
            ):
                errors.append(
                    "input_contract.resume_envelope.packet_sha256: "
                    "ожидается 64 lowercase hex"
                )
            resume_leads = _check_string_list(
                resume_envelope.get("queued_leads"),
                "input_contract.resume_envelope.queued_leads",
                errors,
                unique=True,
            )
            for index, raw_url in enumerate(resume_leads):
                try:
                    canonicalize_url(raw_url)
                except ValueError as exc:
                    errors.append(
                        "input_contract.resume_envelope.queued_leads"
                        f"[{index}]: {exc}"
                    )
    return budget


def validate_input_contract(document: Any) -> list[str]:
    """Проверяет только форму обязательного input-contract."""

    errors: list[str] = []
    _validate_input_contract(document, errors)
    return sorted(set(errors))


def _validate_translation(
    translation: Any,
    relation: Any,
    path: str,
    errors: list[str],
) -> None:
    if translation is None:
        if relation == "translation":
            errors.append(f"{path}: relation=translation требует translation mapping")
        return
    mapping = _check_exact_keys(
        translation,
        {"text", "method", "reviewer_id"},
        path,
        errors,
    )
    if mapping is None:
        return
    if not _nonempty_string(mapping.get("text")):
        errors.append(f"{path}.text: ожидается непустой перевод")
    if not _nonempty_string(mapping.get("method")):
        errors.append(f"{path}.method: ожидается способ перевода")
    reviewer_id = mapping.get("reviewer_id")
    if reviewer_id is not None and not _nonempty_string(reviewer_id):
        errors.append(f"{path}.reviewer_id: ожидается непустая строка или null")


def _validate_evidence_records(
    records: Any,
    errors: list[str],
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    if not isinstance(records, list):
        errors.append("evidence_records: ожидается list")
        return [], set(), set()
    valid_records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    independent_origins: set[str] = set()
    evidence_urls: set[str] = set()

    for index, raw_record in enumerate(records):
        path = f"evidence_records[{index}]"
        record = _check_exact_keys(raw_record, EVIDENCE_KEYS, path, errors)
        if record is None:
            continue
        valid_records.append(record)

        raw_url = record.get("origin_url")
        canonical_origin_url = record.get("canonical_origin_url")
        canonical_url = None
        if not _nonempty_string(raw_url):
            errors.append(f"{path}.origin_url: ожидается http(s) URL")
        else:
            try:
                canonical_url = canonicalize_url(raw_url)
                if canonical_url in seen_urls:
                    errors.append(f"{path}.origin_url: URL уже использован в evidence_records")
                seen_urls.add(canonical_url)
                evidence_urls.add(canonical_url)
            except ValueError as exc:
                errors.append(f"{path}.origin_url: {exc}")

        canonical_origin = None
        if not _nonempty_string(canonical_origin_url):
            errors.append(f"{path}.canonical_origin_url: ожидается http(s) URL")
        else:
            try:
                canonical_origin = canonicalize_url(canonical_origin_url)
            except ValueError as exc:
                errors.append(f"{path}.canonical_origin_url: {exc}")

        origin_identifier = record.get("canonical_origin_id")
        if canonical_origin is not None:
            expected_origin_id = canonical_origin_id(canonical_origin_url)
            if origin_identifier != expected_origin_id:
                errors.append(
                    f"{path}.canonical_origin_id: ожидается {expected_origin_id}"
                )

        relation = record.get("relation")
        if relation not in RELATIONS:
            errors.append(f"{path}.relation: неизвестное значение {relation!r}")
        if relation == "original" and canonical_url and canonical_origin and canonical_url != canonical_origin:
            errors.append(
                f"{path}: relation=original требует совпадения origin_url и canonical_origin_url"
            )

        if not _is_iso_date(record.get("accessed_at")):
            errors.append(f"{path}.accessed_at: ожидается ISO date/datetime")
        published_at = record.get("published_at")
        if published_at is not None and not _is_iso_date(published_at):
            errors.append(f"{path}.published_at: ожидается ISO date/datetime или null")
        language = record.get("language")
        if not _nonempty_string(language) or not LANGUAGE_RE.match(language):
            errors.append(f"{path}.language: ожидается языковой код вроде ru или en-US")

        accessibility = record.get("accessibility")
        if accessibility not in ACCESSIBILITY:
            errors.append(f"{path}.accessibility: неизвестное значение {accessibility!r}")

        full_or_partial = accessibility in {"full_text", "partial_text"}
        for field in ("locator", "short_excerpt", "reported_context", "reported_change", "reported_result"):
            value = record.get(field)
            if full_or_partial and not _nonempty_string(value):
                errors.append(f"{path}.{field}: обязательная непустая строка для {accessibility}")
            elif value is not None and not isinstance(value, str):
                errors.append(f"{path}.{field}: ожидается строка или null")

        excerpt = record.get("short_excerpt")
        extract_hash = record.get("extract_sha256")
        if isinstance(excerpt, str) and len(excerpt) > 500:
            errors.append(f"{path}.short_excerpt: максимум 500 символов")
        if full_or_partial and isinstance(excerpt, str):
            expected_hash = excerpt_sha256(excerpt)
            if extract_hash != expected_hash:
                errors.append(f"{path}.extract_sha256: ожидается {expected_hash}")
        elif extract_hash is not None:
            errors.append(
                f"{path}.extract_sha256: для недоступного текста ожидается null"
            )

        _validate_translation(record.get("translation"), relation, f"{path}.translation", errors)

        if (
            relation == "original"
            and accessibility == "full_text"
            and isinstance(origin_identifier, str)
        ):
            independent_origins.add(origin_identifier)

    return valid_records, independent_origins, evidence_urls


def _validate_review(
    review_value: Any,
    status: Any,
    errors: list[str],
) -> None:
    review = _check_exact_keys(
        review_value,
        {
            "researcher_id",
            "reviewer_class",
            "reviewer_id",
            "reviewed_at",
            "original_opened",
            "disagreements",
            "resolution",
        },
        "review",
        errors,
    )
    if review is None:
        return

    researcher_id = review.get("researcher_id")
    if not _nonempty_string(researcher_id):
        errors.append("review.researcher_id: ожидается непустая строка")
    reviewer_class = review.get("reviewer_class")
    if reviewer_class not in REVIEWER_CLASSES:
        errors.append(f"review.reviewer_class: неизвестное значение {reviewer_class!r}")
    reviewer_id = review.get("reviewer_id")
    reviewed_at = review.get("reviewed_at")
    original_opened = review.get("original_opened")
    if not isinstance(original_opened, bool):
        errors.append("review.original_opened: ожидается boolean")
    disagreements = _check_string_list(
        review.get("disagreements"),
        "review.disagreements",
        errors,
    )
    resolution = review.get("resolution")
    if resolution not in REVIEW_RESOLUTIONS:
        errors.append(f"review.resolution: неизвестное значение {resolution!r}")

    if reviewer_class == "none":
        if reviewer_id is not None:
            errors.append("review.reviewer_id: при reviewer_class=none ожидается null")
        if reviewed_at is not None:
            errors.append("review.reviewed_at: при reviewer_class=none ожидается null")
        if original_opened is not False:
            errors.append(
                "review.original_opened: при reviewer_class=none ожидается false"
            )
    else:
        if not _nonempty_string(reviewer_id):
            errors.append("review.reviewer_id: независимый review требует ID")
        if not _is_iso_date(reviewed_at):
            errors.append("review.reviewed_at: независимый review требует ISO date/datetime")
        if _nonempty_string(researcher_id) and reviewer_id == researcher_id:
            errors.append("review.reviewer_id: reviewer не может совпадать с researcher")

    if status == "DRAFT_EXTERNAL_PRACTICE_CANDIDATE":
        if reviewer_class != "none" or resolution != "not_reviewed":
            errors.append("review: DRAFT требует reviewer_class=none и resolution=not_reviewed")
        if disagreements:
            errors.append("review.disagreements: DRAFT не должен имитировать завершённый review")
    elif status == "NEEDS_MORE_EVIDENCE":
        if resolution not in {"not_reviewed", "unresolved"}:
            errors.append("review.resolution: NEEDS_MORE_EVIDENCE допускает not_reviewed или unresolved")
        if resolution == "unresolved" and not disagreements:
            errors.append("review.disagreements: unresolved требует хотя бы одно разногласие")
    elif status == "REVIEWED_EXTERNAL_PRACTICE_CANDIDATE":
        if reviewer_class not in INDEPENDENT_REVIEWER_CLASSES:
            errors.append("review.reviewer_class: REVIEWED требует свежего reviewer")
        if resolution != "agree":
            errors.append("review.resolution: REVIEWED требует agree")
        if original_opened is not True:
            errors.append("review.original_opened: REVIEWED требует true")
        if disagreements:
            errors.append("review.disagreements: REVIEWED требует пустой список")
    elif status == "REJECTED_CANDIDATE":
        if reviewer_class not in INDEPENDENT_REVIEWER_CLASSES:
            errors.append("review.reviewer_class: REJECTED требует независимого reviewer")
        if resolution != "reject":
            errors.append("review.resolution: REJECTED требует reject")
        if not disagreements:
            errors.append("review.disagreements: REJECTED требует причины")
    elif status == "NO_USABLE_PRACTICE_FOUND":
        if reviewer_class != "none" or resolution != "not_reviewed":
            errors.append("review: NO_USABLE требует reviewer_class=none и resolution=not_reviewed")


def _validate_metrics(
    metrics_value: Any,
    evidence_urls: set[str],
    queued_leads: list[str],
    exhausted_queries: list[str],
    provided_leads: set[str] | None,
    resume_leads: set[str] | None,
    prior_run_id: str | None,
    errors: list[str],
) -> dict[str, Any] | None:
    keys = {
        "queries",
        "sources_discovered",
        "sources_opened",
        "sources_readable",
        "sources_rejected",
        "duplicate_origins",
        "retries",
        "active_seconds",
        "human_review_minutes",
        "observable_cost",
        "failure_codes",
        "discovery_records",
        "query_records",
        "source_attempts",
    }
    metrics = _check_exact_keys(metrics_value, keys, "run_metrics", errors)
    if metrics is None:
        return None

    for field in (
        "queries",
        "sources_discovered",
        "sources_opened",
        "sources_readable",
        "sources_rejected",
        "duplicate_origins",
        "retries",
    ):
        _check_nonnegative_int(metrics.get(field), f"run_metrics.{field}", errors)
    _check_nonnegative_number_or_unknown(
        metrics.get("active_seconds"), "run_metrics.active_seconds", errors
    )
    _check_nonnegative_number_or_unknown(
        metrics.get("human_review_minutes"),
        "run_metrics.human_review_minutes",
        errors,
    )
    if (
        _is_number(metrics.get("active_seconds"))
        and _is_number(metrics.get("human_review_minutes"))
        and metrics["human_review_minutes"] * 60
        > metrics["active_seconds"] + 1e-9
    ):
        errors.append(
            "run_metrics.human_review_minutes: не может превышать active_seconds"
        )

    cost = _check_exact_keys(
        metrics.get("observable_cost"),
        {"amount", "currency"},
        "run_metrics.observable_cost",
        errors,
    )
    if cost is not None:
        amount = cost.get("amount")
        currency = cost.get("currency")
        if amount != "unknown" and (not _is_number(amount) or amount < 0):
            errors.append("run_metrics.observable_cost.amount: ожидается число >= 0 или unknown")
        if amount == "unknown":
            if currency is not None:
                errors.append("run_metrics.observable_cost.currency: при unknown ожидается null")
        elif not _nonempty_string(currency) or not re.match(r"^[A-Z]{3}$", currency):
            errors.append("run_metrics.observable_cost.currency: ожидается ISO-4217")

    failure_codes = _check_string_list(
        metrics.get("failure_codes"),
        "run_metrics.failure_codes",
        errors,
        unique=True,
    )
    unknown_failures = sorted(set(failure_codes) - FAILURE_CODES)
    for failure in unknown_failures:
        errors.append(f"run_metrics.failure_codes: неизвестный код {failure}")

    query_records = metrics.get("query_records")
    query_result_urls: set[str] = set()
    query_results_by_id: dict[str, set[str]] = {}
    recorded_queries: list[str] = []
    query_ids: set[str] = set()
    if not isinstance(query_records, list):
        errors.append("run_metrics.query_records: ожидается list")
    else:
        for index, raw_record in enumerate(query_records):
            path = f"run_metrics.query_records[{index}]"
            record = _check_exact_keys(
                raw_record,
                QUERY_RECORD_KEYS,
                path,
                errors,
            )
            if record is None:
                continue
            query_id = record.get("query_id")
            if not _nonempty_string(query_id):
                errors.append(f"{path}.query_id: ожидается непустая строка")
            elif query_id in query_ids:
                errors.append(f"{path}.query_id: duplicate {query_id}")
            else:
                query_ids.add(query_id)
            query = record.get("query")
            if not _nonempty_string(query):
                errors.append(f"{path}.query: ожидается непустая строка")
            else:
                recorded_queries.append(query)
            language = record.get("language")
            if not _nonempty_string(language) or not LANGUAGE_RE.match(language):
                errors.append(f"{path}.language: ожидается языковой код вроде ru или en-US")
            if not _nonempty_string(record.get("rationale")):
                errors.append(f"{path}.rationale: ожидается непустая строка")
            if not _is_iso_date(record.get("executed_at")):
                errors.append(f"{path}.executed_at: ожидается ISO date/datetime")
            result_urls = record.get("result_urls")
            normalized_results: set[str] = set()
            if not isinstance(result_urls, list):
                errors.append(f"{path}.result_urls: ожидается list")
            else:
                for url_index, raw_url in enumerate(result_urls):
                    if not _nonempty_string(raw_url):
                        errors.append(
                            f"{path}.result_urls[{url_index}]: ожидается http(s) URL"
                        )
                        continue
                    try:
                        normalized_results.add(canonicalize_url(raw_url))
                    except ValueError as exc:
                        errors.append(f"{path}.result_urls[{url_index}]: {exc}")
            if _nonempty_string(query_id):
                query_results_by_id[query_id] = normalized_results
            query_result_urls.update(normalized_results)
    if metrics.get("queries") != len(recorded_queries):
        errors.append(
            f"run_metrics.queries: ожидается {len(recorded_queries)} по query_records"
        )
    if len(set(recorded_queries)) != len(recorded_queries):
        errors.append("run_metrics.query_records: query должен быть уникален в запуске")
    if set(exhausted_queries) != set(recorded_queries):
        errors.append(
            "resume.exhausted_queries: должен совпадать с query из query_records"
        )

    discovery_records = metrics.get("discovery_records")
    discovered_urls: set[str] = set()
    followup_references: list[tuple[str, str, str]] = []
    followup_parents: dict[str, str] = {}
    if not isinstance(discovery_records, list):
        errors.append("run_metrics.discovery_records: ожидается list")
    else:
        for index, raw_record in enumerate(discovery_records):
            path = f"run_metrics.discovery_records[{index}]"
            record = _check_exact_keys(
                raw_record,
                DISCOVERY_RECORD_KEYS,
                path,
                errors,
            )
            if record is None:
                continue
            raw_url = record.get("url")
            if not _nonempty_string(raw_url):
                errors.append(f"{path}.url: ожидается http(s) URL")
                continue
            try:
                url = canonicalize_url(raw_url)
            except ValueError as exc:
                errors.append(f"{path}.url: {exc}")
                continue
            if url in discovered_urls:
                errors.append(f"{path}.url: URL уже есть в discovery_records")
            discovered_urls.add(url)
            method = record.get("method")
            if method not in DISCOVERY_METHODS:
                errors.append(f"{path}.method: неизвестное значение {method!r}")
            reference = record.get("reference")
            if not _nonempty_string(reference):
                errors.append(f"{path}.reference: ожидается непустая строка")
                continue
            if method == "search_result":
                if reference not in query_results_by_id:
                    errors.append(
                        f"{path}.reference: неизвестный query_id {reference!r}"
                    )
                elif url not in query_results_by_id[reference]:
                    errors.append(
                        f"{path}: URL отсутствует в result_urls запроса {reference}"
                    )
            elif method == "user_provided_lead":
                if provided_leads is None:
                    errors.append(
                        f"{path}: user_provided_lead требует --input-contract"
                    )
                elif url not in provided_leads:
                    errors.append(
                        f"{path}: URL отсутствует в input_contract.provided_leads"
                    )
            elif method == "source_followup":
                try:
                    parent_url = canonicalize_url(reference)
                except ValueError as exc:
                    errors.append(f"{path}.reference: {exc}")
                else:
                    followup_references.append((path, url, parent_url))
                    followup_parents[url] = parent_url
            elif method == "resume_lead":
                if resume_leads is None or prior_run_id is None:
                    errors.append(
                        f"{path}: resume_lead требует input-contract resume_envelope"
                    )
                else:
                    if url not in resume_leads:
                        errors.append(
                            f"{path}: URL отсутствует в "
                            "input_contract.resume_envelope.queued_leads"
                        )
                    if reference != prior_run_id:
                        errors.append(
                            f"{path}.reference: ожидается prior_run_id "
                            f"{prior_run_id!r}"
                        )

    missing_query_discoveries = query_result_urls - discovered_urls
    if missing_query_discoveries:
        errors.append(
            "run_metrics.discovery_records: нет записей для retained query URLs: "
            + ", ".join(sorted(missing_query_discoveries))
        )
    if provided_leads is not None:
        missing_provided_leads = provided_leads - discovered_urls
        if missing_provided_leads:
            errors.append(
                "run_metrics.discovery_records: нет user_provided_lead для: "
                + ", ".join(sorted(missing_provided_leads))
            )
    if resume_leads is not None:
        missing_resume_leads = resume_leads - discovered_urls
        if missing_resume_leads:
            errors.append(
                "run_metrics.discovery_records: нет resume_lead для: "
                + ", ".join(sorted(missing_resume_leads))
            )
    for path, url, parent_url in followup_references:
        if parent_url not in discovered_urls or parent_url == url:
            errors.append(
                f"{path}.reference: source_followup требует другой ранее "
                "зафиксированный URL"
            )
    for start_url in followup_parents:
        seen_chain: set[str] = set()
        cursor = start_url
        while cursor in followup_parents:
            if cursor in seen_chain:
                errors.append(
                    "run_metrics.discovery_records: циклический "
                    f"source_followup для {start_url}"
                )
                break
            seen_chain.add(cursor)
            cursor = followup_parents[cursor]
    if metrics.get("sources_discovered") != len(discovered_urls):
        errors.append(
            "run_metrics.sources_discovered: "
            f"ожидается {len(discovered_urls)} по discovery_records"
        )

    attempts_value = metrics.get("source_attempts")
    if not isinstance(attempts_value, list):
        errors.append("run_metrics.source_attempts: ожидается list")
        return metrics
    attempt_urls: set[str] = set()
    derived_readable = 0
    derived_rejected = 0
    derived_duplicates = 0
    derived_retries = 0
    attempt_failure_codes: set[str] = set()
    evidence_attempt_urls: set[str] = set()
    readable_attempt_urls: set[str] = set()
    for index, raw_attempt in enumerate(attempts_value):
        path = f"run_metrics.source_attempts[{index}]"
        attempt = _check_exact_keys(
            raw_attempt,
            {"url", "attempts", "final_accessibility", "disposition", "failure_code"},
            path,
            errors,
        )
        if attempt is None:
            continue
        raw_url = attempt.get("url")
        if not _nonempty_string(raw_url):
            errors.append(f"{path}.url: ожидается http(s) URL")
            continue
        try:
            url = canonicalize_url(raw_url)
        except ValueError as exc:
            errors.append(f"{path}.url: {exc}")
            continue
        if url in attempt_urls:
            errors.append(f"{path}.url: URL уже есть в source_attempts")
        attempt_urls.add(url)
        attempts = attempt.get("attempts")
        if not _is_int(attempts) or attempts < 1:
            errors.append(f"{path}.attempts: ожидается целое число >= 1")
        else:
            derived_retries += attempts - 1
        accessibility = attempt.get("final_accessibility")
        if accessibility not in ACCESSIBILITY:
            errors.append(f"{path}.final_accessibility: неизвестное значение {accessibility!r}")
        if accessibility in {"full_text", "partial_text"}:
            derived_readable += 1
            readable_attempt_urls.add(url)
        disposition = attempt.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append(f"{path}.disposition: неизвестное значение {disposition!r}")
        elif disposition == "rejected":
            derived_rejected += 1
        elif disposition == "duplicate":
            derived_duplicates += 1
        elif disposition == "evidence":
            evidence_attempt_urls.add(url)
        failure_code = attempt.get("failure_code")
        if failure_code is not None:
            if failure_code not in FAILURE_CODES:
                errors.append(f"{path}.failure_code: неизвестный код {failure_code!r}")
            else:
                attempt_failure_codes.add(failure_code)
        if accessibility in {"full_text", "partial_text"} and failure_code is not None:
            errors.append(
                f"{path}.failure_code: читаемый итог требует null"
            )
        if accessibility in {
            "snippet_only",
            "unavailable",
            "paywalled",
            "auth_required",
        } and failure_code is None:
            errors.append(
                f"{path}.failure_code: нечитаемый итог требует код причины"
            )
        if disposition == "evidence" and accessibility not in {
            "full_text",
            "partial_text",
        }:
            errors.append(
                f"{path}.disposition: evidence требует full_text или partial_text"
            )

    derived = {
        "sources_opened": len(attempt_urls),
        "sources_readable": derived_readable,
        "sources_rejected": derived_rejected,
        "duplicate_origins": derived_duplicates,
        "retries": derived_retries,
    }
    for field, expected in derived.items():
        if metrics.get(field) != expected:
            errors.append(f"run_metrics.{field}: ожидается {expected} по source_attempts")

    undiscovered = (attempt_urls | set(queued_leads)) - discovered_urls
    if undiscovered:
        errors.append(
            "run_metrics.discovery_records: opened или queued URL отсутствуют: "
            + ", ".join(sorted(undiscovered))
        )
    orphaned_discoveries = discovered_urls - attempt_urls - set(queued_leads)
    if orphaned_discoveries:
        errors.append(
            "run_metrics.discovery_records: URL не открыт и не поставлен в очередь: "
            + ", ".join(sorted(orphaned_discoveries))
        )
    for path, _url, parent_url in followup_references:
        if parent_url not in readable_attempt_urls:
            errors.append(
                f"{path}.reference: source_followup требует прочитанный "
                "родительский URL"
            )

    if not evidence_urls <= evidence_attempt_urls:
        missing = sorted(evidence_urls - evidence_attempt_urls)
        errors.append(
            "run_metrics.source_attempts: evidence URL без disposition=evidence: "
            + ", ".join(missing)
        )
    if not attempt_failure_codes <= set(failure_codes):
        errors.append(
            "run_metrics.failure_codes: не содержит все failure_code из source_attempts"
        )
    return metrics


def _validate_budget_alignment(
    *,
    budget: dict[str, Any],
    metrics: dict[str, Any] | None,
    resume: dict[str, Any] | None,
    status: Any,
    errors: list[str],
) -> None:
    if metrics is None or resume is None:
        return
    remaining = resume.get("remaining_budget")
    if not isinstance(remaining, dict):
        return

    numeric_limits = all(
        _is_number(budget.get(field))
        for field in (
            "max_active_minutes",
            "max_queries",
            "max_opened_sources",
            "max_fetch_attempts_per_source",
        )
    )
    if not numeric_limits:
        return

    queries = metrics.get("queries")
    opened = metrics.get("sources_opened")
    active_seconds = metrics.get("active_seconds")
    if _is_int(queries):
        if queries > budget["max_queries"]:
            errors.append("run_metrics.queries: превышен max_queries input-contract")
        expected = budget["max_queries"] - queries
        if remaining.get("queries") != expected:
            errors.append(
                f"resume.remaining_budget.queries: ожидается {expected} по input-contract"
            )
    if _is_int(opened):
        if opened > budget["max_opened_sources"]:
            errors.append(
                "run_metrics.sources_opened: превышен max_opened_sources input-contract"
            )
        expected = budget["max_opened_sources"] - opened
        if remaining.get("opened_sources") != expected:
            errors.append(
                "resume.remaining_budget.opened_sources: "
                f"ожидается {expected} по input-contract"
            )
    if _is_number(active_seconds):
        active_minutes = active_seconds / 60
        if active_minutes > budget["max_active_minutes"] + 1e-9:
            errors.append(
                "run_metrics.active_seconds: превышен max_active_minutes input-contract"
            )
        expected = max(0.0, budget["max_active_minutes"] - active_minutes)
        remaining_active = remaining.get("active_minutes")
        if not _is_number(remaining_active) or not math.isclose(
            remaining_active,
            expected,
            rel_tol=0,
            abs_tol=1e-9,
        ):
            errors.append(
                "resume.remaining_budget.active_minutes: "
                f"ожидается {expected:g} по input-contract"
            )
    elif remaining.get("active_minutes") != "unknown":
        errors.append(
            "resume.remaining_budget.active_minutes: при unknown active_seconds "
            "ожидается unknown"
        )

    attempts = metrics.get("source_attempts")
    if isinstance(attempts, list):
        for index, attempt in enumerate(attempts):
            if not isinstance(attempt, dict):
                continue
            attempt_count = attempt.get("attempts")
            if _is_int(attempt_count) and (
                attempt_count > budget["max_fetch_attempts_per_source"]
            ):
                errors.append(
                    f"run_metrics.source_attempts[{index}].attempts: "
                    "превышен max_fetch_attempts_per_source input-contract"
                )
    query_records = metrics.get("query_records")
    allowed_languages = set(budget.get("language_spaces", []))
    if isinstance(query_records, list):
        for index, record in enumerate(query_records):
            if not isinstance(record, dict):
                continue
            language = record.get("language")
            if isinstance(language, str) and language not in allowed_languages:
                errors.append(
                    f"run_metrics.query_records[{index}].language: "
                    "язык отсутствует в input-contract research_budget"
                )

    failure_codes = metrics.get("failure_codes")
    remaining_values = [
        remaining.get("active_minutes"),
        remaining.get("queries"),
        remaining.get("opened_sources"),
    ]
    budget_exhausted = any(value == 0 for value in remaining_values)
    if status == "NO_USABLE_PRACTICE_FOUND":
        if not isinstance(failure_codes, list) or "BUDGET_EXHAUSTED" not in failure_codes:
            errors.append(
                "run_metrics.failure_codes: NO_USABLE требует BUDGET_EXHAUSTED"
            )
        if not budget_exhausted:
            errors.append(
                "resume.remaining_budget: NO_USABLE требует исчерпания "
                "хотя бы одного измеряемого лимита"
            )


def validate_document(
    document: Any,
    *,
    input_contract: Any | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    provided_leads: set[str] | None = None
    resume_leads: set[str] | None = None
    prior_run_id: str | None = None
    if isinstance(input_contract, dict):
        provided_leads = set()
        raw_provided_leads = input_contract.get("provided_leads")
        if isinstance(raw_provided_leads, list):
            for raw_url in raw_provided_leads:
                if not isinstance(raw_url, str):
                    continue
                try:
                    provided_leads.add(canonicalize_url(raw_url))
                except ValueError:
                    continue
        resume_envelope = input_contract.get("resume_envelope")
        if isinstance(resume_envelope, dict):
            raw_prior_run_id = resume_envelope.get("prior_run_id")
            if isinstance(raw_prior_run_id, str):
                prior_run_id = raw_prior_run_id
            raw_resume_leads = resume_envelope.get("queued_leads")
            if isinstance(raw_resume_leads, list):
                resume_leads = set()
                for raw_url in raw_resume_leads:
                    if not isinstance(raw_url, str):
                        continue
                    try:
                        resume_leads.add(canonicalize_url(raw_url))
                    except ValueError:
                        continue
    budget = (
        _validate_input_contract(input_contract, errors)
        if input_contract is not None
        else None
    )
    packet = _check_exact_keys(document, ROOT_KEYS, "$", errors)
    if packet is None:
        return sorted(set(errors)), warnings

    version = packet.get("schema_version")
    if not _is_int(version) or version != SCHEMA_VERSION:
        errors.append("schema_version: ожидается integer 1")
    if not _nonempty_string(packet.get("run_id")):
        errors.append("run_id: ожидается непустая строка")

    fingerprint = packet.get("input_fingerprint")
    if not isinstance(fingerprint, str) or not re.match(r"^ifp-v1-[0-9a-f]{64}$", fingerprint):
        errors.append("input_fingerprint: ожидается ifp-v1- и 64 lowercase hex")
    elif input_contract is None:
        warnings.append(
            "input_fingerprint проверен только по формату; передайте --input-contract для сверки"
        )
    else:
        try:
            expected_fingerprint = input_fingerprint(input_contract)
        except ValueError as exc:
            errors.append(f"input_contract: нельзя вычислить fingerprint: {exc}")
        else:
            if fingerprint != expected_fingerprint:
                errors.append(f"input_fingerprint: ожидается {expected_fingerprint}")

    status = packet.get("status")
    if status not in STATUSES:
        errors.append(f"status: неизвестное значение {status!r}")
    if packet.get("local_status") != "NOT_TESTED":
        errors.append("local_status: допустимо только NOT_TESTED")

    candidate_type = packet.get("candidate_type")
    problem = packet.get("reported_problem")
    intervention = packet.get("reported_intervention")
    result = packet.get("reported_result")
    packet_candidate_id = packet.get("candidate_id")

    components: list[str] = []
    if status == "NO_USABLE_PRACTICE_FOUND":
        for field, value in (
            ("candidate_id", packet_candidate_id),
            ("candidate_type", candidate_type),
            ("reported_problem", problem),
            ("reported_intervention", intervention),
            ("reported_result", result),
        ):
            if value is not None:
                errors.append(f"{field}: для NO_USABLE ожидается null")
    else:
        if candidate_type not in CANDIDATE_TYPES:
            errors.append(f"candidate_type: неизвестное значение {candidate_type!r}")
        if not _nonempty_string(problem):
            errors.append("reported_problem: ожидается непустая строка")
        if not _nonempty_string(result):
            errors.append("reported_result: ожидается непустая строка")
        intervention_mapping = _check_exact_keys(
            intervention,
            {"components", "attribution_note"},
            "reported_intervention",
            errors,
        )
        if intervention_mapping is not None:
            components = _check_string_list(
                intervention_mapping.get("components"),
                "reported_intervention.components",
                errors,
                unique=True,
            )
            normalized_components = [normalize_text(item) for item in components]
            if len(set(normalized_components)) != len(normalized_components):
                errors.append(
                    "reported_intervention.components: компоненты должны быть "
                    "уникальны после нормализации"
                )
            if not _nonempty_string(intervention_mapping.get("attribution_note")):
                errors.append("reported_intervention.attribution_note: ожидается непустая строка")
        if candidate_type == "atomic_mechanism" and len(components) != 1:
            errors.append("reported_intervention.components: atomic_mechanism требует один компонент")
        if candidate_type == "reported_intervention_bundle" and len(components) < 2:
            errors.append("reported_intervention.components: bundle требует минимум два компонента")
        if _nonempty_string(problem) and _nonempty_string(result) and components:
            expected_candidate_id = candidate_id(problem, components, result)
            if packet_candidate_id != expected_candidate_id:
                errors.append(f"candidate_id: ожидается {expected_candidate_id}")

    records, independent_origins, evidence_urls = _validate_evidence_records(
        packet.get("evidence_records"),
        errors,
    )
    if status == "NO_USABLE_PRACTICE_FOUND" and records:
        errors.append("evidence_records: NO_USABLE хранит screening trail в source_attempts, здесь ожидается []")
    elif status != "NO_USABLE_PRACTICE_FOUND" and not records:
        errors.append("evidence_records: candidate status требует хотя бы одну запись")

    basis = _check_exact_keys(
        packet.get("evidence_basis"),
        {"independent_origin_count", "corroboration", "causal_support"},
        "evidence_basis",
        errors,
    )
    if basis is not None:
        independent_count = basis.get("independent_origin_count")
        if independent_count != len(independent_origins):
            errors.append(
                f"evidence_basis.independent_origin_count: ожидается {len(independent_origins)}"
            )
        expected_corroboration = "independent" if len(independent_origins) >= 2 else "none"
        if basis.get("corroboration") != expected_corroboration:
            errors.append(f"evidence_basis.corroboration: ожидается {expected_corroboration}")
        causal_support = basis.get("causal_support")
        if causal_support not in CAUSAL_SUPPORT:
            errors.append(f"evidence_basis.causal_support: неизвестное значение {causal_support!r}")
        elif status == "NO_USABLE_PRACTICE_FOUND" and causal_support != "not_applicable":
            errors.append("evidence_basis.causal_support: NO_USABLE требует not_applicable")
        elif candidate_type == "reported_intervention_bundle" and causal_support != "bundle_only":
            errors.append("evidence_basis.causal_support: bundle требует bundle_only")
        elif candidate_type == "atomic_mechanism" and causal_support not in {
            "single_change_reported",
            "controlled_isolation",
        }:
            errors.append(
                "evidence_basis.causal_support: atomic требует single_change_reported или controlled_isolation"
            )

    applicability = _check_exact_keys(
        packet.get("applicability"),
        {"matches", "differences", "unknowns", "acceptance_evidence_not_addressed"},
        "applicability",
        errors,
    )
    if applicability is not None:
        list_values = {}
        for field in ("matches", "differences", "unknowns", "acceptance_evidence_not_addressed"):
            list_values[field] = _check_string_list(
                applicability.get(field),
                f"applicability.{field}",
                errors,
            )
        if status == "NO_USABLE_PRACTICE_FOUND" and any(list_values.values()):
            errors.append("applicability: NO_USABLE требует пустые списки")
        elif status != "NO_USABLE_PRACTICE_FOUND" and not list_values[
            "acceptance_evidence_not_addressed"
        ]:
            errors.append(
                "applicability.acceptance_evidence_not_addressed: candidate обязан назвать недостающее доказательство"
            )

    _validate_review(packet.get("review"), status, errors)
    if status == "REVIEWED_EXTERNAL_PRACTICE_CANDIDATE":
        full_originals = [
            record
            for record in records
            if record.get("relation") == "original"
            and record.get("accessibility") == "full_text"
        ]
        if not full_originals:
            errors.append("evidence_records: REVIEWED требует хотя бы один full_text original")

    resume = _check_exact_keys(
        packet.get("resume"),
        {"queued_leads", "exhausted_queries", "remaining_budget", "next_action"},
        "resume",
        errors,
    )
    queued_leads: list[str] = []
    exhausted_queries: list[str] = []
    if resume is not None:
        raw_queued = _check_string_list(
            resume.get("queued_leads"),
            "resume.queued_leads",
            errors,
            unique=True,
        )
        for index, url in enumerate(raw_queued):
            try:
                canonical = canonicalize_url(url)
                queued_leads.append(canonical)
            except ValueError as exc:
                errors.append(f"resume.queued_leads[{index}]: {exc}")
        exhausted_queries = _check_string_list(
            resume.get("exhausted_queries"),
            "resume.exhausted_queries",
            errors,
            unique=True,
        )
        remaining = _check_exact_keys(
            resume.get("remaining_budget"),
            {"active_minutes", "queries", "opened_sources"},
            "resume.remaining_budget",
            errors,
        )
        if remaining is not None:
            _check_nonnegative_number_or_unknown(
                remaining.get("active_minutes"),
                "resume.remaining_budget.active_minutes",
                errors,
            )
            for field in ("queries", "opened_sources"):
                _check_nonnegative_int_or_unknown(
                    remaining.get(field),
                    f"resume.remaining_budget.{field}",
                    errors,
                )
        if not _nonempty_string(resume.get("next_action")):
            errors.append("resume.next_action: ожидается одно непустое действие")

    if set(queued_leads) & evidence_urls:
        errors.append("resume.queued_leads: очередь пересекается с evidence URL")

    metrics = _validate_metrics(
        packet.get("run_metrics"),
        evidence_urls,
        queued_leads,
        exhausted_queries,
        provided_leads,
        resume_leads,
        prior_run_id,
        errors,
    )
    if isinstance(metrics, dict) and isinstance(
        metrics.get("source_attempts"),
        list,
    ):
        attempt_accessibility: dict[str, Any] = {}
        for raw_attempt in metrics["source_attempts"]:
            if not isinstance(raw_attempt, dict):
                continue
            raw_url = raw_attempt.get("url")
            if not isinstance(raw_url, str):
                continue
            try:
                normalized_url = canonicalize_url(raw_url)
            except ValueError:
                continue
            attempt_accessibility[normalized_url] = raw_attempt.get(
                "final_accessibility"
            )
        for index, record in enumerate(records):
            raw_url = record.get("origin_url")
            if not isinstance(raw_url, str):
                continue
            try:
                normalized_url = canonicalize_url(raw_url)
            except ValueError:
                continue
            observed_accessibility = attempt_accessibility.get(normalized_url)
            if (
                observed_accessibility is not None
                and record.get("accessibility") != observed_accessibility
            ):
                errors.append(
                    f"evidence_records[{index}].accessibility: не совпадает "
                    "с source_attempts.final_accessibility "
                    f"({record.get('accessibility')!r} != "
                    f"{observed_accessibility!r})"
                )
    if budget is not None:
        _validate_budget_alignment(
            budget=budget,
            metrics=metrics,
            resume=resume,
            status=status,
            errors=errors,
        )
    return sorted(set(errors)), sorted(set(warnings))


def _write_fixed_identifiers(
    path: Path,
    document: dict[str, Any],
    input_contract: Any | None,
) -> None:
    if input_contract is not None:
        document["input_fingerprint"] = input_fingerprint(input_contract)
    if document.get("status") != "NO_USABLE_PRACTICE_FOUND":
        intervention = document.get("reported_intervention")
        if (
            _nonempty_string(document.get("reported_problem"))
            and isinstance(intervention, dict)
            and isinstance(intervention.get("components"), list)
            and all(_nonempty_string(item) for item in intervention["components"])
            and _nonempty_string(document.get("reported_result"))
        ):
            document["candidate_id"] = candidate_id(
                document["reported_problem"],
                intervention["components"],
                document["reported_result"],
            )
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _render_text(
    *,
    ok: bool,
    document: Any,
    errors: list[str],
    warnings: list[str],
) -> str:
    lines = ["VALID" if ok else "FAIL"]
    for warning in warnings:
        lines.append(f"WARNING: {warning}")
    for error in errors:
        lines.append(f"ERROR: {error}")
    if ok:
        lines.append(PASS_MESSAGE)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--input-contract", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fix-identifiers",
        action="store_true",
        help="Пересчитать candidate_id и, при наличии input-contract, input_fingerprint.",
    )
    args = parser.parse_args(argv)

    try:
        document = read_yaml(args.packet)
        contract = read_yaml(args.input_contract) if args.input_contract else None
        if args.fix_identifiers:
            if not isinstance(document, dict):
                raise PacketReadError("корень packet должен быть mapping")
            _write_fixed_identifiers(args.packet, document, contract)
            document = read_yaml(args.packet)
        errors, warnings = validate_document(document, input_contract=contract)
    except PacketReadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # defensive CLI boundary
        print(f"ERROR: внутренний сбой validator: {exc}", file=sys.stderr)
        return 2

    ok = not errors
    if args.format == "json":
        payload = {
            "ok": ok,
            "schema_version": document.get("schema_version") if isinstance(document, dict) else None,
            "status": document.get("status") if isinstance(document, dict) else None,
            "candidate_id": document.get("candidate_id") if isinstance(document, dict) else None,
            "errors": errors,
            "warnings": warnings,
            "truth_boundary": PASS_MESSAGE,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(_render_text(ok=ok, document=document, errors=errors, warnings=warnings))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
