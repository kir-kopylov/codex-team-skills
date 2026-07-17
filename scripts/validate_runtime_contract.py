#!/usr/bin/env python3
"""Проверяет единый контракт доставки skills в Codex и Claude Code."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


AGENTS_RUNTIME_BEGIN = "<!-- BEGIN GENERATED RUNTIME CONTRACT -->"
AGENTS_RUNTIME_END = "<!-- END GENERATED RUNTIME CONTRACT -->"
CLAUDE_RUNTIME_BEGIN = "<!-- BEGIN GENERATED CLAUDE RUNTIME CONTRACT -->"
CLAUDE_RUNTIME_END = "<!-- END GENERATED CLAUDE RUNTIME CONTRACT -->"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
PLUGIN_RUNTIME_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_.~-])(?:[A-Za-z0-9_.~-]+/)*"
    r"\.(?:codex|claude)-plugin(?:/[A-Za-z0-9_.~-]+)*/?"
    r"(?![A-Za-z0-9_./~-])",
    re.IGNORECASE,
)
HOME_SKILLS_LITERAL_RE = re.compile(
    r"~/\.[A-Za-z][A-Za-z0-9_-]*/skills/?(?![A-Za-z0-9_/-])",
    re.IGNORECASE,
)
RUNTIME_ENV_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*(?:SKILLS_DIR|SKILLS_SRC)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
SMOKE_JOB_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?:claude|codex)-[A-Za-z0-9-]*smoke(?![A-Za-z0-9-])",
    re.IGNORECASE,
)
RUNTIME_TEST_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_])test_(?:claude|codex)[A-Za-z0-9_]*\.py(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)

TOP_LEVEL_KEYS = {"schema_version", "identity", "shared", "runtimes"}
IDENTITY_KEYS = {"marketplace", "plugin"}
SHARED_KEYS = {"plugin_root", "skills"}
RUNTIME_KEYS = {
    "id",
    "display_name",
    "plugin_manifest",
    "marketplace_manifest",
    "marketplace_source",
    "skill_discovery",
    "version_policy",
    "delivery",
}
EXPECTED_RUNTIME_IDS = {"codex", "claude_code"}
EXPECTED_RUNTIME_DISPLAY_NAMES = {"codex": "Codex", "claude_code": "Claude Code"}
EXPECTED_CODEX_BUILDER = "scripts/build_release_bundle.py"
EXPECTED_CODEX_BUILD_JOB = "build-release-bundle"
EXPECTED_CLAUDE_SYNC_SCRIPT = "scripts/pull-skills.sh"


class RuntimeContractError(ValueError):
    """Контракт отсутствует, противоречив или расходится с репозиторием."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise RuntimeContractError(f"Повторяющийся YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeContractError(message)


def _require_mapping(value: Any, context: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{context}: ожидается mapping")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    _require(not missing and not extra, f"{context}: missing={missing}, extra={extra}")


def _require_string(value: Any, context: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{context}: ожидается непустая строка")
    return value


def load_runtime_contract(path: Path) -> dict[str, Any]:
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, yaml.YAMLError, RuntimeContractError) as exc:
        if isinstance(exc, RuntimeContractError):
            raise
        raise RuntimeContractError(f"Не удалось прочитать {path}: {exc}") from exc
    return _require_mapping(data, str(path))


def _validate_repo_path_literal(value: Any, context: str) -> str:
    literal = _require_string(value, context)
    _require("\\" not in literal, f"{context}: используйте POSIX path, не backslash: {literal}")
    _require(not literal.startswith("/"), f"{context}: absolute path запрещён: {literal}")
    path = PurePosixPath(literal)
    _require(path.parts and ".." not in path.parts, f"{context}: path не должен содержать '..': {literal}")
    return literal


def exact_case_path(root: Path, literal: str, context: str) -> Path:
    """Разрешает repo-relative path и сверяет регистр каждого сегмента."""

    _validate_repo_path_literal(literal, context)
    current = root
    for part in PurePosixPath(literal).parts:
        if part == ".":
            continue
        _require(current.is_dir(), f"{context}: parent не является папкой: {current}")
        entries = {entry.name: entry for entry in current.iterdir()}
        if part not in entries:
            case_matches = sorted(name for name in entries if name.casefold() == part.casefold())
            if case_matches:
                raise RuntimeContractError(
                    f"{context}: неверный регистр сегмента {part!r}; на диске {case_matches}"
                )
            raise RuntimeContractError(f"{context}: path не существует: {literal}")
        current = entries[part]
    return current


def _load_json_strict(path: Path) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeContractError(f"{path}: повторяющийся JSON key {key!r}")
            result[key] = value
        return result

    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(f"Не удалось прочитать JSON {path}: {exc}") from exc
    return _require_mapping(data, str(path))


def _validate_contract_schema(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _require_exact_keys(contract, TOP_LEVEL_KEYS, "runtime-contract.yaml")
    _require(type(contract["schema_version"]) is int and contract["schema_version"] == 1, "schema_version: нужна 1")

    identity = _require_mapping(contract["identity"], "identity")
    _require_exact_keys(identity, IDENTITY_KEYS, "identity")
    _require_string(identity["marketplace"], "identity.marketplace")
    _require_string(identity["plugin"], "identity.plugin")

    shared = _require_mapping(contract["shared"], "shared")
    _require_exact_keys(shared, SHARED_KEYS, "shared")
    _validate_repo_path_literal(shared["plugin_root"], "shared.plugin_root")
    _validate_repo_path_literal(shared["skills"], "shared.skills")

    runtimes = contract["runtimes"]
    _require(isinstance(runtimes, list), "runtimes: ожидается list, не mapping")
    runtime_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_runtime in enumerate(runtimes):
        runtime = _require_mapping(raw_runtime, f"runtimes[{index}]")
        _require_exact_keys(runtime, RUNTIME_KEYS, f"runtimes[{index}]")
        runtime_id = _require_string(runtime["id"], f"runtimes[{index}].id")
        _require(runtime_id not in runtime_by_id, f"runtimes: повторяющийся id {runtime_id!r}")
        runtime_by_id[runtime_id] = runtime

    _require(set(runtime_by_id) == EXPECTED_RUNTIME_IDS, f"runtimes ids должны быть {sorted(EXPECTED_RUNTIME_IDS)}")

    for runtime_id, runtime in runtime_by_id.items():
        _require(
            runtime["display_name"] == EXPECTED_RUNTIME_DISPLAY_NAMES[runtime_id],
            f"{runtime_id}.display_name: ожидается {EXPECTED_RUNTIME_DISPLAY_NAMES[runtime_id]!r}",
        )
        _validate_repo_path_literal(runtime["plugin_manifest"], f"{runtime_id}.plugin_manifest")
        _validate_repo_path_literal(runtime["marketplace_manifest"], f"{runtime_id}.marketplace_manifest")

        source = _require_mapping(runtime["marketplace_source"], f"{runtime_id}.marketplace_source")
        discovery = _require_mapping(runtime["skill_discovery"], f"{runtime_id}.skill_discovery")
        delivery = _require_mapping(runtime["delivery"], f"{runtime_id}.delivery")

        if runtime_id == "codex":
            _require_exact_keys(source, {"kind", "source", "path"}, "codex.marketplace_source")
            _require(source["kind"] == "local_object", "codex.marketplace_source.kind: нужна local_object")
            _require(source["source"] == "local", "codex.marketplace_source.source: нужна local")
            _validate_repo_path_literal(source["path"], "codex.marketplace_source.path")

            _require_exact_keys(discovery, {"kind", "field", "value"}, "codex.skill_discovery")
            _require(discovery["kind"] == "manifest_field", "codex.skill_discovery.kind: нужна manifest_field")
            _require(discovery["field"] == "skills", "codex.skill_discovery.field: нужна skills")
            _require(discovery["value"] == "./skills/", "codex.skill_discovery.value: нужна ./skills/")
            _require(runtime["version_policy"] == "required_semver", "codex.version_policy: нужна required_semver")

            _require_exact_keys(delivery, {"kind", "builder", "ci_job"}, "codex.delivery")
            _require(delivery["kind"] == "signed_bundle", "codex.delivery.kind: нужна signed_bundle")
            builder = _validate_repo_path_literal(delivery["builder"], "codex.delivery.builder")
            _require(
                builder == EXPECTED_CODEX_BUILDER,
                f"codex.delivery.builder: schema v1 требует {EXPECTED_CODEX_BUILDER}",
            )
            _require(
                delivery["ci_job"] == EXPECTED_CODEX_BUILD_JOB,
                f"codex.delivery.ci_job: schema v1 требует {EXPECTED_CODEX_BUILD_JOB}",
            )
        else:
            _require_exact_keys(source, {"kind", "value"}, "claude_code.marketplace_source")
            _require(source["kind"] == "relative_path_string", "claude_code.marketplace_source.kind: нужна relative_path_string")
            _validate_repo_path_literal(source["value"], "claude_code.marketplace_source.value")

            _require_exact_keys(discovery, {"kind", "value"}, "claude_code.skill_discovery")
            _require(discovery["kind"] == "plugin_root_convention", "claude_code.skill_discovery.kind: нужна plugin_root_convention")
            _require(discovery["value"] == "skills", "claude_code.skill_discovery.value: нужна skills")
            _require(runtime["version_policy"] == "forbidden", "claude_code.version_policy: нужна forbidden")

            _require_exact_keys(delivery, {"kind", "legacy_sync"}, "claude_code.delivery")
            _require(
                delivery["kind"] == "native_marketplace_with_legacy_sync",
                "claude_code.delivery.kind: нужна native_marketplace_with_legacy_sync",
            )
            sync = _require_mapping(delivery["legacy_sync"], "claude_code.delivery.legacy_sync")
            _require_exact_keys(
                sync,
                {"script", "source_env", "destination_env", "default_destination", "ci_job"},
                "claude_code.delivery.legacy_sync",
            )
            sync_script = _validate_repo_path_literal(
                sync["script"],
                "claude_code.delivery.legacy_sync.script",
            )
            _require(
                sync_script == EXPECTED_CLAUDE_SYNC_SCRIPT,
                "claude_code.delivery.legacy_sync.script: schema v1 требует "
                f"{EXPECTED_CLAUDE_SYNC_SCRIPT}",
            )
            for key in ("source_env", "destination_env", "default_destination", "ci_job"):
                _require_string(sync[key], f"claude_code.delivery.legacy_sync.{key}")
            _require(sync["source_env"] == "TEAM_SKILLS_SRC", "claude_code source_env: нужна TEAM_SKILLS_SRC")
            _require(sync["destination_env"] == "CLAUDE_SKILLS_DIR", "claude_code destination_env: нужна CLAUDE_SKILLS_DIR")
            _require(sync["default_destination"] == "~/.claude/skills/", "claude_code default_destination: нужна ~/.claude/skills/")
            _require(sync["ci_job"] == "claude-sync-smoke", "claude_code ci_job: нужна claude-sync-smoke")

    return runtime_by_id


def _marketplace_plugin_entry(marketplace: dict[str, Any], plugin_name: str, context: str) -> dict[str, Any]:
    plugins = marketplace.get("plugins")
    _require(isinstance(plugins, list), f"{context}.plugins: ожидается list")
    matches = [item for item in plugins if isinstance(item, dict) and item.get("name") == plugin_name]
    _require(len(matches) == 1, f"{context}: plugin {plugin_name!r} должен встречаться ровно один раз")
    return matches[0]


def _shell_line_invokes_script(line: str, script: str) -> bool:
    try:
        tokens = shlex.split(line, comments=True, posix=True)
    except ValueError:
        return False
    if not tokens:
        return False

    assignment_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
    index = 0
    if tokens[index] == "env":
        index += 1
    while index < len(tokens) and assignment_re.match(tokens[index]):
        index += 1
    if index >= len(tokens):
        return False

    accepted_paths = {script, f"./{script}"}
    command = tokens[index]
    if command in accepted_paths:
        return True
    interpreter = Path(command).name
    shell_or_python = interpreter in {"bash", "sh", "zsh"} or bool(
        re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", interpreter)
    )
    if shell_or_python and index + 1 < len(tokens):
        return tokens[index + 1] in accepted_paths
    return False


def validate_ci_job_invokes_entrypoint(workflow: dict[str, Any], job_name: str, script: str) -> None:
    jobs = _require_mapping(workflow.get("jobs"), "CI workflow.jobs")
    job = _require_mapping(jobs.get(job_name), f"CI workflow.jobs.{job_name}")
    steps = job.get("steps")
    _require(isinstance(steps, list), f"CI job {job_name!r}: steps должен быть list")
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("run"), str):
            continue
        if any(_shell_line_invokes_script(line, script) for line in step["run"].splitlines()):
            return
    raise RuntimeContractError(f"CI job {job_name!r} не вызывает declared entrypoint {script!r}")


def validate_runtime_contract(root: Path, contract: dict[str, Any]) -> None:
    root = root.resolve()
    runtime_by_id = _validate_contract_schema(contract)
    identity = contract["identity"]
    shared = contract["shared"]

    plugin_root = exact_case_path(root, shared["plugin_root"], "shared.plugin_root")
    skills = exact_case_path(root, shared["skills"], "shared.skills")
    _require(plugin_root.is_dir(), "shared.plugin_root должен быть папкой")
    _require(skills.is_dir(), "shared.skills должен быть папкой")
    _require(skills == plugin_root / "skills", "shared.skills должен быть <plugin_root>/skills")

    manifest_paths: set[Path] = set()
    marketplace_paths: set[Path] = set()

    for runtime_id, runtime in runtime_by_id.items():
        manifest_path = exact_case_path(root, runtime["plugin_manifest"], f"{runtime_id}.plugin_manifest")
        marketplace_path = exact_case_path(root, runtime["marketplace_manifest"], f"{runtime_id}.marketplace_manifest")
        _require(manifest_path.is_file(), f"{runtime_id}.plugin_manifest должен быть файлом")
        _require(marketplace_path.is_file(), f"{runtime_id}.marketplace_manifest должен быть файлом")
        _require(manifest_path not in manifest_paths, "Два runtime не могут использовать один plugin manifest")
        _require(marketplace_path not in marketplace_paths, "Два runtime не могут использовать один marketplace manifest")
        manifest_paths.add(manifest_path)
        marketplace_paths.add(marketplace_path)

        expected_manifest_dir = ".codex-plugin" if runtime_id == "codex" else ".claude-plugin"
        _require(
            manifest_path.parent.name == expected_manifest_dir and manifest_path.parent.parent == plugin_root,
            f"{runtime_id}.plugin_manifest должен лежать в {shared['plugin_root']}/{expected_manifest_dir}/plugin.json",
        )

        manifest = _load_json_strict(manifest_path)
        marketplace = _load_json_strict(marketplace_path)
        _require(manifest.get("name") == identity["plugin"], f"{runtime_id} manifest.name расходится с identity.plugin")
        _require(marketplace.get("name") == identity["marketplace"], f"{runtime_id} marketplace.name расходится с identity.marketplace")
        entry = _marketplace_plugin_entry(marketplace, identity["plugin"], f"{runtime_id}.marketplace")

        source = runtime["marketplace_source"]
        if source["kind"] == "local_object":
            expected_source: Any = {"source": source["source"], "path": source["path"]}
            source_literal = source["path"]
        else:
            expected_source = source["value"]
            source_literal = source["value"]
        _require(entry.get("source") == expected_source, f"{runtime_id} marketplace source расходится с runtime-contract.yaml")
        source_path = exact_case_path(root, source_literal, f"{runtime_id}.marketplace_source")
        _require(source_path == plugin_root, f"{runtime_id} marketplace source должен вести в shared.plugin_root")

        policy = runtime["version_policy"]
        if policy == "required_semver":
            version = manifest.get("version")
            _require(isinstance(version, str) and bool(SEMVER_RE.fullmatch(version)), f"{runtime_id} manifest.version должен быть semver")
        else:
            _require("version" not in manifest, f"{runtime_id} manifest не должен содержать version")

        discovery = runtime["skill_discovery"]
        if discovery["kind"] == "manifest_field":
            _require(
                manifest.get(discovery["field"]) == discovery["value"],
                f"{runtime_id} manifest.{discovery['field']} расходится с контрактом",
            )
            discovered_skills = exact_case_path(plugin_root, discovery["value"], f"{runtime_id}.skill_discovery")
        else:
            discovered_skills = exact_case_path(plugin_root, discovery["value"], f"{runtime_id}.skill_discovery")
        _require(discovered_skills == skills, f"{runtime_id} должен читать shared.skills")

    codex_builder = exact_case_path(
        root,
        runtime_by_id["codex"]["delivery"]["builder"],
        "codex.delivery.builder",
    )
    _require(codex_builder.is_file(), "codex.delivery.builder должен быть файлом")

    sync = runtime_by_id["claude_code"]["delivery"]["legacy_sync"]
    sync_script = exact_case_path(root, sync["script"], "claude_code.delivery.legacy_sync.script")
    _require(sync_script.is_file(), "claude_code legacy sync script должен быть файлом")
    sync_text = sync_script.read_text(encoding="utf-8")
    for key in ("source_env", "destination_env", "default_destination"):
        _require(sync[key] in sync_text, f"legacy sync script не содержит contract literal {sync[key]!r}")

    workflow_path = exact_case_path(root, ".github/workflows/tests.yml", "CI workflow")
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    workflow = _require_mapping(workflow, str(workflow_path))
    codex_delivery = runtime_by_id["codex"]["delivery"]
    validate_ci_job_invokes_entrypoint(
        workflow,
        codex_delivery["ci_job"],
        codex_delivery["builder"],
    )
    validate_ci_job_invokes_entrypoint(workflow, sync["ci_job"], sync["script"])


def _runtime_fact_lines(contract: dict[str, Any]) -> tuple[str, ...]:
    runtime_by_id = _validate_contract_schema(contract)
    shared = contract["shared"]
    codex = runtime_by_id["codex"]
    claude = runtime_by_id["claude_code"]
    sync = claude["delivery"]["legacy_sync"]

    return (
        f"Both runtimes consume the same `{shared['skills']}/` tree.",
        "",
        "| Concern | Codex | Claude Code |",
        "| --- | --- | --- |",
        f"| Plugin manifest | `{codex['plugin_manifest']}` | `{claude['plugin_manifest']}` |",
        f"| Marketplace metadata | `{codex['marketplace_manifest']}` | `{claude['marketplace_manifest']}` |",
        f"| Skill discovery | manifest field `{codex['skill_discovery']['field']}` = `{codex['skill_discovery']['value']}` | plugin-root convention `{claude['skill_discovery']['value']}/` |",
        "| Version policy | semver `version` is required | `version` is forbidden |",
        f"| Delivery | signed bundle built by `{codex['delivery']['builder']}` | native marketplace; legacy folder sync through `{sync['script']}` |",
        f"| CI delivery job | `{codex['delivery']['ci_job']}` invokes the builder | `{sync['ci_job']}` invokes the legacy sync |",
        f"| Folder-sync destination | not applicable | `{sync['default_destination']}` via `{sync['destination_env']}` |",
        "",
        f"The legacy Claude Code sync reads `{sync['source_env']}` as its source override.",
    )


def render_agents_runtime_block(contract: dict[str, Any]) -> str:
    return "\n".join(
        (
            AGENTS_RUNTIME_BEGIN,
            "The runtime facts below are generated from `runtime-contract.yaml`. Edit the",
            "contract, not this block.",
            "",
            *_runtime_fact_lines(contract),
            AGENTS_RUNTIME_END,
        )
    )


def render_claude_runtime_block(contract: dict[str, Any]) -> str:
    return "\n".join(
        (
            CLAUDE_RUNTIME_BEGIN,
            "The runtime facts below are generated from `runtime-contract.yaml`. Edit the",
            "contract, not this block.",
            "",
            *_runtime_fact_lines(contract),
            CLAUDE_RUNTIME_END,
        )
    )


def _extract_generated_runtime_block(
    text: str,
    *,
    begin: str,
    end: str,
    document_name: str,
) -> str:
    _require(text.count(begin) == 1, f"{document_name} должен содержать один marker {begin}")
    _require(text.count(end) == 1, f"{document_name} должен содержать один marker {end}")
    start = text.index(begin)
    block_end = text.index(end, start) + len(end)
    return text[start:block_end]


def _plugin_literal_variants(literal: str) -> set[str]:
    variants = {literal}
    parts = PurePosixPath(literal).parts
    for index, part in enumerate(parts):
        if part in {".codex-plugin", ".claude-plugin"}:
            variants.add(PurePosixPath(*parts[index:]).as_posix())
    return variants


def validate_reserved_runtime_literals(
    root: Path,
    contract: dict[str, Any],
    text: str,
    generated_block: str,
    *,
    document_name: str,
) -> None:
    runtime_by_id = _validate_contract_schema(contract)
    plugin_literals: set[str] = {".codex-plugin", ".claude-plugin"}
    home_destinations: set[str] = set()
    env_names: set[str] = set()
    ci_jobs: set[str] = set()

    for runtime in runtime_by_id.values():
        for key in ("plugin_manifest", "marketplace_manifest"):
            literal = runtime[key]
            if "-plugin" in literal:
                plugin_literals.update(_plugin_literal_variants(literal))
        delivery = runtime["delivery"]
        if "legacy_sync" in delivery:
            sync = delivery["legacy_sync"]
            home_destinations.add(sync["default_destination"])
            env_names.update((sync["source_env"], sync["destination_env"]))
            ci_jobs.add(sync["ci_job"])

    outside = text.replace(generated_block, "", 1)
    for match in PLUGIN_RUNTIME_LITERAL_RE.finditer(outside):
        literal = match.group(0)
        _require(
            literal in plugin_literals,
            f"{document_name}: неизвестный или неоднозначный plugin literal {literal!r}",
        )
    for match in HOME_SKILLS_LITERAL_RE.finditer(outside):
        literal = match.group(0)
        _require(
            literal in home_destinations,
            f"{document_name}: неизвестная runtime skills destination {literal!r}",
        )
    for match in RUNTIME_ENV_LITERAL_RE.finditer(outside):
        literal = match.group(0)
        _require(literal in env_names, f"{document_name}: неизвестная runtime env variable {literal!r}")
    for match in SMOKE_JOB_LITERAL_RE.finditer(outside):
        literal = match.group(0)
        _require(literal in ci_jobs, f"{document_name}: неизвестный CI job {literal!r}")
    for match in RUNTIME_TEST_LITERAL_RE.finditer(outside):
        literal = match.group(0)
        test_path = exact_case_path(root, f"tests/{literal}", f"{document_name} test literal {literal}")
        _require(test_path.is_file(), f"{document_name}: test literal не является файлом: {literal}")


def validate_no_runtime_fact_duplicates(
    contract: dict[str, Any],
    text: str,
    generated_block: str,
    *,
    document_name: str,
) -> None:
    runtime_by_id = _validate_contract_schema(contract)
    codex = runtime_by_id["codex"]
    claude = runtime_by_id["claude_code"]
    sync = claude["delivery"]["legacy_sync"]
    protected_literals = {
        codex["plugin_manifest"],
        claude["plugin_manifest"],
        codex["marketplace_manifest"],
        claude["marketplace_manifest"],
        codex["delivery"]["builder"],
        codex["delivery"]["ci_job"],
        sync["script"],
        sync["source_env"],
        sync["destination_env"],
        sync["default_destination"],
        sync["ci_job"],
    }
    outside = text.replace(generated_block, "", 1)
    duplicates = sorted(literal for literal in protected_literals if literal in outside)
    _require(
        not duplicates,
        f"{document_name}: runtime facts продублированы вне generated block: {duplicates}",
    )


def validate_agents_runtime_block(root: Path, contract: dict[str, Any], text: str) -> None:
    actual = _extract_generated_runtime_block(
        text,
        begin=AGENTS_RUNTIME_BEGIN,
        end=AGENTS_RUNTIME_END,
        document_name="AGENTS.md",
    )
    expected = render_agents_runtime_block(contract)
    _require(actual == expected, "AGENTS.md: generated runtime block расходится с runtime-contract.yaml")
    validate_no_runtime_fact_duplicates(contract, text, actual, document_name="AGENTS.md")
    validate_reserved_runtime_literals(root, contract, text, actual, document_name="AGENTS.md")


def validate_claude_runtime_block(root: Path, contract: dict[str, Any], text: str) -> None:
    actual = _extract_generated_runtime_block(
        text,
        begin=CLAUDE_RUNTIME_BEGIN,
        end=CLAUDE_RUNTIME_END,
        document_name="CLAUDE.md",
    )
    expected = render_claude_runtime_block(contract)
    _require(actual == expected, "CLAUDE.md: generated runtime block расходится с runtime-contract.yaml")
    validate_no_runtime_fact_duplicates(contract, text, actual, document_name="CLAUDE.md")
    validate_reserved_runtime_literals(root, contract, text, actual, document_name="CLAUDE.md")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeContractError(f"Не удалось прочитать {path}: {exc}") from exc


def validate_repository(
    root: Path,
    contract_path: Path | None = None,
    agents_path: Path | None = None,
    claude_path: Path | None = None,
) -> None:
    root = root.resolve()
    contract_path = contract_path or root / "runtime-contract.yaml"
    agents_path = agents_path or root / "AGENTS.md"
    claude_path = claude_path or root / "CLAUDE.md"
    contract = load_runtime_contract(contract_path)
    validate_runtime_contract(root, contract)
    validate_agents_runtime_block(root, contract, _read_text(agents_path))
    validate_claude_runtime_block(root, contract, _read_text(claude_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Корень репозитория")
    parser.add_argument("--contract", type=Path, help="Путь к runtime-contract.yaml")
    parser.add_argument("--agents", type=Path, help="Путь к AGENTS.md")
    parser.add_argument("--claude", type=Path, help="Путь к CLAUDE.md")
    render_group = parser.add_mutually_exclusive_group()
    render_group.add_argument(
        "--render-agents-block",
        action="store_true",
        help="Напечатать канонический generated block для AGENTS.md",
    )
    render_group.add_argument(
        "--render-claude-block",
        action="store_true",
        help="Напечатать канонический generated block для CLAUDE.md",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    contract_path = args.contract or root / "runtime-contract.yaml"
    try:
        contract = load_runtime_contract(contract_path)
        if args.render_agents_block:
            print(render_agents_runtime_block(contract))
            return 0
        if args.render_claude_block:
            print(render_claude_runtime_block(contract))
            return 0
        validate_runtime_contract(root, contract)
        agents_path = args.agents or root / "AGENTS.md"
        claude_path = args.claude or root / "CLAUDE.md"
        validate_agents_runtime_block(root, contract, agents_path.read_text(encoding="utf-8"))
        validate_claude_runtime_block(root, contract, claude_path.read_text(encoding="utf-8"))
    except (OSError, RuntimeContractError) as exc:
        print(f"Ошибка runtime contract: {exc}", file=sys.stderr)
        return 1

    print("Runtime contract, AGENTS.md и CLAUDE.md согласованы.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
