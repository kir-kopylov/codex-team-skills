from __future__ import annotations

import re

import pytest
import yaml

from conftest import ROOT, load_registry


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "pr-semantic-verifier"

VERDICTS = {"PROVED", "PARTIAL", "PROXY_ONLY", "UNVERIFIED", "DISPROVED"}
FINDINGS = {
    "implementation-defect",
    "test-contract-defect",
    "introduced-regression",
    "pre-existing-failure",
    "coverage-gap",
    "evidence-scope-gap",
    "environment-uncertain",
    "contract-changed",
    "stale-fixture",
}
CLAIM_FIELDS = {
    "claim",
    "essential",
    "required_observation",
    "available_evidence",
    "evidence_freshness",
    "proves",
    "does_not_prove",
    "claim_verdict",
}
ORACLE_QUESTIONS = {
    "could-pass-while-broken",
    "could-fail-while-correct",
}
AGGREGATION = {
    "any-essential-disproved": "DISPROVED",
    "all-essential-direct": "PROVED",
    "mixed-proved-unresolved": "PARTIAL",
    "indirect-only": "PROXY_ONLY",
    "no-comparable-evidence": "UNVERIFIED",
}
VERDICT_RULES = {
    "PROVED": "all-essential-direct",
    "PARTIAL": "mixed-proved-unresolved",
    "PROXY_ONLY": "indirect-only",
    "UNVERIFIED": "no-comparable-evidence",
    "DISPROVED": "any-essential-disproved",
}
ORACLE_PURPOSES = {
    "could-pass-while-broken": "detect-false-green",
    "could-fail-while-correct": "detect-test-contract-defect",
}
ORACLE_QUESTION_TEXTS = {
    "could-pass-while-broken": "Может ли тест пройти, когда обещанный результат всё ещё сломан?",
    "could-fail-while-correct": "Может ли тест упасть, хотя реализация соответствует исходному требованию?",
}
EVIDENCE_LAYERS = [
    "repository",
    "local-test",
    "CI",
    "review",
    "merge",
    "installation",
    "runtime",
    "user-outcome",
]
INTENT_CONTRACT = {
    "priority": ["user-goal", "issue-or-spec", "pr-body"],
    "evidence_only": ["code", "tests"],
    "conflict_action": "ask-one-question",
}
MUTATION_POLICY = {
    "verification": {
        "mode": "read-only",
        "allowed": ["read", "run-focused-checks", "temporary-artifacts"],
        "prohibited": [
            "edit-tracked-files",
            "rerun-ci",
            "comment",
            "commit",
            "push",
            "merge",
            "release",
        ],
        "result": "report-only",
    },
    "explicit-fix": {
        "sequence": ["verdict", "handoff"],
        "execution": "specialized-workflow",
        "prohibited": ["silent-mutation"],
    },
}
BASE_HEAD_CASES = {
    "base-pass-head-fail": {
        "base": {"pass"},
        "head": {"fail"},
        "attribution": {"head-only-failure"},
        "finding": {"introduced-regression", "comparable-and-valid-oracle"},
        "semantic": {"evaluate-claim-separately"},
    },
    "same-failure-both": {
        "base": {"fail", "same-signature"},
        "head": {"fail", "same-signature"},
        "attribution": {"failure-present-on-base"},
        "finding": {"pre-existing-failure"},
        "semantic": {"evaluate-claim-separately"},
    },
    "different-failure-both": {
        "base": {"fail", "signature-a"},
        "head": {"fail", "signature-b"},
        "attribution": {"attribution-inconclusive"},
        "finding": {"none-by-matrix-alone"},
        "semantic": {"evaluate-claim-separately"},
    },
    "base-fail-head-pass": {
        "base": {"fail"},
        "head": {"pass"},
        "attribution": {"observed-failure-removed"},
        "finding": {"none-by-matrix-alone"},
        "semantic": {"evaluate-claim-separately"},
    },
    "both-pass": {
        "base": {"pass"},
        "head": {"pass"},
        "attribution": {"failure-not-reproduced"},
        "finding": {"none-by-matrix-alone"},
        "semantic": {"evaluate-claim-separately"},
    },
    "execution-uncertain": {
        "base": {"timeout/setup/flake"},
        "head": {"any"},
        "attribution": {"attribution-inconclusive"},
        "finding": {"environment-uncertain"},
        "semantic": {"UNVERIFIED-for-attribution"},
    },
}
REQUIRED_EXAMPLES = {
    "examples/good-01.md",
    "examples/good-02.md",
    "examples/good-03.md",
    "examples/good-04.md",
    "examples/anti-01.md",
    "examples/anti-02.md",
    "examples/anti-03.md",
}
EVAL_CASES = {
    "false-green-string-check",
    "false-green-mock",
    "base-pass-head-fail",
    "same-failure-both",
    "different-failure-both",
    "base-fail-head-pass",
    "contract-change",
    "stale-fixture",
    "runtime-unknown",
    "insufficient-evidence",
}
BASE_HEAD_EVAL_CONTRACT = {
    "base-pass-head-fail": "base-pass-head-fail",
    "same-failure-both": "same-failure-both",
    "different-failure-both": "different-failure-both",
    "base-fail-head-pass": "base-fail-head-pass",
}


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects ambiguous duplicate contract keys."""


def construct_unique_mapping(loader: UniqueKeyLoader, node, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_unique_mapping,
)


def strict_yaml_load(value: str):
    return yaml.load(value, Loader=UniqueKeyLoader)


def read(relative: str) -> str:
    return (SKILL / relative).read_text(encoding="utf-8")


def section(relative: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)",
        read(relative),
    )
    assert match, f"{relative}: нет секции {heading!r}"
    return match.group(1)


def table_rows(relative: str, heading: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section(relative, heading).splitlines()
        if line.strip().startswith("|")
    ]


def code_tokens(cells: list[str]) -> list[str]:
    return [
        token
        for cell in cells
        for token in re.findall(r"`([^`]+)`", cell)
    ]


def first_code_column(relative: str, heading: str) -> set[str]:
    values = []
    for cells in table_rows(relative, heading):
        match = re.fullmatch(r"`([^`]+)`", cells[0])
        if match:
            values.append(match.group(1))
    assert len(values) == len(set(values)), f"{relative}: duplicate rows in {heading}"
    return set(values)


def code_map(relative: str, heading: str) -> dict[str, str]:
    result = {}
    for cells in table_rows(relative, heading):
        tokens = code_tokens(cells)
        if len(tokens) >= 2:
            assert tokens[0] not in result, f"{relative}: duplicate key {tokens[0]} in {heading}"
            result[tokens[0]] = tokens[-1]
    return result


def yaml_block(relative: str, heading: str, root_key: str):
    match = re.search(
        r"(?ms)```yaml\s*\n(.*?)^```\s*$",
        section(relative, heading),
    )
    assert match, f"{relative}: нет YAML-контракта в секции {heading!r}"
    data = strict_yaml_load(match.group(1))
    assert isinstance(data, dict) and root_key in data
    return data[root_key]


def structured_text_template(relative: str, heading: str) -> dict:
    match = re.search(
        r"(?ms)```text\s*\n(.*?)^```\s*$",
        section(relative, heading),
    )
    assert match, f"{relative}: нет структурированного text-шаблона в секции {heading!r}"
    data = strict_yaml_load(match.group(1))
    assert isinstance(data, dict)
    return data


def eval_case_text(case_id: str) -> str:
    match = re.search(
        rf"(?ms)^###\s+Case\s+\d+\s*[-—:]\s*`{re.escape(case_id)}`\s*\n"
        r"(.*?)(?=^###\s+Case\s+|^##\s+|\Z)",
        read("references/eval-rubric.md"),
    )
    assert match, f"references/eval-rubric.md: нет case {case_id!r}"
    return match.group(1)


def evidence_layers() -> list[str]:
    layers = []
    for line in section("references/verdict-model.md", "Лестница Доказательств").splitlines():
        match = re.match(r"\d+\.\s+`([^`]+)`", line)
        if match:
            layers.append(match.group(1))
    return layers


def test_registry_and_package_keep_experimental_read_only_boundary() -> None:
    registry = load_registry(SKILL)
    listed_examples = set(registry["example_files"])

    assert registry["owner"] == "@kir-kopylov"
    assert registry["status"] == "experimental"
    assert registry["evaluation"] == {
        "status": "not-run",
        "required_before_team_ready": True,
        "rubric": "references/eval-rubric.md",
        "minimum_cases": 10,
    }
    assert listed_examples == REQUIRED_EXAMPLES
    assert {path.relative_to(SKILL).as_posix() for path in (SKILL / "examples").glob("*.md")} == REQUIRED_EXAMPLES
    assert all("TODO" not in read(relative) for relative in listed_examples)

    assert {
        path.relative_to(SKILL).as_posix()
        for path in (SKILL / "references").glob("*.md")
    } == {
        "references/verdict-model.md",
        "references/base-head-attribution.md",
        "references/eval-rubric.md",
    }
    assert {path.name for path in (SKILL / "scripts").iterdir() if path.is_file()} == {
        "log_usage_feedback.py"
    }
    assert not (SKILL / "agents").exists()

    assert yaml_block(
        "SKILL.md",
        "Входы И Источник Требования",
        "intent_contract",
    ) == INTENT_CONTRACT
    assert yaml_block(
        "SKILL.md",
        "Read-Only Граница И Handoff",
        "mutation_policy",
    ) == MUTATION_POLICY

    skill = read("SKILL.md")
    for target in {
        "gh-fix-ci",
        "gh-address-comments",
        "git-pr-lifecycle-safeguard",
        "add-team-skill",
        "production-forensic-auditor",
        "stuck-troubleshooting-reframe",
    }:
        assert f"`{target}`" in skill


def test_verdict_reference_defines_the_complete_semantic_contract() -> None:
    reference = "references/verdict-model.md"

    assert first_code_column(reference, "semantic_verdict") == VERDICTS
    assert code_map(reference, "semantic_verdict") == VERDICT_RULES
    assert first_code_column(reference, "finding_types") == FINDINGS
    assert first_code_column(reference, "claim_evidence_fields") == CLAIM_FIELDS
    assert first_code_column(reference, "test_oracle_questions") == ORACLE_QUESTIONS
    assert code_map(reference, "test_oracle_questions") == ORACLE_PURPOSES
    assert code_map(reference, "aggregation") == AGGREGATION
    assert {condition: verdict for verdict, condition in VERDICT_RULES.items()} == AGGREGATION
    assert evidence_layers() == EVIDENCE_LAYERS


def test_result_template_requires_both_oracle_questions_for_every_test() -> None:
    template = structured_text_template("SKILL.md", "Формат Результата")
    oracle_rows = template["Проверка test oracle (обязательна для каждого теста)"]

    assert isinstance(oracle_rows, list) and len(oracle_rows) == 1
    assert oracle_rows[0] == {
        "test": None,
        "questions": {
            question_id: {
                "question": question_text,
                "answer": None,
                "evidence": None,
            }
            for question_id, question_text in ORACLE_QUESTION_TEXTS.items()
        },
    }


def test_contract_yaml_loader_rejects_duplicate_oracle_keys() -> None:
    duplicate = """questions:
  could-pass-while-broken: first
  could-pass-while-broken: second
"""

    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key"):
        strict_yaml_load(duplicate)


def test_base_head_reference_keeps_attribution_cautious() -> None:
    rows = {}
    for cells in table_rows("references/base-head-attribution.md", "base_head_cases"):
        tokens = code_tokens(cells)
        if tokens:
            assert len(cells) == 6
            case_id = tokens[0]
            assert case_id not in rows
            rows[case_id] = {
                "base": set(code_tokens([cells[1]])),
                "head": set(code_tokens([cells[2]])),
                "attribution": set(code_tokens([cells[3]])),
                "finding": set(code_tokens([cells[4]])),
                "semantic": set(code_tokens([cells[5]])),
            }

    assert rows == BASE_HEAD_CASES


def test_examples_cover_false_confidence_and_routing_boundaries() -> None:
    expected = {
        "examples/good-01.md": {
            "run_verifier": True,
            "semantic_verdict": "PROXY_ONLY",
            "finding_types": ["evidence-scope-gap", "coverage-gap"],
            "highest_proven_layer": "repository",
            "unverified_layers": ["installation", "runtime", "user-outcome"],
            "mutation_allowed": False,
        },
        "examples/good-02.md": {
            "run_verifier": True,
            "semantic_verdict": "PROVED",
            "finding_types": [
                "test-contract-defect",
                "contract-changed",
                "stale-fixture",
            ],
            "highest_proven_layer": "local-test",
            "mutation_allowed": False,
        },
        "examples/good-03.md": {
            "run_verifier": True,
            "semantic_verdict": "UNVERIFIED",
            "finding_types": ["pre-existing-failure"],
            "highest_proven_layer": "local-test",
            "unverified_layers": ["claim-outcome"],
            "mutation_allowed": False,
        },
        "examples/good-04.md": {
            "run_verifier": True,
            "semantic_verdict": "PARTIAL",
            "finding_types": ["evidence-scope-gap"],
            "highest_proven_layer": "merge",
            "unverified_layers": ["installation", "runtime", "user-outcome"],
            "mutation_allowed": False,
        },
        "examples/anti-01.md": {
            "run_verifier": False,
            "route_to": "gh-fix-ci",
            "mutation_allowed": False,
        },
        "examples/anti-02.md": {
            "run_verifier": False,
            "route_to": "production-forensic-auditor",
            "mutation_allowed": False,
        },
        "examples/anti-03.md": {
            "run_verifier": False,
            "route_to": "git-pr-lifecycle-safeguard",
            "secondary_route": "add-team-skill",
            "mutation_allowed": False,
        },
    }

    assert {
        relative: yaml_block(relative, "Ожидаемое Поведение", "decision")
        for relative in REQUIRED_EXAMPLES
    } == expected


def test_exceptions_and_evaluation_cover_required_failure_classes() -> None:
    registered = set(load_registry(SKILL)["example_files"])
    exceptions = strict_yaml_load(read("known-exceptions.yaml"))["exceptions"]

    assert len(exceptions) == 5
    assert {
        "examples/good-01.md",
        "examples/good-02.md",
        "examples/good-03.md",
        "examples/good-04.md",
    } <= {item["source_example"] for item in exceptions}
    for item in exceptions:
        assert item["source_example"] in registered
        assert (SKILL / item["source_example"]).is_file()

    rubric = read("references/eval-rubric.md")
    case_ids = set(
        re.findall(
            r"(?m)^###\s+Case\s+\d+\s*[-—:]\s*`([^`]+)`\s*$",
            rubric,
        )
    )
    assert case_ids == EVAL_CASES
    eval_contract = yaml_block(
        "references/eval-rubric.md",
        "Base/Head Контракт Оценки",
        "base_head_eval_contract",
    )
    assert eval_contract == BASE_HEAD_EVAL_CONTRACT
    assert all(case_id in EVAL_CASES for case_id in eval_contract)
    assert all(matrix_case in BASE_HEAD_CASES for matrix_case in eval_contract.values())
    assert BASE_HEAD_CASES[eval_contract["different-failure-both"]] == {
        "base": {"fail", "signature-a"},
        "head": {"fail", "signature-b"},
        "attribution": {"attribution-inconclusive"},
        "finding": {"none-by-matrix-alone"},
        "semantic": {"evaluate-claim-separately"},
    }
    assert set(code_tokens([eval_case_text("different-failure-both")])) == {
        "different-failure-both",
        "base_head_cases",
        "execution-uncertain",
    }
    assert BASE_HEAD_CASES["execution-uncertain"]["finding"] == {
        "environment-uncertain"
    }
    assert code_map("references/eval-rubric.md", "promotion_gate") == {
        "independent-evaluators": "2",
        "false-proved": "0",
        "weakened-invariants": "0",
        "primary-classification": "at-least-9-of-10",
        "unavailable-external-layers": "explicitly-unverified",
        "real-pr-classes": "3",
    }
