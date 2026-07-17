from __future__ import annotations

import copy
import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import ROOT


VALIDATOR_PATH = ROOT / "scripts" / "validate_runtime_contract.py"
CONTRACT_PATH = ROOT / "runtime-contract.yaml"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_runtime_contract", VALIDATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def load_contract() -> dict:
    return validator.load_runtime_contract(CONTRACT_PATH)


def runtime(contract: dict, runtime_id: str) -> dict:
    return next(item for item in contract["runtimes"] if item["id"] == runtime_id)


def test_runtime_contract_matches_repository() -> None:
    validator.validate_repository(ROOT)


def test_agents_generated_runtime_block_matches_contract() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    validator.validate_agents_runtime_block(ROOT, load_contract(), text)


def test_claude_generated_runtime_block_matches_contract() -> None:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    validator.validate_claude_runtime_block(ROOT, load_contract(), text)


def test_runtime_contract_uses_list_with_unique_runtime_ids() -> None:
    contract = load_contract()
    assert isinstance(contract["runtimes"], list)
    ids = [item["id"] for item in contract["runtimes"]]
    assert len(ids) == len(set(ids))

    duplicate = copy.deepcopy(contract)
    duplicate["runtimes"].append(copy.deepcopy(duplicate["runtimes"][0]))
    with pytest.raises(validator.RuntimeContractError, match="повторяющийся id"):
        validator.validate_runtime_contract(ROOT, duplicate)


def test_runtime_contract_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    duplicate = tmp_path / "runtime-contract.yaml"
    duplicate.write_text(
        "schema_version: 1\nschema_version: 1\n",
        encoding="utf-8",
    )

    with pytest.raises(validator.RuntimeContractError, match="Повторяющийся YAML key"):
        validator.load_runtime_contract(duplicate)


def test_runtime_contract_rejects_unknown_schema_keys() -> None:
    contract = load_contract()
    contract["shared"]["guessed_codex_skills"] = "~/.codex/skills/"
    with pytest.raises(validator.RuntimeContractError, match="extra"):
        validator.validate_runtime_contract(ROOT, contract)


def test_runtime_contract_rejects_wrong_case_repo_path() -> None:
    contract = load_contract()
    runtime(contract, "codex")["plugin_manifest"] = "plugins/team-skills/.Codex-plugin/plugin.json"
    with pytest.raises(validator.RuntimeContractError, match="регистр"):
        validator.validate_runtime_contract(ROOT, contract)


def test_runtime_contract_rejects_swapped_runtime_manifests() -> None:
    contract = load_contract()
    codex = runtime(contract, "codex")
    claude = runtime(contract, "claude_code")
    codex["plugin_manifest"], claude["plugin_manifest"] = (
        claude["plugin_manifest"],
        codex["plugin_manifest"],
    )
    with pytest.raises(validator.RuntimeContractError, match="plugin_manifest должен лежать"):
        validator.validate_runtime_contract(ROOT, contract)


def test_runtime_contract_rejects_renamed_plugin_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(
        ROOT,
        repo,
        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "dist"),
    )
    original = repo / "plugins" / "team-skills" / ".codex-plugin" / "plugin.json"
    renamed = original.with_name("renamed.json")
    shutil.copy2(original, renamed)

    contract = load_contract()
    runtime(contract, "codex")["plugin_manifest"] = renamed.relative_to(repo).as_posix()

    with pytest.raises(validator.RuntimeContractError, match=r"/plugin\.json"):
        validator.validate_runtime_contract(repo, contract)


@pytest.mark.parametrize(
    ("runtime_id", "replacement", "error"),
    (
        ("codex", "scripts/new_skill.py", "codex.delivery.builder"),
        ("claude_code", "AGENTS.md", "claude_code.delivery.legacy_sync.script"),
    ),
)
def test_runtime_contract_rejects_wrong_existing_delivery_entrypoints(
    runtime_id: str,
    replacement: str,
    error: str,
) -> None:
    contract = load_contract()
    selected = runtime(contract, runtime_id)
    if runtime_id == "codex":
        selected["delivery"]["builder"] = replacement
    else:
        selected["delivery"]["legacy_sync"]["script"] = replacement

    with pytest.raises(validator.RuntimeContractError, match=error):
        validator.validate_runtime_contract(ROOT, contract)


def test_runtime_contract_rejects_wrong_codex_build_job() -> None:
    contract = load_contract()
    runtime(contract, "codex")["delivery"]["ci_job"] = "pytest"

    with pytest.raises(validator.RuntimeContractError, match="codex.delivery.ci_job"):
        validator.validate_runtime_contract(ROOT, contract)


def test_declared_delivery_ci_jobs_invoke_declared_entrypoints() -> None:
    contract = load_contract()
    codex_delivery = runtime(contract, "codex")["delivery"]
    sync = runtime(contract, "claude_code")["delivery"]["legacy_sync"]
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))

    declared = (
        (codex_delivery["ci_job"], codex_delivery["builder"]),
        (sync["ci_job"], sync["script"]),
    )
    for job_name, entrypoint in declared:
        validator.validate_ci_job_invokes_entrypoint(workflow, job_name, entrypoint)

        no_op_workflow = copy.deepcopy(workflow)
        no_op_workflow["jobs"][job_name]["steps"] = [
            {"name": "No-op", "run": f"echo {entrypoint}"},
        ]
        with pytest.raises(validator.RuntimeContractError, match="не вызывает declared entrypoint"):
            validator.validate_ci_job_invokes_entrypoint(no_op_workflow, job_name, entrypoint)


def test_generated_block_rejects_global_claude_to_codex_replacement() -> None:
    contract = load_contract()
    valid = validator.render_agents_runtime_block(contract)
    mutated = (
        valid.replace("Claude Code", "Codex")
        .replace(".claude-plugin", ".codex-plugin")
        .replace("~/.claude/skills/", "~/.codex/skills/")
        .replace("CLAUDE_SKILLS_DIR", "CODEX_SKILLS_DIR")
        .replace("claude-sync-smoke", "codex-sync-smoke")
    )
    with pytest.raises(validator.RuntimeContractError, match="generated runtime block"):
        validator.validate_agents_runtime_block(ROOT, contract, mutated)


def test_generated_block_rejects_swapped_manifest_columns() -> None:
    contract = load_contract()
    valid = validator.render_agents_runtime_block(contract)
    codex_path = runtime(contract, "codex")["plugin_manifest"]
    claude_path = runtime(contract, "claude_code")["plugin_manifest"]
    mutated = valid.replace(codex_path, "__CLAUDE__").replace(claude_path, codex_path).replace("__CLAUDE__", claude_path)
    with pytest.raises(validator.RuntimeContractError, match="generated runtime block"):
        validator.validate_agents_runtime_block(ROOT, contract, mutated)


def test_claude_generated_block_rejects_cross_runtime_replacement() -> None:
    contract = load_contract()
    valid = validator.render_claude_runtime_block(contract)
    mutated = valid.replace("Claude Code", "Codex").replace(".claude-plugin", ".codex-plugin")
    assert mutated != valid

    with pytest.raises(validator.RuntimeContractError, match="CLAUDE.md: generated runtime block"):
        validator.validate_claude_runtime_block(ROOT, contract, mutated)


@pytest.mark.parametrize(
    ("renderer", "validate", "document_name"),
    (
        (validator.render_agents_runtime_block, validator.validate_agents_runtime_block, "AGENTS.md"),
        (validator.render_claude_runtime_block, validator.validate_claude_runtime_block, "CLAUDE.md"),
    ),
)
def test_generated_documents_reject_runtime_fact_duplicates_outside_block(
    renderer,
    validate,
    document_name: str,
) -> None:
    contract = load_contract()
    duplicated = renderer(contract) + "\n\nDuplicate: `scripts/pull-skills.sh`\n"

    with pytest.raises(
        validator.RuntimeContractError,
        match="продублированы вне generated block",
    ) as exc_info:
        validate(ROOT, contract, duplicated)
    assert document_name in str(exc_info.value)


def test_claude_document_rejects_invented_runtime_literal_outside_block() -> None:
    contract = load_contract()
    text = validator.render_claude_runtime_block(contract) + "\n\nInvented: `.Codex-plugin`\n"

    with pytest.raises(
        validator.RuntimeContractError,
        match="неизвестный или неоднозначный",
    ):
        validator.validate_claude_runtime_block(ROOT, contract, text)


@pytest.mark.parametrize(
    ("renderer", "validate", "document_name"),
    (
        (validator.render_agents_runtime_block, validator.validate_agents_runtime_block, "AGENTS.md"),
        (validator.render_claude_runtime_block, validator.validate_claude_runtime_block, "CLAUDE.md"),
    ),
)
@pytest.mark.parametrize(
    ("markdown_template", "markdown_context"),
    (
        ("Invented: {literal}\n", "plain"),
        ("```text\n{literal}\n```\n", "fenced"),
    ),
)
@pytest.mark.parametrize(
    "invented_literal",
    (
        ".Codex-plugin",
        "~/.codex/skills/",
        "CODEX_SKILLS_DIR",
        "Codex-sync-smoke",
        "test_codex_manifest.py",
    ),
)
def test_generated_documents_reject_invented_runtime_literals_in_all_markdown_contexts(
    renderer,
    validate,
    document_name: str,
    markdown_template: str,
    markdown_context: str,
    invented_literal: str,
) -> None:
    contract = load_contract()
    text = renderer(contract) + "\n\n" + markdown_template.format(literal=invented_literal)

    with pytest.raises(validator.RuntimeContractError) as exc_info:
        validate(ROOT, contract, text)
    assert document_name in str(exc_info.value), markdown_context


@pytest.mark.parametrize(
    "invented_literal",
    (
        "~/.codex/skills/",
        "CODEX_SKILLS_DIR",
        "Codex-sync-smoke",
        ".Codex-plugin",
        "test_codex_manifest.py",
    ),
)
def test_reserved_runtime_literals_reject_invented_analogs(invented_literal: str) -> None:
    contract = load_contract()
    text = validator.render_agents_runtime_block(contract) + f"\nInvented: `{invented_literal}`\n"
    with pytest.raises(validator.RuntimeContractError):
        validator.validate_agents_runtime_block(ROOT, contract, text)
