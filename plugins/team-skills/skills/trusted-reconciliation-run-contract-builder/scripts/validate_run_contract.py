#!/usr/bin/env python3
"""Проверяет форму и внутренние инварианты run-contract v1.1."""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


SKILL_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_DIR / "references" / "run-contract.schema.yaml"


class ContractReadError(Exception):
    """Контракт или схема не читаются как уникальный YAML mapping."""


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader, который не разрешает молча перезаписывать YAML-ключи."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    if not isinstance(node, MappingNode):
        raise ConstructorError(None, None, "ожидается YAML mapping", node.start_mark)
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ConstructorError(
                "при разборе mapping",
                node.start_mark,
                "нехэшируемый YAML-ключ",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise ConstructorError(
                "при разборе mapping",
                node.start_mark,
                f"повторяющийся ключ {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ContractReadError(f"{label} не найден: {path}")
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ContractReadError(f"{label} не удалось прочитать: {error}") from error
    if not isinstance(data, dict):
        raise ContractReadError(f"{label}: ожидается YAML mapping")
    return data


def load_schema() -> dict[str, Any]:
    return _load_yaml_mapping(SCHEMA_PATH, "схема")


def load_contract(path: Path) -> dict[str, Any]:
    return _load_yaml_mapping(path, "контракт")


def _schema_strings(schema: dict[str, Any], key: str) -> set[str]:
    value = schema.get(key)
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ContractReadError(f"схема.{key}: ожидается непустой список строк")
    return {item.strip() for item in value}


def _mapping(value: Any, path: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path}: ожидается mapping")
        return None
    return value


def _list(value: Any, path: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{path}: ожидается list")
        return []
    return value


def _exact_keys(
    value: dict[str, Any], expected: set[str], path: str, errors: list[str]
) -> None:
    for key in sorted(expected - set(value)):
        errors.append(f"{path}.{key}: обязательное поле отсутствует")
    for key in sorted(set(value) - expected, key=str):
        errors.append(f"{path}.{key}: неизвестное поле")


def _text(value: Any, path: str, errors: list[str], *, allow_unknown: bool = False) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: ожидается непустая строка")
        return None
    result = value.strip()
    if not allow_unknown and result.upper() == "UNKNOWN":
        errors.append(f"{path}: UNKNOWN здесь недопустим")
    return result


def _iso_date_or_timestamp(
    value: Any,
    path: str,
    errors: list[str],
    *,
    allow_unknown: bool = False,
) -> str | None:
    result = _text(value, path, errors, allow_unknown=allow_unknown)
    if result is None or (allow_unknown and result == "UNKNOWN"):
        return result
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", result):
            date.fromisoformat(result)
        elif re.match(r"^\d{4}-\d{2}-\d{2}T", result):
            datetime.fromisoformat(result.replace("Z", "+00:00"))
        else:
            raise ValueError
    except ValueError:
        errors.append(f"{path}: ожидается ISO date или ISO timestamp")
    return result


def _enum(
    value: Any, allowed: set[str], path: str, errors: list[str]
) -> str | None:
    if not isinstance(value, str):
        errors.append(f"{path}: ожидается строковый enum")
        return None
    if value not in allowed:
        errors.append(f"{path}: неизвестное значение {value!r}")
        return None
    return value


def _boolean(value: Any, path: str, errors: list[str]) -> bool | None:
    if not isinstance(value, bool):
        errors.append(f"{path}: ожидается true или false")
        return None
    return value


def _number(
    value: Any,
    path: str,
    errors: list[str],
    *,
    minimum: float | None = None,
    strictly_positive: bool = False,
) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        errors.append(f"{path}: ожидается конечное число")
        return None
    result = float(value)
    if minimum is not None and result < minimum:
        errors.append(f"{path}: значение должно быть не меньше {minimum}")
    if strictly_positive and result <= 0:
        errors.append(f"{path}: значение должно быть больше нуля")
    return result


def _integer(
    value: Any, path: str, errors: list[str], *, minimum: int = 0
) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{path}: ожидается целое число")
        return None
    if value < minimum:
        errors.append(f"{path}: значение должно быть не меньше {minimum}")
    return value


def _strings(
    value: Any,
    path: str,
    errors: list[str],
    *,
    unique: bool = False,
    nonempty: bool = False,
) -> list[str]:
    result: list[str] = []
    for index, item in enumerate(_list(value, path, errors)):
        text = _text(item, f"{path}[{index}]", errors, allow_unknown=True)
        if text is not None:
            result.append(text)
    if unique and len(result) != len(set(result)):
        errors.append(f"{path}: значения должны быть уникальными")
    if nonempty and not result:
        errors.append(f"{path}: нужен хотя бы один элемент")
    return result


def _enum_list(
    value: Any,
    allowed: set[str],
    path: str,
    errors: list[str],
    *,
    unique: bool = True,
    nonempty: bool = False,
) -> list[str]:
    result: list[str] = []
    for index, item in enumerate(_list(value, path, errors)):
        parsed = _enum(item, allowed, f"{path}[{index}]", errors)
        if parsed is not None:
            result.append(parsed)
    if unique and len(result) != len(set(result)):
        errors.append(f"{path}: значения должны быть уникальными")
    if nonempty and not result:
        errors.append(f"{path}: нужен хотя бы один элемент")
    return result


def _role_ref(
    value: Any,
    roles: dict[str, dict[str, Any]],
    path: str,
    errors: list[str],
    *,
    permission: str | None = None,
) -> str | None:
    role_id = _text(value, path, errors)
    if role_id is None:
        return None
    role = roles.get(role_id)
    if role is None:
        errors.append(f"{path}: неизвестная роль {role_id!r}")
        return None
    if permission is not None and role.get(permission) is not True:
        errors.append(f"{path}: роль {role_id!r} не имеет {permission}=true")
    return role_id


def _validate_roles(
    contract: dict[str, Any], schema: dict[str, Any], errors: list[str]
) -> dict[str, dict[str, Any]]:
    required = _schema_strings(schema, "role_required")
    roles: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_list(contract.get("roles"), "roles", errors)):
        path = f"roles[{index}]"
        role = _mapping(raw, path, errors)
        if role is None:
            continue
        _exact_keys(role, required, path, errors)
        role_id = _text(role.get("role_id"), f"{path}.role_id", errors)
        _text(role.get("responsibility"), f"{path}.responsibility", errors)
        for key in required - {"role_id", "responsibility"}:
            _boolean(role.get(key), f"{path}.{key}", errors)
        if role_id is not None:
            if role_id in roles:
                errors.append(f"{path}.role_id: дубликат {role_id!r}")
            else:
                roles[role_id] = role
    if not roles:
        errors.append("roles: нужна хотя бы одна роль")
    return roles


def _validate_condition(
    value: Any,
    schema: dict[str, Any],
    path: str,
    errors: list[str],
) -> str | None:
    condition = _mapping(value, path, errors)
    if condition is None:
        return None
    _exact_keys(condition, _schema_strings(schema, "condition_required"), path, errors)
    status = _enum(
        condition.get("status"),
        _schema_strings(schema, "condition_statuses"),
        f"{path}.status",
        errors,
    )
    rule = condition.get("rule")
    refs = _strings(condition.get("evidence_refs"), f"{path}.evidence_refs", errors, unique=True)
    if status in {"APPROVED", "NOT_APPLICABLE"}:
        _text(rule, f"{path}.rule", errors)
    elif status == "UNKNOWN" and rule is not None:
        _text(rule, f"{path}.rule", errors, allow_unknown=True)
    if status == "APPROVED" and not refs:
        errors.append(f"{path}.evidence_refs: APPROVED требует evidence")
    return status


def _validate_format_evidence(
    value: Any, schema: dict[str, Any], path: str, errors: list[str]
) -> str | None:
    evidence = _mapping(value, path, errors)
    if evidence is None:
        return None
    _exact_keys(evidence, _schema_strings(schema, "format_evidence_required"), path, errors)
    level = _enum(
        evidence.get("level"),
        _schema_strings(schema, "format_evidence_levels"),
        f"{path}.level",
        errors,
    )
    refs = _strings(evidence.get("evidence_refs"), f"{path}.evidence_refs", errors, unique=True, nonempty=True)
    observed = _iso_date_or_timestamp(evidence.get("observed_at"), f"{path}.observed_at", errors)
    if level in {"OBSERVED_REAL_SAMPLE", "PRODUCTION_CONFIRMED"} and (not refs or observed is None):
        errors.append(f"{path}: реальный evidence level требует ссылку и время наблюдения")
    return level


def _validate_source_identity(
    source: dict[str, Any], schema: dict[str, Any], path: str, errors: list[str]
) -> None:
    file_identity = _mapping(source.get("file_identity"), f"{path}.file_identity", errors)
    if file_identity is not None:
        ipath = f"{path}.file_identity"
        _exact_keys(file_identity, _schema_strings(schema, "file_identity_required"), ipath, errors)
        _strings(file_identity.get("key_fields"), f"{ipath}.key_fields", errors, unique=True, nonempty=True)
        _enum(file_identity.get("hash_algorithm"), _schema_strings(schema, "identity_hash_algorithms"), f"{ipath}.hash_algorithm", errors)
        _enum(file_identity.get("duplicate_action"), _schema_strings(schema, "file_duplicate_actions"), f"{ipath}.duplicate_action", errors)

    record_identity = _mapping(source.get("record_identity"), f"{path}.record_identity", errors)
    if record_identity is not None:
        ipath = f"{path}.record_identity"
        _exact_keys(record_identity, _schema_strings(schema, "record_identity_required"), ipath, errors)
        key_fields = _strings(record_identity.get("key_fields"), f"{ipath}.key_fields", errors, unique=True, nonempty=True)
        _strings(record_identity.get("version_fields"), f"{ipath}.version_fields", errors, unique=True, nonempty=True)
        stable_source_id = _mapping(record_identity.get("stable_source_id"), f"{ipath}.stable_source_id", errors)
        if stable_source_id is not None:
            spath = f"{ipath}.stable_source_id"
            _exact_keys(stable_source_id, _schema_strings(schema, "stable_source_id_required"), spath, errors)
            status = _enum(stable_source_id.get("status"), _schema_strings(schema, "stable_source_id_statuses"), f"{spath}.status", errors)
            absent_action = _enum(stable_source_id.get("absent_action"), _schema_strings(schema, "stable_source_id_absent_actions"), f"{spath}.absent_action", errors)
            field = stable_source_id.get("field")
            if status == "PRESENT":
                parsed_field = _text(field, f"{spath}.field", errors)
                if parsed_field is not None and parsed_field not in key_fields:
                    errors.append(f"{spath}.field: PRESENT требует поле из record_identity.key_fields")
                if absent_action != "NOT_APPLICABLE":
                    errors.append(f"{spath}.absent_action: PRESENT требует NOT_APPLICABLE")
            elif status == "ABSENT":
                if field is not None:
                    errors.append(f"{spath}.field: ABSENT требует null")
                if absent_action not in {"MANUAL_CANDIDATE_ONLY", "CREATE_EXCEPTION"}:
                    errors.append(f"{spath}.absent_action: ABSENT разрешает только MANUAL_CANDIDATE_ONLY или CREATE_EXCEPTION")
        template = _text(record_identity.get("canonical_id_template"), f"{ipath}.canonical_id_template", errors)
        if template is not None and "{" not in template:
            errors.append(f"{ipath}.canonical_id_template: шаблон должен ссылаться на поля")
        _enum(record_identity.get("collision_action"), _schema_strings(schema, "record_collision_actions"), f"{ipath}.collision_action", errors)
        _enum(record_identity.get("correction_action"), _schema_strings(schema, "record_correction_actions"), f"{ipath}.correction_action", errors)


def _validate_sources(
    contract: dict[str, Any],
    schema: dict[str, Any],
    roles: dict[str, dict[str, Any]],
    errors: list[str],
) -> tuple[set[str], dict[str, str], set[str]]:
    required = _schema_strings(schema, "source_passport_required")
    source_ids: set[str] = set()
    levels: dict[str, str] = {}
    privacy_classes: set[str] = set()
    sources = _list(contract.get("source_passports"), "source_passports", errors)
    if not sources:
        errors.append("source_passports: нужен хотя бы один источник")
    for index, raw in enumerate(sources):
        path = f"source_passports[{index}]"
        source = _mapping(raw, path, errors)
        if source is None:
            continue
        _exact_keys(source, required, path, errors)
        source_id = _text(source.get("source_id"), f"{path}.source_id", errors)
        if source_id is not None:
            if source_id in source_ids:
                errors.append(f"{path}.source_id: дубликат {source_id!r}")
            source_ids.add(source_id)
        _text(source.get("business_meaning"), f"{path}.business_meaning", errors)
        _role_ref(source.get("owner_role"), roles, f"{path}.owner_role", errors)
        mode = _enum(source.get("required_mode"), _schema_strings(schema, "source_required_modes"), f"{path}.required_mode", errors)
        condition_status = _validate_condition(source.get("condition"), schema, f"{path}.condition", errors)
        if mode == "REQUIRED" and condition_status != "NOT_APPLICABLE":
            errors.append(f"{path}.condition.status: REQUIRED требует NOT_APPLICABLE")
        if mode == "CONDITIONAL" and condition_status == "NOT_APPLICABLE":
            errors.append(f"{path}.condition.status: CONDITIONAL требует APPROVED или UNKNOWN")
        _text(source.get("delivery_rule"), f"{path}.delivery_rule", errors)
        level = _validate_format_evidence(source.get("format_evidence"), schema, f"{path}.format_evidence", errors)
        if source_id is not None and level is not None:
            levels[source_id] = level
        _text(source.get("row_grain"), f"{path}.row_grain", errors)
        _validate_source_identity(source, schema, path, errors)
        period = _mapping(source.get("period_rule"), f"{path}.period_rule", errors)
        if period is not None:
            _exact_keys(period, _schema_strings(schema, "period_rule_required"), f"{path}.period_rule", errors)
            for key in ("event_time_field", "timezone", "allocation_rule_id"):
                _text(period.get(key), f"{path}.period_rule.{key}", errors)
        _text(source.get("completeness_rule"), f"{path}.completeness_rule", errors)
        _validate_condition(source.get("zero_activity_evidence"), schema, f"{path}.zero_activity_evidence", errors)
        _strings(source.get("control_totals"), f"{path}.control_totals", errors, unique=True, nonempty=True)
        privacy = _enum(source.get("privacy_class"), _schema_strings(schema, "privacy_classes"), f"{path}.privacy_class", errors)
        if privacy is not None:
            privacy_classes.add(privacy)
    return source_ids, levels, privacy_classes


def _validate_run_identity(contract: dict[str, Any], schema: dict[str, Any], errors: list[str]) -> None:
    root = _mapping(contract.get("run_identity"), "run_identity", errors)
    if root is None:
        return
    _exact_keys(root, _schema_strings(schema, "run_identity_required"), "run_identity", errors)
    specs = (
        ("run_id", "run_id_required", "required_components", "required_run_id_components"),
        ("manifest", "manifest_required", "required_fields", "required_manifest_fields"),
        ("normalized_record_id", "normalized_record_id_required", "required_components", "required_normalized_record_components"),
        ("idempotency", "idempotency_required", "key_components", "required_idempotency_components"),
    )
    for name, required_key, list_key, schema_list_key in specs:
        value = _mapping(root.get(name), f"run_identity.{name}", errors)
        if value is None:
            continue
        _exact_keys(value, _schema_strings(schema, required_key), f"run_identity.{name}", errors)
        actual = set(_strings(value.get(list_key), f"run_identity.{name}.{list_key}", errors, unique=True, nonempty=True))
        missing = _schema_strings(schema, schema_list_key) - actual
        if missing:
            errors.append(f"run_identity.{name}.{list_key}: нет компонентов " + ", ".join(sorted(missing)))
        if name in {"run_id", "normalized_record_id"}:
            template = _text(value.get("template"), f"run_identity.{name}.template", errors)
            if template is not None:
                for component in _schema_strings(schema, schema_list_key):
                    if "{" + component + "}" not in template:
                        errors.append(f"run_identity.{name}.template: нет {{{component}}}")
    run_id = root.get("run_id") if isinstance(root.get("run_id"), dict) else {}
    _text(run_id.get("uniqueness_scope"), "run_identity.run_id.uniqueness_scope", errors)
    manifest = root.get("manifest") if isinstance(root.get("manifest"), dict) else {}
    _enum(manifest.get("hash_algorithm"), _schema_strings(schema, "identity_hash_algorithms"), "run_identity.manifest.hash_algorithm", errors)
    if manifest.get("immutable_snapshot") is not True:
        errors.append("run_identity.manifest.immutable_snapshot: должно быть true")
    normalized = root.get("normalized_record_id") if isinstance(root.get("normalized_record_id"), dict) else {}
    _enum(normalized.get("collision_action"), _schema_strings(schema, "record_collision_actions"), "run_identity.normalized_record_id.collision_action", errors)
    _enum(normalized.get("correction_action"), _schema_strings(schema, "record_correction_actions"), "run_identity.normalized_record_id.correction_action", errors)
    idempotency = root.get("idempotency") if isinstance(root.get("idempotency"), dict) else {}
    _enum(idempotency.get("duplicate_action"), _schema_strings(schema, "idempotency_duplicate_actions"), "run_identity.idempotency.duplicate_action", errors)


def _reachable(start: str, pairs: set[tuple[str, str]]) -> set[str]:
    graph: dict[str, set[str]] = {}
    for source, target in pairs:
        graph.setdefault(source, set()).add(target)
    result = {start}
    queue = deque([start])
    while queue:
        for target in graph.get(queue.popleft(), set()):
            if target not in result:
                result.add(target)
                queue.append(target)
    return result


def _can_reach_terminal(states: set[str], pairs: set[tuple[str, str]], terminals: set[str]) -> set[str]:
    reverse = {(target, source) for source, target in pairs}
    result: set[str] = set()
    for terminal in terminals & states:
        result |= _reachable(terminal, reverse)
    return result


def _validate_lifecycle(
    contract: dict[str, Any], schema: dict[str, Any], roles: dict[str, dict[str, Any]], errors: list[str]
) -> set[str]:
    lifecycle = _mapping(contract.get("lifecycle"), "lifecycle", errors)
    if lifecycle is None:
        return set()
    _exact_keys(lifecycle, {"states", "transitions"}, "lifecycle", errors)
    allowed_states = _schema_strings(schema, "required_states")
    states = set(_enum_list(lifecycle.get("states"), allowed_states, "lifecycle.states", errors, nonempty=True))
    if states != allowed_states:
        errors.append("lifecycle.states: набор должен точно совпадать со схемой")
    pairs: set[tuple[str, str]] = set()
    pair_owners: dict[tuple[str, str], str] = {}
    for index, raw in enumerate(_list(lifecycle.get("transitions"), "lifecycle.transitions", errors)):
        path = f"lifecycle.transitions[{index}]"
        transition = _mapping(raw, path, errors)
        if transition is None:
            continue
        _exact_keys(transition, _schema_strings(schema, "transition_required"), path, errors)
        source = _enum(transition.get("from"), states, f"{path}.from", errors) if states else None
        target = _enum(transition.get("to"), states, f"{path}.to", errors) if states else None
        _text(transition.get("gate_code"), f"{path}.gate_code", errors)
        _text(transition.get("signal"), f"{path}.signal", errors)
        owner = _role_ref(transition.get("owner_role"), roles, f"{path}.owner_role", errors)
        _text(transition.get("recovery_check"), f"{path}.recovery_check", errors)
        if source is not None and target is not None:
            pair = (source, target)
            if pair in pairs:
                errors.append(f"{path}: дублирует переход {source} -> {target}")
            pairs.add(pair)
            if owner is not None:
                pair_owners[pair] = owner
    required_pairs = {
        (pair[0], pair[1])
        for pair in schema.get("required_transition_pairs", [])
        if isinstance(pair, list) and len(pair) == 2 and all(isinstance(item, str) for item in pair)
    }
    for source, target in sorted(required_pairs - pairs):
        errors.append(f"lifecycle.transitions: нет обязательного перехода {source} -> {target}")
    unreachable = states - _reachable("WAITING_INPUTS", pairs)
    if unreachable:
        errors.append("lifecycle.states: недостижимы из WAITING_INPUTS: " + ", ".join(sorted(unreachable)))
    terminals = _schema_strings(schema, "terminal_states")
    dead = states - _can_reach_terminal(states, pairs, terminals)
    if dead:
        errors.append("lifecycle.states: нет пути к терминальному состоянию: " + ", ".join(sorted(dead)))
    close_owner = pair_owners.get(("READY_FOR_REVIEW", "CLOSED"))
    if close_owner is not None:
        _role_ref(close_owner, roles, "lifecycle.close_owner", errors, permission="may_close_run")
    reopen_owner = pair_owners.get(("CLOSED", "REOPEN_REQUIRED"))
    if reopen_owner is not None:
        _role_ref(reopen_owner, roles, "lifecycle.reopen_owner", errors, permission="may_reopen_run")
    return states


def _validate_completeness(
    contract: dict[str, Any], schema: dict[str, Any], source_ids: set[str], errors: list[str]
) -> tuple[str | None, str | None]:
    value = _mapping(contract.get("completeness"), "completeness", errors)
    if value is None:
        return None, None
    _exact_keys(value, _schema_strings(schema, "completeness_required"), "completeness", errors)
    perimeter = set(_strings(value.get("perimeter_source_ids"), "completeness.perimeter_source_ids", errors, unique=True, nonempty=True))
    if perimeter != source_ids:
        errors.append("completeness.perimeter_source_ids: должен точно совпадать с паспортами источников")
    covered: set[str] = set()
    for index, raw in enumerate(_list(value.get("coverage_rules"), "completeness.coverage_rules", errors)):
        path = f"completeness.coverage_rules[{index}]"
        rule = _mapping(raw, path, errors)
        if rule is None:
            continue
        _exact_keys(rule, _schema_strings(schema, "coverage_rule_required"), path, errors)
        source = _enum(rule.get("source_id"), source_ids, f"{path}.source_id", errors) if source_ids else None
        if source is not None:
            if source in covered:
                errors.append(f"{path}.source_id: повторное правило {source!r}")
            covered.add(source)
        _text(rule.get("evidence_ref"), f"{path}.evidence_ref", errors)
        _enum(rule.get("missing_action"), _schema_strings(schema, "coverage_missing_actions"), f"{path}.missing_action", errors)
    if covered != source_ids:
        errors.append("completeness.coverage_rules: нужны правила для каждого источника")
    _strings(value.get("hard_close_gate_codes"), "completeness.hard_close_gate_codes", errors, unique=True, nonempty=True)
    true_cov = _mapping(value.get("true_coverage"), "completeness.true_coverage", errors)
    true_id = None
    if true_cov is not None:
        _exact_keys(true_cov, _schema_strings(schema, "coverage_definition_required"), "completeness.true_coverage", errors)
        true_id = _text(true_cov.get("metric_id"), "completeness.true_coverage.metric_id", errors)
        _strings(true_cov.get("included_record_statuses"), "completeness.true_coverage.included_record_statuses", errors, unique=True, nonempty=True)
        _enum_list(true_cov.get("excluded_exception_statuses"), _schema_strings(schema, "required_exception_states"), "completeness.true_coverage.excluded_exception_statuses", errors, nonempty=True)
        if true_cov.get("exceptions_count_as_covered") is not False:
            errors.append("completeness.true_coverage.exceptions_count_as_covered: должно быть false")
    registration = _mapping(value.get("exception_registration"), "completeness.exception_registration", errors)
    registration_id = None
    if registration is not None:
        _exact_keys(registration, _schema_strings(schema, "exception_registration_definition_required"), "completeness.exception_registration", errors)
        registration_id = _text(registration.get("metric_id"), "completeness.exception_registration.metric_id", errors)
        _enum_list(registration.get("registered_exception_statuses"), _schema_strings(schema, "required_exception_states"), "completeness.exception_registration.registered_exception_statuses", errors, nonempty=True)
    if true_id is not None and true_id == registration_id:
        errors.append("completeness: покрытие и регистрация исключений должны ссылаться на разные метрики")
    return true_id, registration_id


def _validate_exceptions(
    contract: dict[str, Any], schema: dict[str, Any], roles: dict[str, dict[str, Any]], errors: list[str]
) -> tuple[str | None, str | None]:
    value = _mapping(contract.get("exceptions"), "exceptions", errors)
    if value is None:
        return None, None
    _exact_keys(value, _schema_strings(schema, "exceptions_required"), "exceptions", errors)
    states = set(_enum_list(value.get("queue_states"), _schema_strings(schema, "required_exception_states"), "exceptions.queue_states", errors, nonempty=True))
    if states != _schema_strings(schema, "required_exception_states"):
        errors.append("exceptions.queue_states: набор должен точно совпадать со схемой")
    fields = set(_strings(value.get("required_fields"), "exceptions.required_fields", errors, unique=True, nonempty=True))
    missing = _schema_strings(schema, "required_exception_fields") - fields
    if missing:
        errors.append("exceptions.required_fields: нет полей " + ", ".join(sorted(missing)))
    _strings(value.get("reason_codes"), "exceptions.reason_codes", errors, unique=True, nonempty=True)
    _role_ref(value.get("default_owner_role"), roles, "exceptions.default_owner_role", errors)
    closure = _role_ref(value.get("closure_owner_role"), roles, "exceptions.closure_owner_role", errors, permission="may_approve_exceptions")
    waiver = _role_ref(value.get("waiver_owner_role"), roles, "exceptions.waiver_owner_role", errors, permission="may_approve_exceptions")
    _enum(value.get("closure_rule_code"), _schema_strings(schema, "exception_closure_rule_codes"), "exceptions.closure_rule_code", errors)
    _enum(value.get("waiver_rule_code"), _schema_strings(schema, "exception_waiver_rule_codes"), "exceptions.waiver_rule_code", errors)
    return closure, waiver


def _validate_decisions(
    contract: dict[str, Any], schema: dict[str, Any], roles: dict[str, dict[str, Any]], errors: list[str]
) -> dict[str, str]:
    value = _mapping(contract.get("decision_boundaries"), "decision_boundaries", errors)
    if value is None:
        return {}
    _exact_keys(value, _schema_strings(schema, "decision_boundaries_required"), "decision_boundaries", errors)
    _enum(value.get("automation_mode"), _schema_strings(schema, "automation_modes"), "decision_boundaries.automation_mode", errors)
    deterministic = set(_enum_list(value.get("deterministic_actions"), _schema_strings(schema, "allowed_deterministic_actions"), "decision_boundaries.deterministic_actions", errors, nonempty=True))
    missing_det = _schema_strings(schema, "required_deterministic_actions") - deterministic
    if missing_det:
        errors.append("decision_boundaries.deterministic_actions: нет действий " + ", ".join(sorted(missing_det)))
    ai_actions = set(_enum_list(value.get("ai_actions"), _schema_strings(schema, "allowed_ai_actions"), "decision_boundaries.ai_actions", errors, nonempty=True))
    approvals: dict[str, str] = {}
    required_human = _schema_strings(schema, "required_human_actions")
    for index, raw in enumerate(_list(value.get("human_approvals"), "decision_boundaries.human_approvals", errors)):
        path = f"decision_boundaries.human_approvals[{index}]"
        item = _mapping(raw, path, errors)
        if item is None:
            continue
        _exact_keys(item, _schema_strings(schema, "human_approval_required"), path, errors)
        action = _enum(item.get("action"), required_human, f"{path}.action", errors)
        role = _role_ref(item.get("role_id"), roles, f"{path}.role_id", errors)
        if action is not None and role is not None:
            if action in approvals:
                errors.append(f"{path}.action: дубликат {action!r}")
            approvals[action] = role
    if set(approvals) != required_human:
        errors.append("decision_boundaries.human_approvals: нужен ровно полный набор решений")
    permission_by_action = {
        "ACCEPT_MATCH": "may_approve_exceptions",
        "POST_CLASSIFICATION": "may_approve_exceptions",
        "CLOSE_EXCEPTION": "may_approve_exceptions",
        "APPROVE_WAIVER": "may_approve_exceptions",
        "CLOSE_RUN": "may_close_run",
        "REOPEN_RUN": "may_reopen_run",
        "CHANGE_RULE": "may_change_rules",
        "APPROVE_DATA_GOVERNANCE": "may_approve_data_governance",
    }
    for action, role in approvals.items():
        permission = permission_by_action[action]
        _role_ref(role, roles, f"decision_boundaries.human_approvals[{action}]", errors, permission=permission)
    prohibited = set(_enum_list(value.get("prohibited_ai_actions"), _schema_strings(schema, "forbidden_ai_actions"), "decision_boundaries.prohibited_ai_actions", errors, nonempty=True))
    if prohibited != _schema_strings(schema, "forbidden_ai_actions"):
        errors.append("decision_boundaries.prohibited_ai_actions: нужен полный закрытый набор запретов")
    if ai_actions & prohibited:
        errors.append("decision_boundaries: ИИ получил запрещённое действие")
    if value.get("model_self_assessment_is_evidence") is not False:
        errors.append("decision_boundaries.model_self_assessment_is_evidence: должно быть false")
    if value.get("automatic_ai_posting") is not False:
        errors.append("decision_boundaries.automatic_ai_posting: должно быть false")
    return approvals


def _validate_provenance(contract: dict[str, Any], schema: dict[str, Any], errors: list[str]) -> None:
    value = _mapping(contract.get("provenance"), "provenance", errors)
    if value is None:
        return
    _exact_keys(value, _schema_strings(schema, "provenance_required"), "provenance", errors)
    for key, required_key in (
        ("required_links", "required_provenance_links"),
        ("model_record_fields", "required_model_record_fields"),
        ("retained_artifacts", "required_retained_artifacts"),
    ):
        actual = set(_strings(value.get(key), f"provenance.{key}", errors, unique=True, nonempty=True))
        missing = _schema_strings(schema, required_key) - actual
        if missing:
            errors.append(f"provenance.{key}: нет элементов " + ", ".join(sorted(missing)))
    for key in ("external_provider_version_policy", "stable_provider_call_id_policy"):
        _enum(value.get(key), _schema_strings(schema, "unavailable_provider_policies"), f"provenance.{key}", errors)


def _validate_rerun(
    contract: dict[str, Any], schema: dict[str, Any], roles: dict[str, dict[str, Any]], errors: list[str]
) -> str | None:
    value = _mapping(contract.get("rerun_and_late_data"), "rerun_and_late_data", errors)
    if value is None:
        return None
    _exact_keys(value, _schema_strings(schema, "rerun_required"), "rerun_and_late_data", errors)
    for key in ("new_run_id_required", "prior_run_immutable", "supersession_link_required", "comparison_required"):
        if value.get(key) is not True:
            errors.append(f"rerun_and_late_data.{key}: должно быть true")
    late = _mapping(value.get("late_data_policy"), "rerun_and_late_data.late_data_policy", errors)
    late_status = None
    if late is not None:
        path = "rerun_and_late_data.late_data_policy"
        _exact_keys(late, _schema_strings(schema, "late_data_policy_required"), path, errors)
        late_status = _enum(late.get("status"), _schema_strings(schema, "late_data_policy_statuses"), f"{path}.status", errors)
        refs = _strings(late.get("evidence_refs"), f"{path}.evidence_refs", errors, unique=True)
        if late_status == "APPROVED":
            _enum(late.get("rule"), _schema_strings(schema, "late_data_rules"), f"{path}.rule", errors)
            if not refs:
                errors.append(f"{path}.evidence_refs: APPROVED требует evidence")
        elif late_status == "UNKNOWN" and late.get("rule") is not None:
            errors.append(f"{path}.rule: при UNKNOWN должно быть null")
    _role_ref(value.get("reopen_owner_role"), roles, "rerun_and_late_data.reopen_owner_role", errors, permission="may_reopen_run")
    _text(value.get("recovery_check"), "rerun_and_late_data.recovery_check", errors)
    return late_status


def _validate_failure_controls(
    contract: dict[str, Any], schema: dict[str, Any], roles: dict[str, dict[str, Any]], states: set[str], errors: list[str]
) -> None:
    required_codes = _schema_strings(schema, "required_failure_codes")
    seen: set[str] = set()
    for index, raw in enumerate(_list(contract.get("failure_controls"), "failure_controls", errors)):
        path = f"failure_controls[{index}]"
        item = _mapping(raw, path, errors)
        if item is None:
            continue
        _exact_keys(item, _schema_strings(schema, "failure_control_required"), path, errors)
        code = _enum(item.get("failure_code"), required_codes, f"{path}.failure_code", errors)
        if code is not None:
            if code in seen:
                errors.append(f"{path}.failure_code: дубликат {code!r}")
            seen.add(code)
        _text(item.get("signal"), f"{path}.signal", errors)
        _enum_list(item.get("blocked_states"), states, f"{path}.blocked_states", errors, nonempty=True)
        _role_ref(item.get("owner_role"), roles, f"{path}.owner_role", errors)
        retry = _mapping(item.get("retry_policy"), f"{path}.retry_policy", errors)
        if retry is not None:
            rpath = f"{path}.retry_policy"
            _exact_keys(retry, _schema_strings(schema, "retry_policy_required"), rpath, errors)
            strategy = _enum(retry.get("strategy"), _schema_strings(schema, "retry_strategies"), f"{rpath}.strategy", errors)
            attempts = _integer(retry.get("max_attempts"), f"{rpath}.max_attempts", errors)
            _integer(retry.get("backoff_seconds"), f"{rpath}.backoff_seconds", errors)
            if strategy == "NONE" and attempts not in {None, 0}:
                errors.append(f"{rpath}.max_attempts: NONE требует 0")
            if strategy != "NONE" and attempts == 0:
                errors.append(f"{rpath}.max_attempts: retry требует хотя бы 1")
        _enum(item.get("fallback_action"), _schema_strings(schema, "fallback_actions"), f"{path}.fallback_action", errors)
        _integer(item.get("alert_deadline_minutes"), f"{path}.alert_deadline_minutes", errors, minimum=1)
        _text(item.get("recovery_check"), f"{path}.recovery_check", errors)
    if seen != required_codes:
        errors.append("failure_controls: нужен ровно полный набор failure_code")


def _validate_data_governance(
    contract: dict[str, Any], schema: dict[str, Any], roles: dict[str, dict[str, Any]], source_privacy: set[str], errors: list[str]
) -> dict[str, Any]:
    value = _mapping(contract.get("data_governance"), "data_governance", errors)
    result: dict[str, Any] = {"status": None, "retention_status": None, "backup_status": None, "restore": None}
    if value is None:
        return result
    _exact_keys(value, _schema_strings(schema, "data_governance_required"), "data_governance", errors)
    result["status"] = _enum(value.get("status"), _schema_strings(schema, "governance_statuses"), "data_governance.status", errors)
    _role_ref(value.get("owner_role"), roles, "data_governance.owner_role", errors, permission="may_approve_data_governance")
    classes = set(_enum_list(value.get("data_classes"), _schema_strings(schema, "privacy_classes"), "data_governance.data_classes", errors, nonempty=True))
    if not source_privacy <= classes:
        errors.append("data_governance.data_classes: не покрывает классы источников")
    _enum_list(value.get("allowed_storage"), _schema_strings(schema, "allowed_storage_classes"), "data_governance.allowed_storage", errors, nonempty=True)
    access = _mapping(value.get("access_control"), "data_governance.access_control", errors)
    if access is not None:
        _exact_keys(access, _schema_strings(schema, "access_control_required"), "data_governance.access_control", errors)
        for key in ("read_roles", "export_roles"):
            refs = _strings(access.get(key), f"data_governance.access_control.{key}", errors, unique=True, nonempty=True)
            for index, role in enumerate(refs):
                _role_ref(role, roles, f"data_governance.access_control.{key}[{index}]", errors)
        if access.get("least_privilege") is not True:
            errors.append("data_governance.access_control.least_privilege: должно быть true")
    retention = _mapping(value.get("retention"), "data_governance.retention", errors)
    if retention is not None:
        _exact_keys(retention, _schema_strings(schema, "retention_required"), "data_governance.retention", errors)
        result["retention_status"] = _enum(retention.get("status"), _schema_strings(schema, "retention_statuses"), "data_governance.retention.status", errors)
        deletion_method = _text(
            retention.get("deletion_method"),
            "data_governance.retention.deletion_method",
            errors,
            allow_unknown=True,
        )
        if result["retention_status"] == "APPROVED":
            _integer(retention.get("days"), "data_governance.retention.days", errors, minimum=1)
            if deletion_method == "UNKNOWN":
                errors.append("data_governance.retention.deletion_method: APPROVED требует метод удаления")
        elif retention.get("days") is not None:
            errors.append("data_governance.retention.days: при UNKNOWN должно быть null")
    backup = _mapping(value.get("backup"), "data_governance.backup", errors)
    if backup is not None:
        _exact_keys(backup, _schema_strings(schema, "backup_required"), "data_governance.backup", errors)
        result["backup_status"] = _enum(backup.get("status"), _schema_strings(schema, "backup_statuses"), "data_governance.backup.status", errors)
        _enum(backup.get("destination_class"), _schema_strings(schema, "backup_destination_classes"), "data_governance.backup.destination_class", errors)
        if backup.get("encrypted") is not True:
            errors.append("data_governance.backup.encrypted: должно быть true")
        result["restore"] = _enum(backup.get("restore_test_status"), _schema_strings(schema, "restore_test_statuses"), "data_governance.backup.restore_test_status", errors)
        if result["restore"] == "PASSED":
            _text(backup.get("last_restore_test_at"), "data_governance.backup.last_restore_test_at", errors)
        elif backup.get("last_restore_test_at") is not None:
            errors.append("data_governance.backup.last_restore_test_at: без PASSED должно быть null")
    external = _mapping(value.get("external_ai"), "data_governance.external_ai", errors)
    if external is not None:
        _exact_keys(external, _schema_strings(schema, "external_ai_required"), "data_governance.external_ai", errors)
        _enum(external.get("input_mode"), _schema_strings(schema, "external_ai_input_modes"), "data_governance.external_ai.input_mode", errors)
        if external.get("raw_personal_data_allowed") is not False:
            errors.append("data_governance.external_ai.raw_personal_data_allowed: должно быть false")
        _strings(external.get("approved_processors"), "data_governance.external_ai.approved_processors", errors, unique=True)
    redaction = _mapping(value.get("redaction"), "data_governance.redaction", errors)
    if redaction is not None:
        _exact_keys(redaction, _schema_strings(schema, "redaction_required"), "data_governance.redaction", errors)
        if redaction.get("required") is not True:
            errors.append("data_governance.redaction.required: должно быть true")
        _strings(redaction.get("protected_fields"), "data_governance.redaction.protected_fields", errors, unique=True, nonempty=True)
        _text(redaction.get("verification_method"), "data_governance.redaction.verification_method", errors)
    return result


def _validate_measurement(
    value: Any, schema: dict[str, Any], path: str, errors: list[str]
) -> tuple[str | None, float | None, str | None]:
    item = _mapping(value, path, errors)
    if item is None:
        return None, None, None
    _exact_keys(item, _schema_strings(schema, "measurement_required"), path, errors)
    status = _enum(item.get("status"), _schema_strings(schema, "measurement_statuses"), f"{path}.status", errors)
    unit = _text(item.get("unit"), f"{path}.unit", errors, allow_unknown=True)
    refs = _strings(item.get("evidence_refs"), f"{path}.evidence_refs", errors, unique=True)
    number = None
    if status == "KNOWN":
        number = _number(item.get("value"), f"{path}.value", errors, minimum=0)
        if not refs:
            errors.append(f"{path}.evidence_refs: KNOWN требует evidence")
    elif status in {"UNKNOWN", "NOT_APPLICABLE"} and item.get("value") is not None:
        errors.append(f"{path}.value: при {status} должно быть null")
    return status, number, unit


def _validate_metrics(
    contract: dict[str, Any], schema: dict[str, Any], roles: dict[str, dict[str, Any]], true_id: str | None, registration_id: str | None, errors: list[str]
) -> dict[str, dict[str, Any]]:
    root = _mapping(contract.get("metrics"), "metrics", errors)
    if root is None:
        return {}
    _exact_keys(root, _schema_strings(schema, "metrics_required"), "metrics", errors)
    seen: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_list(root.get("definitions"), "metrics.definitions", errors)):
        path = f"metrics.definitions[{index}]"
        metric = _mapping(raw, path, errors)
        if metric is None:
            continue
        _exact_keys(metric, _schema_strings(schema, "metric_required"), path, errors)
        metric_id = _text(metric.get("metric_id"), f"{path}.metric_id", errors)
        if metric_id is not None:
            if metric_id in seen:
                errors.append(f"{path}.metric_id: дубликат {metric_id!r}")
            seen[metric_id] = metric
        metric_class = _enum(metric.get("class"), _schema_strings(schema, "metric_classes"), f"{path}.class", errors)
        kind = _enum(metric.get("kind"), _schema_strings(schema, "metric_kinds"), f"{path}.kind", errors)
        _text(metric.get("definition"), f"{path}.definition", errors)
        n_status, numerator, n_unit = _validate_measurement(metric.get("numerator"), schema, f"{path}.numerator", errors)
        d_status, denominator, d_unit = _validate_measurement(metric.get("denominator"), schema, f"{path}.denominator", errors)
        r_status, result, r_unit = _validate_measurement(metric.get("result"), schema, f"{path}.result", errors)
        if kind == "RATE":
            if n_status == "NOT_APPLICABLE" or d_status == "NOT_APPLICABLE":
                errors.append(f"{path}: RATE не допускает NOT_APPLICABLE для numerator/denominator")
            elif n_status == "KNOWN" and d_status == "KNOWN" and numerator is not None and denominator is not None:
                if denominator == 0:
                    if r_status != "NOT_APPLICABLE" or result is not None:
                        errors.append(f"{path}.result: нулевой denominator требует NOT_APPLICABLE/null")
                else:
                    expected = numerator / denominator
                    if r_status != "KNOWN" or result is None or not math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9):
                        errors.append(f"{path}.result: должен равняться numerator / denominator")
                    if result is not None and not 0 <= result <= 1:
                        errors.append(f"{path}.result.value: RATE должен быть от 0 до 1")
                if n_unit != d_unit:
                    errors.append(f"{path}: numerator и denominator RATE должны иметь одну unit")
                if r_unit != "ratio":
                    errors.append(f"{path}.result.unit: RATE требует ratio")
            elif r_status != "UNKNOWN" or result is not None:
                errors.append(f"{path}.result: неизвестный numerator/denominator требует UNKNOWN/null")
        elif kind in {"COUNT", "AMOUNT", "DURATION"}:
            if d_status != "NOT_APPLICABLE" or denominator is not None:
                errors.append(f"{path}.denominator: скалярная метрика требует NOT_APPLICABLE/null")
            if n_status == "KNOWN":
                if r_status != "KNOWN" or result is None or numerator is None or not math.isclose(result, numerator):
                    errors.append(f"{path}.result: должен повторять известный numerator")
            elif r_status != "UNKNOWN" or result is not None:
                errors.append(f"{path}.result: неизвестный numerator требует UNKNOWN/null")
        _strings(metric.get("data_source_refs"), f"{path}.data_source_refs", errors, unique=True, nonempty=True)
        _enum(metric.get("frequency"), _schema_strings(schema, "metric_frequencies"), f"{path}.frequency", errors)
        _role_ref(metric.get("owner_role"), roles, f"{path}.owner_role", errors)
        if metric_id == "true_coverage_rate" and metric_class != "TRUE_COVERAGE":
            errors.append(f"{path}.class: true_coverage_rate требует TRUE_COVERAGE")
        if metric_id == "exception_registration_rate" and metric_class != "EXCEPTION_REGISTRATION":
            errors.append(f"{path}.class: exception_registration_rate требует EXCEPTION_REGISTRATION")
    missing = _schema_strings(schema, "required_metric_ids") - set(seen)
    if missing:
        errors.append("metrics.definitions: нет метрик " + ", ".join(sorted(missing)))
    if true_id != "true_coverage_rate" or registration_id != "exception_registration_rate":
        errors.append("completeness: ссылки на обязательные метрики неверны")
    return seen


def _validate_pilot(
    contract: dict[str, Any], schema: dict[str, Any], roles: dict[str, dict[str, Any]], metrics: dict[str, dict[str, Any]], errors: list[str]
) -> str | None:
    value = _mapping(contract.get("pilot"), "pilot", errors)
    if value is None:
        return None
    _exact_keys(value, _schema_strings(schema, "pilot_required"), "pilot", errors)
    _role_ref(value.get("selection_owner_role"), roles, "pilot.selection_owner_role", errors, permission="may_select_pilot")
    _text(value.get("selection_method"), "pilot.selection_method", errors)
    _strings(value.get("periods"), "pilot.periods", errors, unique=True, nonempty=True)
    if value.get("baseline_required") is not True:
        errors.append("pilot.baseline_required: должно быть true")
    _strings(value.get("baseline_evidence_refs"), "pilot.baseline_evidence_refs", errors, unique=True, nonempty=True)
    if value.get("gold_review_required") is not True:
        errors.append("pilot.gold_review_required: должно быть true")
    _strings(value.get("acceptance_gates"), "pilot.acceptance_gates", errors, unique=True, nonempty=True)
    status = _enum(value.get("measured_results_status"), _schema_strings(schema, "pilot_result_statuses"), "pilot.measured_results_status", errors)
    result_ids = set(_strings(value.get("result_metric_ids"), "pilot.result_metric_ids", errors, unique=True, nonempty=True))
    if not result_ids <= set(metrics):
        errors.append("pilot.result_metric_ids: содержит неизвестную метрику")
    missing = _schema_strings(schema, "pilot_required_metric_results") - result_ids
    if missing:
        errors.append("pilot.result_metric_ids: нет метрик " + ", ".join(sorted(missing)))
    if value.get("production_readiness_claim") is not False:
        errors.append("pilot.production_readiness_claim: должно быть false")
    return status


def _validate_economics(contract: dict[str, Any], schema: dict[str, Any], errors: list[str]) -> None:
    root = _mapping(contract.get("economics"), "economics", errors)
    if root is None:
        return
    _exact_keys(root, _schema_strings(schema, "economics_required"), "economics", errors)
    required_ids = _schema_strings(schema, "required_economic_inputs")
    expected_units = schema.get("economic_units") if isinstance(schema.get("economic_units"), dict) else {}
    inputs: dict[str, tuple[str | None, float | None, str | None]] = {}
    currencies: set[str] = set()
    for index, raw in enumerate(_list(root.get("inputs"), "economics.inputs", errors)):
        path = f"economics.inputs[{index}]"
        item = _mapping(raw, path, errors)
        if item is None:
            continue
        _exact_keys(item, _schema_strings(schema, "economic_input_required"), path, errors)
        input_id = _enum(item.get("input_id"), required_ids, f"{path}.input_id", errors)
        status = _enum(item.get("status"), _schema_strings(schema, "economic_statuses"), f"{path}.status", errors)
        unit = _text(item.get("unit"), f"{path}.unit", errors, allow_unknown=True)
        currency = _text(item.get("currency_code"), f"{path}.currency_code", errors, allow_unknown=True)
        refs = _strings(item.get("evidence_refs"), f"{path}.evidence_refs", errors, unique=True)
        observed = _iso_date_or_timestamp(item.get("observed_at"), f"{path}.observed_at", errors, allow_unknown=True)
        number = None
        if status == "KNOWN":
            number = _number(item.get("value"), f"{path}.value", errors, minimum=0)
            if not refs or observed == "UNKNOWN":
                errors.append(f"{path}: KNOWN требует evidence_refs и observed_at")
        elif status == "UNKNOWN" and item.get("value") is not None:
            errors.append(f"{path}.value: UNKNOWN требует null")
        if input_id is not None:
            if input_id in inputs:
                errors.append(f"{path}.input_id: дубликат {input_id!r}")
            inputs[input_id] = (status, number, currency)
            if unit != expected_units.get(input_id):
                errors.append(f"{path}.unit: ожидается {expected_units.get(input_id)!r}")
            if expected_units.get(input_id, "").startswith("currency"):
                if status == "KNOWN" and (currency is None or not re.fullmatch(r"[A-Z]{3}", currency)):
                    errors.append(f"{path}.currency_code: KNOWN требует ISO-код валюты")
                if status == "KNOWN" and currency is not None:
                    currencies.add(currency)
            elif currency != "NOT_APPLICABLE":
                errors.append(f"{path}.currency_code: для невалютного входа нужно NOT_APPLICABLE")
    missing = required_ids - set(inputs)
    if missing:
        errors.append("economics.inputs: нет входов " + ", ".join(sorted(missing)))
    if len(currencies) > 1:
        errors.append("economics.inputs: валютные входы должны быть в одной валюте")
    decision = _mapping(root.get("decision"), "economics.decision", errors)
    if decision is None:
        return
    _exact_keys(decision, _schema_strings(schema, "economic_decision_required"), "economics.decision", errors)
    decision_status = _enum(decision.get("status"), _schema_strings(schema, "economic_decision_statuses"), "economics.decision.status", errors)
    _enum(decision.get("formula_version"), _schema_strings(schema, "economic_formula_versions"), "economics.decision.formula_version", errors)
    decision_currency = _text(
        decision.get("currency_code"),
        "economics.decision.currency_code",
        errors,
        allow_unknown=True,
    )
    decision_refs = _strings(decision.get("evidence_refs"), "economics.decision.evidence_refs", errors, unique=True)
    all_known = not missing and all(status == "KNOWN" and number is not None for status, number, _ in inputs.values())
    if not all_known:
        if decision_status != "UNKNOWN" or decision.get("monthly_net_benefit") is not None or decision.get("payback_months") is not None:
            errors.append("economics.decision: неизвестные входы требуют UNKNOWN и null")
        if decision_currency != "UNKNOWN":
            errors.append("economics.decision.currency_code: неизвестные входы требуют UNKNOWN")
        return
    values = {key: item[1] for key, item in inputs.items()}
    assert all(value is not None for value in values.values())
    net = (
        (values["baseline_manual_minutes_per_month"] - values["target_manual_minutes_per_month"])
        * values["loaded_labor_cost_per_minute"]
        + values["baseline_material_error_cost_per_month"]
        - values["target_material_error_cost_per_month"]
        - values["monthly_operating_cost"]
    )
    payback = values["development_cost"] / net if net > 0 else None
    expected_status = "ACCEPT" if payback is not None and payback <= values["payback_threshold_months"] else "REJECT"
    reported_net = _number(decision.get("monthly_net_benefit"), "economics.decision.monthly_net_benefit", errors) if net >= 0 else decision.get("monthly_net_benefit")
    if not isinstance(reported_net, (int, float)) or isinstance(reported_net, bool) or not math.isclose(float(reported_net), net):
        errors.append("economics.decision.monthly_net_benefit: не совпадает с PAYBACK_V1")
    if payback is None:
        if decision.get("payback_months") is not None:
            errors.append("economics.decision.payback_months: при неположительной выгоде должно быть null")
    else:
        reported_payback = _number(decision.get("payback_months"), "economics.decision.payback_months", errors, minimum=0)
        if reported_payback is None or not math.isclose(reported_payback, payback, rel_tol=1e-9, abs_tol=1e-9):
            errors.append("economics.decision.payback_months: не совпадает с PAYBACK_V1")
    if decision_status != expected_status:
        errors.append(f"economics.decision.status: по PAYBACK_V1 ожидается {expected_status}")
    currency = next(iter(currencies), None)
    if decision.get("currency_code") != currency:
        errors.append("economics.decision.currency_code: не совпадает с входами")
    if not decision_refs:
        errors.append("economics.decision.evidence_refs: вычисленное решение требует evidence")


def _validate_unresolved(
    contract: dict[str, Any], schema: dict[str, Any], roles: dict[str, dict[str, Any]], errors: list[str]
) -> list[dict[str, Any]]:
    root = _mapping(contract.get("unresolved"), "unresolved", errors)
    records: list[dict[str, Any]] = []
    if root is None:
        return records
    _exact_keys(root, _schema_strings(schema, "unresolved_required"), "unresolved", errors)
    seen: set[str] = set()
    for group in ("business_questions", "pending_context", "unknown_facts"):
        for index, raw in enumerate(_list(root.get(group), f"unresolved.{group}", errors)):
            path = f"unresolved.{group}[{index}]"
            item = _mapping(raw, path, errors)
            if item is None:
                continue
            _exact_keys(item, _schema_strings(schema, "unresolved_record_required"), path, errors)
            item_id = _text(item.get("item_id"), f"{path}.item_id", errors)
            if item_id is not None:
                if item_id in seen:
                    errors.append(f"{path}.item_id: дубликат {item_id!r}")
                seen.add(item_id)
            _text(item.get("statement"), f"{path}.statement", errors)
            _role_ref(item.get("owner_role"), roles, f"{path}.owner_role", errors)
            status = _enum(item.get("status"), _schema_strings(schema, "unresolved_statuses"), f"{path}.status", errors)
            _enum_list(item.get("blocks_maturity"), _schema_strings(schema, "maturity_targets"), f"{path}.blocks_maturity", errors, nonempty=True)
            _text(item.get("establish_by"), f"{path}.establish_by", errors)
            refs = _strings(item.get("evidence_refs"), f"{path}.evidence_refs", errors, unique=True)
            if status == "OPEN" and item.get("resolution") is not None:
                errors.append(f"{path}.resolution: OPEN требует null")
            if status == "RESOLVED":
                _text(item.get("resolution"), f"{path}.resolution", errors)
                if not refs:
                    errors.append(f"{path}.evidence_refs: RESOLVED требует evidence")
            records.append(item)
    return records


def _validate_maturity(
    contract: dict[str, Any], source_levels: dict[str, str], late_status: str | None, governance: dict[str, Any], pilot_status: str | None, metrics: dict[str, dict[str, Any]], unresolved: list[dict[str, Any]], errors: list[str]
) -> None:
    status = contract.get("contract_status") if isinstance(contract.get("contract_status"), str) else None
    if status == "DRAFT" or status is None:
        return
    if any(level == "SYNTHETIC_ONLY" for level in source_levels.values()):
        errors.append(f"contract_status {status}: синтетический источник блокирует зрелость")
    if late_status != "APPROVED":
        errors.append(f"contract_status {status}: late_data_policy должен быть APPROVED")
    if governance.get("status") != "APPROVED" or governance.get("retention_status") != "APPROVED":
        errors.append(f"contract_status {status}: governance и retention должны быть APPROVED")
    if governance.get("backup_status") != "APPROVED" or governance.get("restore") != "PASSED":
        errors.append(f"contract_status {status}: backup должен быть APPROVED и restore-test PASSED")
    blocked_targets = {"PILOT_READY"}
    if status == "PILOT_EVALUATED":
        blocked_targets.add("PILOT_EVALUATED")
    for item in unresolved:
        if item.get("status") == "OPEN" and isinstance(item.get("blocks_maturity"), list):
            if blocked_targets & {target for target in item["blocks_maturity"] if isinstance(target, str)}:
                errors.append(f"contract_status {status}: открытый blocker {item.get('item_id')!r}")
    if status == "PILOT_EVALUATED":
        if pilot_status != "EVALUATED":
            errors.append("contract_status PILOT_EVALUATED: пилот должен быть EVALUATED")
        for metric_id in ("true_coverage_rate", "exception_registration_rate", "manual_minutes", "material_error_rate"):
            metric = metrics.get(metric_id)
            result = metric.get("result") if isinstance(metric, dict) and isinstance(metric.get("result"), dict) else {}
            if result.get("status") not in {"KNOWN", "NOT_APPLICABLE"}:
                errors.append(f"contract_status PILOT_EVALUATED: метрика {metric_id} не измерена")


def validate_contract(contract: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    """Вернуть ошибки формы и внутренних инвариантов; бизнес-истину не проверяет."""

    if schema is None:
        schema = load_schema()
    errors: list[str] = []
    _exact_keys(contract, _schema_strings(schema, "root_required"), "contract", errors)
    if contract.get("contract_version") != schema.get("contract_version"):
        errors.append(f"contract_version: ожидается {schema.get('contract_version')!r}")
    _text(contract.get("contract_id"), "contract_id", errors)
    status = _enum(contract.get("contract_status"), _schema_strings(schema, "contract_statuses"), "contract_status", errors)
    _text(contract.get("objective"), "objective", errors)
    scope = _mapping(contract.get("scope"), "scope", errors)
    if scope is not None:
        _exact_keys(scope, _schema_strings(schema, "scope_required"), "scope", errors)
        _strings(scope.get("included"), "scope.included", errors, nonempty=True)
        _strings(scope.get("excluded"), "scope.excluded", errors, nonempty=True)
    evidence = _mapping(contract.get("evidence_boundary"), "evidence_boundary", errors)
    if evidence is not None:
        _exact_keys(evidence, _schema_strings(schema, "evidence_boundary_required"), "evidence_boundary", errors)
        _strings(evidence.get("observed_inputs"), "evidence_boundary.observed_inputs", errors, unique=True, nonempty=True)
        _strings(evidence.get("unverified_assumptions"), "evidence_boundary.unverified_assumptions", errors, unique=True)
        if evidence.get("production_readiness_claim") is not False:
            errors.append("evidence_boundary.production_readiness_claim: должно быть false")
    roles = _validate_roles(contract, schema, errors)
    source_ids, source_levels, privacy_classes = _validate_sources(contract, schema, roles, errors)
    _validate_run_identity(contract, schema, errors)
    states = _validate_lifecycle(contract, schema, roles, errors)
    true_id, registration_id = _validate_completeness(contract, schema, source_ids, errors)
    closure_role, waiver_role = _validate_exceptions(contract, schema, roles, errors)
    approvals = _validate_decisions(contract, schema, roles, errors)
    if closure_role is not None and approvals.get("CLOSE_EXCEPTION") != closure_role:
        errors.append("exceptions.closure_owner_role: не совпадает с human approval CLOSE_EXCEPTION")
    if waiver_role is not None and approvals.get("APPROVE_WAIVER") != waiver_role:
        errors.append("exceptions.waiver_owner_role: не совпадает с human approval APPROVE_WAIVER")
    _validate_provenance(contract, schema, errors)
    late_status = _validate_rerun(contract, schema, roles, errors)
    _validate_failure_controls(contract, schema, roles, states, errors)
    governance = _validate_data_governance(contract, schema, roles, privacy_classes, errors)
    metrics = _validate_metrics(contract, schema, roles, true_id, registration_id, errors)
    pilot_status = _validate_pilot(contract, schema, roles, metrics, errors)
    _validate_economics(contract, schema, errors)
    unresolved = _validate_unresolved(contract, schema, roles, errors)
    if status is not None:
        _validate_maturity(contract, source_levels, late_status, governance, pilot_status, metrics, unresolved, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="Путь к YAML-контракту запуска")
    args = parser.parse_args(argv)
    try:
        schema = load_schema()
        contract = load_contract(args.contract)
        errors = validate_contract(contract, schema)
    except ContractReadError as error:
        print(f"ОШИБКА: {error}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ОШИБКА: {error}", file=sys.stderr)
        print(f"INVALID: найдено ошибок: {len(errors)}", file=sys.stderr)
        return 1
    print("VALID: форма и внутренние инварианты run-contract v1.1 соблюдены.")
    print("Это не подтверждает бизнес-истину, полноту реальных данных или готовность к production.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
