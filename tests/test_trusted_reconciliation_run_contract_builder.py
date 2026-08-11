from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

from conftest import ROOT, load_registry


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "trusted-reconciliation-run-contract-builder"
VALIDATOR = SKILL / "scripts" / "validate_run_contract.py"
EXAMPLE = SKILL / "references" / "run-contract.example.yaml"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_run_contract", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_contract() -> dict:
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


def _metric(contract: dict, metric_id: str) -> dict:
    return next(item for item in contract["metrics"]["definitions"] if item["metric_id"] == metric_id)


def test_package_is_experimental_design_only_and_uses_executable_paths() -> None:
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(SKILL)

    assert registry["status"] == "experimental"
    assert registry["owner"] == "@kir-kopylov"
    assert len(registry["example_files"]) == 5
    for relative in registry["example_files"]:
        assert (SKILL / relative).is_file()
    for required in (
        "проектирует контракт",
        "не загружает банковские файлы",
        "production_readiness_claim: false",
        "PROPOSE_ONLY",
        "failure_control",
        "data_governance",
        "$RECONCILIATION_SKILL_DIR/scripts/validate_run_contract.py",
        "$RECONCILIATION_SKILL_DIR/scripts/log_usage_feedback.py",
    ):
        assert required in body
    assert "<skill-dir>" not in body


def test_synthetic_draft_passes_cli_with_narrow_verdict() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(EXAMPLE)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "run-contract v1.1" in result.stdout
    assert "не подтверждает бизнес-истину" in result.stdout
    assert "готовность к production" in result.stdout


def test_loader_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    text = EXAMPLE.read_text(encoding="utf-8").replace(
        'contract_status: "DRAFT"',
        'contract_status: "PILOT_READY"\ncontract_status: "DRAFT"',
        1,
    )
    duplicate.write_text(text, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(duplicate)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "повторяющийся ключ" in result.stderr


def test_maturity_status_cannot_be_promoted_without_real_pilot_gates() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    contract["contract_status"] = "PILOT_EVALUATED"

    errors = validator.validate_contract(contract)

    assert any("синтетический источник блокирует зрелость" in error for error in errors)
    assert any("late_data_policy должен быть APPROVED" in error for error in errors)
    assert any("governance и retention должны быть APPROVED" in error for error in errors)
    assert any("пилот должен быть EVALUATED" in error for error in errors)
    assert any("открытый blocker" in error for error in errors)


def test_zero_denominator_cannot_publish_hundred_percent() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    metric = _metric(contract, "true_coverage_rate")
    metric["numerator"] = {"status": "KNOWN", "value": 0, "unit": "records", "evidence_refs": ["n"]}
    metric["denominator"] = {"status": "KNOWN", "value": 0, "unit": "records", "evidence_refs": ["d"]}
    metric["result"] = {"status": "KNOWN", "value": 1.0, "unit": "ratio", "evidence_refs": ["r"]}

    errors = validator.validate_contract(contract)

    assert any("нулевой denominator требует NOT_APPLICABLE/null" in error for error in errors)


def test_ai_actions_are_closed_and_human_actions_require_role_authority() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    contract["decision_boundaries"]["ai_actions"] = ["AUTO_APPROVE_AND_POST"]
    close = next(item for item in contract["decision_boundaries"]["human_approvals"] if item["action"] == "CLOSE_RUN")
    close["role_id"] = "source_operator"

    errors = validator.validate_contract(contract)

    assert any("ai_actions[0]: неизвестное значение" in error for error in errors)
    assert any("не имеет may_close_run=true" in error for error in errors)


def test_lifecycle_requires_reverse_path_from_every_nonterminal_state() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    contract["lifecycle"]["transitions"] = [
        item
        for item in contract["lifecycle"]["transitions"]
        if not (item["from"] == "INPUTS_INCOMPLETE" and item["to"] == "WAITING_INPUTS")
    ]

    errors = validator.validate_contract(contract)

    assert any("нет обязательного перехода INPUTS_INCOMPLETE -> WAITING_INPUTS" in error for error in errors)
    assert any("нет пути к терминальному состоянию: INPUTS_INCOMPLETE" in error for error in errors)


def test_exception_closure_and_waiver_require_matching_authorized_roles() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    contract["exceptions"]["closure_owner_role"] = "source_operator"
    contract["exceptions"]["waiver_owner_role"] = "source_operator"

    errors = validator.validate_contract(contract)

    assert any("closure_owner_role" in error and "may_approve_exceptions" in error for error in errors)
    assert any("waiver_owner_role" in error and "may_approve_exceptions" in error for error in errors)
    assert any("не совпадает с human approval CLOSE_EXCEPTION" in error for error in errors)


def test_failure_controls_require_complete_operational_set() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    contract["failure_controls"] = [
        item for item in contract["failure_controls"] if item["failure_code"] != "AI_UNAVAILABLE"
    ]

    errors = validator.validate_contract(contract)

    assert any("нужен ровно полный набор failure_code" in error for error in errors)


def test_data_governance_blocks_real_pilot_until_approved_and_restored() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    contract["contract_status"] = "PILOT_READY"
    for source in contract["source_passports"]:
        source["format_evidence"]["level"] = "OBSERVED_REAL_SAMPLE"
        source["zero_activity_evidence"] = {
            "status": "APPROVED",
            "rule": "Наблюдаемый пустой экспорт.",
            "evidence_refs": ["zero-evidence"],
        }
    contract["rerun_and_late_data"]["late_data_policy"] = {
        "status": "APPROVED",
        "rule": "REOPEN_AFFECTED_PERIOD",
        "evidence_refs": ["late-policy"],
    }
    for group in contract["unresolved"].values():
        for item in group:
            item["status"] = "RESOLVED"
            item["resolution"] = "Решено для теста."
            item["evidence_refs"] = ["resolution"]

    errors = validator.validate_contract(contract)

    assert any("governance и retention должны быть APPROVED" in error for error in errors)
    assert any("backup должен быть APPROVED и restore-test PASSED" in error for error in errors)


def test_typed_economics_rejects_fiction_and_recomputes_payback() -> None:
    validator = _load_validator()
    bad = _valid_contract()
    item = bad["economics"]["inputs"][0]
    item.update(status="KNOWN", value="invented", evidence_refs=["claim"], observed_at="2026-08-12")
    assert any("ожидается конечное число" in error for error in validator.validate_contract(bad))

    good = _valid_contract()
    values = {
        "baseline_manual_minutes_per_month": 1000,
        "target_manual_minutes_per_month": 200,
        "loaded_labor_cost_per_minute": 1,
        "baseline_material_error_cost_per_month": 500,
        "target_material_error_cost_per_month": 100,
        "development_cost": 10000,
        "monthly_operating_cost": 200,
        "payback_threshold_months": 12,
    }
    currency_inputs = {
        "loaded_labor_cost_per_minute",
        "baseline_material_error_cost_per_month",
        "target_material_error_cost_per_month",
        "development_cost",
        "monthly_operating_cost",
    }
    for economic_input in good["economics"]["inputs"]:
        input_id = economic_input["input_id"]
        economic_input.update(
            status="KNOWN",
            value=values[input_id],
            currency_code="KZT" if input_id in currency_inputs else "NOT_APPLICABLE",
            evidence_refs=[f"evidence-{input_id}"],
            observed_at="2026-08-12",
        )
    good["economics"]["decision"] = {
        "status": "ACCEPT",
        "monthly_net_benefit": 1000,
        "payback_months": 10,
        "currency_code": "KZT",
        "formula_version": "PAYBACK_V1",
        "evidence_refs": ["calculation-v1"],
    }
    assert validator.validate_contract(good) == []


def test_source_evidence_and_strong_identity_are_not_decorative() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    contract["source_passports"][0]["record_identity"]["version_fields"] = []
    contract["run_identity"]["run_id"]["template"] = "constant-run-id"

    errors = validator.validate_contract(contract)

    assert any("version_fields: нужен хотя бы один элемент" in error for error in errors)
    assert any("run_identity.run_id.template: нет {period_start}" in error for error in errors)


def test_weak_record_key_cannot_masquerade_as_stable_source_identity() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    identity = contract["source_passports"][0]["record_identity"]
    identity["key_fields"] = ["amount", "date"]
    identity["version_fields"] = ["source_record_version"]

    errors = validator.validate_contract(contract)

    assert any("stable_source_id.field: PRESENT требует поле" in error for error in errors)

    identity["stable_source_id"] = {
        "status": "ABSENT",
        "field": None,
        "absent_action": "AUTO_MATCH",
    }
    errors = validator.validate_contract(contract)
    assert any("stable_source_id.absent_action" in error for error in errors)


def test_observed_times_are_iso_and_unresolved_blocks_maturity_is_nonempty() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    contract["source_passports"][0]["format_evidence"]["observed_at"] = "12/08/2026"
    contract["unresolved"]["pending_context"][0]["blocks_maturity"] = []
    values = {
        "baseline_manual_minutes_per_month": 100,
        "target_manual_minutes_per_month": 50,
        "loaded_labor_cost_per_minute": 10,
        "baseline_material_error_cost_per_month": 1000,
        "target_material_error_cost_per_month": 0,
        "development_cost": 10000,
        "monthly_operating_cost": 500,
        "payback_threshold_months": 12,
    }
    currency_inputs = {
        "loaded_labor_cost_per_minute",
        "baseline_material_error_cost_per_month",
        "target_material_error_cost_per_month",
        "development_cost",
        "monthly_operating_cost",
    }
    for item in contract["economics"]["inputs"]:
        item.update(
            status="KNOWN",
            value=values[item["input_id"]],
            currency_code="KZT" if item["input_id"] in currency_inputs else "NOT_APPLICABLE",
            evidence_refs=["observed"],
            observed_at="yesterday",
        )

    errors = validator.validate_contract(contract)

    assert any("format_evidence.observed_at: ожидается ISO" in error for error in errors)
    assert any("economics.inputs[0].observed_at: ожидается ISO" in error for error in errors)
    assert any("blocks_maturity: нужен хотя бы один элемент" in error for error in errors)


def test_unresolved_records_require_owner_resolution_evidence_and_maturity_dependency() -> None:
    validator = _load_validator()
    contract = _valid_contract()
    item = contract["unresolved"]["pending_context"][0]
    item["owner_role"] = ["source_operator"]
    item["resolution"] = "Уже решено"
    item["blocks_maturity"] = ["UNKNOWN_LEVEL"]

    errors = validator.validate_contract(contract)

    assert any("owner_role: ожидается непустая строка" in error for error in errors)
    assert any("blocks_maturity[0]: неизвестное значение" in error for error in errors)
    assert any("resolution: OPEN требует null" in error for error in errors)


def _scalar_paths(value, prefix=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _scalar_paths(child, prefix + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _scalar_paths(child, prefix + (index,))
    else:
        yield prefix


def _replace_at(value, path, replacement):
    current = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement


def test_every_scalar_shape_failure_returns_errors_instead_of_crashing() -> None:
    validator = _load_validator()
    schema = validator.load_schema()
    base = _valid_contract()

    for path in _scalar_paths(base):
        mutated = copy.deepcopy(base)
        _replace_at(mutated, path, [{"invalid": "shape"}])
        errors = validator.validate_contract(mutated, schema)
        assert isinstance(errors, list), path
        assert errors, path
