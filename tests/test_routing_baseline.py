from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from conftest import ROOT


SCRIPT_PATH = ROOT / "scripts" / "routing_baseline.py"
MODEL = "synthetic-judge"
ALPHA = "alpha-one"
BETA = "beta-two"


@pytest.fixture
def routing(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("routing_baseline_under_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "registry"
    skills = root / "plugins" / "team-skills" / "skills"
    skills.mkdir(parents=True)
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "SKILLS", skills)

    def unexpected_judge(*args, **kwargs):
        pytest.fail("Тест не должен обращаться к реальной модели")

    monkeypatch.setattr(module, "ask_judge", unexpected_judge)
    return module


def add_skill(routing, name):
    folder = routing.SKILLS / name
    (folder / "examples").mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: "Синтетическая процедура {name}"\n---\n',
        encoding="utf-8",
    )
    (folder / "skill.yaml").write_text(
        json.dumps(
            {"status": "experimental", "natural_triggers": [f"Запрос для {name}"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (folder / "examples" / "good-01.md").write_text(
        f"# Синтетический пример\n\n## Вход\nПример для {name}.\n\n"
        "## Ожидаемое Поведение\nОбработать запрос.\n\n## Нельзя\nМенять задачу.\n",
        encoding="utf-8",
    )


@pytest.fixture
def library(routing):
    for name in (ALPHA, BETA, "gamma-three", "delta-four", "epsilon-five"):
        add_skill(routing, name)
    return routing


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def invoke(routing, monkeypatch, out, *args, source="triggers"):
    monkeypatch.setattr(
        sys, "argv",
        [str(SCRIPT_PATH), "--out", str(out), "--source", source, *args],
    )
    return routing.main()


def inputs(out, source="triggers"):
    return read_json(out / f"inputs-{source}.json")


def summary(out, source="triggers"):
    return read_json(out / f"summary-{source}-{MODEL}.json")


def install_successful_judge(routing, monkeypatch, out, calls, source="triggers"):
    codes = read_json(out / "skills.json")["codes"]
    answers = {item["text"]: codes[item["owner"]] for item in inputs(out, source)}

    def judge(cli, workdir, choices, text, model):
        calls.append((text, model))
        return 0, answers[text], ""

    monkeypatch.setattr(routing, "ask_judge", judge)


@pytest.mark.parametrize("source", ["triggers", "examples"])
def test_targeted_build_selects_requested_inputs_but_keeps_all_choices(
    library, tmp_path, monkeypatch, source,
):
    out = tmp_path / "targeted"
    invoke(
        library, monkeypatch, out, "build",
        "--skill", ALPHA, "--skill", BETA,
        "--related", "gamma-three", "--related", "delta-four",
        source=source,
    )
    selected = {ALPHA, BETA, "gamma-three", "delta-four"}
    assert {item["owner"] for item in inputs(out, source)} == selected
    meta = read_json(out / "skills.json")
    assert set(meta["codes"]) == selected | {"epsilon-five"}
    choices = (out / "choice_list.txt").read_text(encoding="utf-8")
    assert all(f"{code}:" in choices for code in meta["codes"].values())
    scope = read_json(out / f"scope-{source}.json")
    assert scope["mode"] == "targeted"
    assert set(scope["selected_skills"]) == selected


@pytest.mark.parametrize(
    "selection",
    [(), ("--related", BETA), ("--full", "--skill", ALPHA), ("--skill", "missing-skill")],
)
def test_build_requires_an_explicit_valid_scope(library, tmp_path, monkeypatch, selection):
    with pytest.raises(SystemExit) as error:
        invoke(library, monkeypatch, tmp_path / "invalid", "build", *selection)
    assert error.value.code != 0


def test_adding_a_skill_does_not_renumber_or_reorder_existing_choices(library, tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    library.build(before, "triggers", skills=[ALPHA])
    old_codes = read_json(before / "skills.json")["codes"]
    old_lines = (before / "choice_list.txt").read_text(encoding="utf-8").splitlines()
    add_skill(library, "aardvark-new")
    library.build(after, "triggers", skills=[ALPHA])
    new_codes = read_json(after / "skills.json")["codes"]
    assert {name: new_codes[name] for name in old_codes} == old_codes
    old_code_set = set(old_codes.values())
    preserved = [
        line for line in (after / "choice_list.txt").read_text(encoding="utf-8").splitlines()
        if line.split(":", 1)[0] in old_code_set
    ]
    assert preserved == old_lines


@pytest.mark.parametrize("legacy", [False, True], ids=["full", "legacy"])
def test_full_or_legacy_run_requires_acknowledgement_before_any_calls(
    library, tmp_path, monkeypatch, legacy,
):
    out = tmp_path / "complete"
    invoke(library, monkeypatch, out, "build", "--full")
    if legacy:
        (out / "scope-triggers.json").unlink()
    calls = []
    install_successful_judge(library, monkeypatch, out, calls)
    with pytest.raises(SystemExit) as error:
        invoke(library, monkeypatch, out, "run", "--model", MODEL, "--workers", "1")
    assert error.value.code != 0
    assert calls == []
    assert not (out / "raw").exists()
    invoke(library, monkeypatch, out, "run", "--model", MODEL, "--workers", "1", "--full")
    assert len(calls) == len(inputs(out))


def test_targeted_cli_defaults_to_one_attempt_and_requires_explicit_model(
    library, tmp_path, monkeypatch,
):
    out = tmp_path / "one-attempt"
    invoke(library, monkeypatch, out, "build", "--skill", ALPHA, "--related", BETA)
    calls = []
    install_successful_judge(library, monkeypatch, out, calls)
    with pytest.raises(SystemExit) as error:
        invoke(library, monkeypatch, out, "run")
    assert error.value.code != 0
    assert calls == []
    invoke(library, monkeypatch, out, "run", "--model", MODEL, "--workers", "1")
    assert len(calls) == 2
    records = [json.loads(line) for line in (out / "raw" / "answers.jsonl").read_text().splitlines()]
    assert {record["run"] for record in records} == {1}
    invoke(library, monkeypatch, out, "report", "--model", MODEL)
    assert summary(out)["runs"] == 1
    assert summary(out)["total"] == [2, 2]
    assert summary(out)["partial"] is False


def test_failed_call_with_valid_code_is_not_a_vote_or_a_cached_success(
    library, tmp_path, monkeypatch,
):
    out = tmp_path / "retry"
    library.build(out, "triggers", skills=[ALPHA])
    own_code = read_json(out / "skills.json")["codes"][ALPHA]
    calls = []

    def judge(*args):
        calls.append(args)
        return (1, own_code, "Синтетическая ошибка") if len(calls) == 1 else (0, own_code, "")

    monkeypatch.setattr(library, "ask_judge", judge)
    library.run(out, "triggers", MODEL, workers=1)
    with pytest.raises(SystemExit):
        library.report(out, "triggers", MODEL)
    library.report(out, "triggers", MODEL, allow_partial=True)
    assert summary(out)["partial"] is True
    assert summary(out)["total"][0] == 0
    assert summary(out)["failed_calls"] == 1
    library.run(out, "triggers", MODEL, workers=1)
    assert len(calls) == 2
    library.report(out, "triggers", MODEL)
    assert summary(out)["partial"] is False
    assert summary(out)["total"] == [1, 1]
    library.run(out, "triggers", MODEL, workers=1)
    assert len(calls) == 2


def test_duplicate_attempts_cannot_manufacture_a_complete_majority(
    library, tmp_path, monkeypatch,
):
    out = tmp_path / "duplicates"
    library.build(out, "triggers", skills=[ALPHA])
    install_successful_judge(library, monkeypatch, out, [])
    library.run(out, "triggers", MODEL, workers=1)
    answers = out / "raw" / "answers.jsonl"
    record = answers.read_text(encoding="utf-8")
    answers.write_text(record * 3, encoding="utf-8")
    with pytest.raises(SystemExit):
        library.report(out, "triggers", MODEL, runs=3)
    library.report(out, "triggers", MODEL, runs=3, allow_partial=True)
    result = summary(out)
    assert result["partial"] is True
    assert result["total"][0] == 0
    assert len(result["rows"][0]["votes"]) == 1


def test_single_foreign_vote_is_reported_as_foreign_not_no_majority(
    library, tmp_path, monkeypatch,
):
    out = tmp_path / "foreign"
    library.build(out, "triggers", skills=[ALPHA])
    other_code = read_json(out / "skills.json")["codes"][BETA]
    monkeypatch.setattr(library, "ask_judge", lambda *args: (0, other_code, ""))
    library.run(out, "triggers", MODEL, workers=1)
    library.report(out, "triggers", MODEL)
    result = summary(out)
    assert result["partial"] is False
    assert result["total"] == [0, 1]
    assert result["pairs"] == [{"owner": ALPHA, "went": BETA, "count": 1}]
