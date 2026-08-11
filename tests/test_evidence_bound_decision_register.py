from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from conftest import ROOT, load_registry


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "evidence-bound-decision-register"
VALIDATOR_PATH = SKILL / "scripts" / "validate_decision_register.py"
MANAGER_PATH = SKILL / "scripts" / "manage_decision_register.py"
CANONICAL_GATE = """Перед любым вопросом проведи контрфактическую проверку:
Представь наиболее вероятные ответы пользователя.
Назови, какое решение, действие или часть результата изменит каждый ответ.
Если следующий шаг при всех ответах одинаков — вопрос запрещён.
Если пользователь уже зафиксировал выбор — запиши его, не открывай заново.
Если неизвестное техническое и его можно проверить самостоятельно — проверь, не спрашивай.
Задавай только ближайший вопрос, ответ на который реально меняет результат."""


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _modules():
    validator = _load(VALIDATOR_PATH, "decision_validator_test")
    if str(VALIDATOR_PATH.parent) not in sys.path:
        sys.path.insert(0, str(VALIDATOR_PATH.parent))
    manager = _load(MANAGER_PATH, "decision_manager_test")
    return validator, manager


def _write_bundle(tmp_path: Path, *, reviewed: bool = True):
    v, _ = _modules()
    tmp_path.mkdir(parents=True, exist_ok=True)
    questions = [
        v.QuestionRow(i, f"Синтетический вопрос {i}?", v.question_fingerprint(f"Синтетический вопрос {i}?"), i + 1)
        for i in range(1, 8)
    ]
    sources = [
        v.SourceRow("missing-one", "expected_file", "MISSING", "expected:first-export", "", "", 2),
        v.SourceRow("missing-two", "expected_measurement", "MISSING", "expected:second-measurement", "", "", 3),
        v.SourceRow("delegation-one", "delegation", "OBSERVED", "conversation:turn-1", v.sha256_text("delegated"), "2026-08-12T10:00:00+05:00", 4),
        v.SourceRow("user-answer", "user_turn", "OBSERVED", "conversation:turn-2", v.sha256_text("answer"), "2026-08-12T10:00:00+05:00", 5),
    ]
    final_review = "REVIEWED" if reviewed else "UNREVIEWED"
    answers = [
        v.AnswerRow(1, "UNKNOWN", "не знаю — ответ установит первый экспорт.", "[needed:missing-one]", "", "NOT_REQUIRED", 2),
        v.AnswerRow(2, "UNKNOWN", "не знаю — ответ установит второе измерение.", "[needed:missing-two]", "", "NOT_REQUIRED", 3),
        v.AnswerRow(3, "PENDING_CONTEXT", v.PENDING_PREFIX + " Нужен ответ 1.", "[decision:1]", "1", "NOT_REQUIRED", 4),
        v.AnswerRow(4, "PENDING_CONTEXT", v.PENDING_PREFIX + " Нужен ответ 3.", "[decision:3]", "3", "NOT_REQUIRED", 5),
        v.AnswerRow(5, "PENDING_CONTEXT", v.PENDING_PREFIX + " Нужны ответы 1 и 2.", "[decision:1;2]", "1;2", "NOT_REQUIRED", 6),
        v.AnswerRow(6, "DERIVED", "Используется делегированное техническое правило.", "[evidence:delegation-one]", "", final_review, 7),
        v.AnswerRow(7, "ANSWERED", "Утверждает назначенная роль.", "[evidence:user-answer]", "", final_review, 8),
    ]
    events: list[dict] = []
    previous = v.GENESIS_HASH
    for question, answer in zip(questions, answers):
        baseline_state = v.answer_state(answer)
        if answer.status in v.ACCEPTED_STATUSES:
            baseline_state["semantic_review"] = "UNREVIEWED"
        event = v.build_history_event(
            sequence=len(events) + 1,
            recorded_at="2026-08-12T10:00:00+05:00",
            actor="fixture-builder",
            action="BASELINE",
            question=question,
            state=baseline_state,
            previous_event_hash=previous,
        )
        events.append(event)
        previous = event["event_hash"]
    if reviewed:
        for question_id in (6, 7):
            event = v.build_history_event(
                sequence=len(events) + 1,
                recorded_at="2026-08-12T10:01:00+05:00",
                actor="reviewer-role",
                action="SEMANTIC_REVIEW",
                question=questions[question_id - 1],
                state=v.answer_state(answers[question_id - 1]),
                previous_event_hash=previous,
                review_basis="Проверен буквальный вопрос и всё основание.",
            )
            events.append(event)
            previous = event["event_hash"]

    q_path = tmp_path / "question-index.tsv"
    a_path = tmp_path / "answer-register.csv"
    s_path = tmp_path / "source-manifest.csv"
    h_path = tmp_path / "decision-history.jsonl"
    with q_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(v.QUESTION_HEADER)
        writer.writerows((row.question_id, row.question, row.question_fingerprint) for row in questions)
    with a_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(v.ANSWER_HEADER)
        writer.writerows(tuple(getattr(row, field) for field in v.ANSWER_HEADER) for row in answers)
    with s_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(v.SOURCE_HEADER)
        writer.writerows(tuple(getattr(row, field) for field in v.SOURCE_HEADER) for row in sources)
    h_path.write_text("".join(v.canonical_json(event) + "\n" for event in events), encoding="utf-8")
    return v, questions, answers, sources, events, (q_path, a_path, s_path, h_path)


def test_skill_contract_exposes_routing_history_and_safe_commands() -> None:
    registry = load_registry(SKILL)
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert registry["status"] == "experimental"
    assert registry["owner"] == "@kir-kopylov"
    assert CANONICAL_GATE in body
    for fragment in (
        "adaptive-interviewer",
        "razbor-chata-na-artefakty",
        "source-manifest.csv",
        "decision-history.jsonl",
        "manage_decision_register.py",
        "--require-reviewed",
        "Каждая закрытая строка получит",
    ):
        assert fragment in body
    assert "python3 <skill-dir>" not in body


def test_valid_bundle_ranks_roots_and_passes_review_gate(tmp_path: Path) -> None:
    v, _, _, _, _, paths = _write_bundle(tmp_path, reviewed=True)
    report = v.validate_files(*paths, require_reviewed=True)
    assert report.errors == ()
    assert [(item.question_id, item.impact) for item in report.unresolved_roots] == [(1, 3), (2, 1)]
    assert report.unreviewed_accepted_ids == ()


def test_missing_source_is_not_evidence_and_unknown_is_strict(tmp_path: Path) -> None:
    v, questions, answers, sources, events, _ = _write_bundle(tmp_path)
    bad_answered = v.AnswerRow(7, "ANSWERED", "Якобы известно.", "[evidence:missing-one]", "", "REVIEWED", 8)
    bad_unknown = v.AnswerRow(1, "UNKNOWN", "не знаю —", "[evidence:delegation-one]", "", "NOT_REQUIRED", 2)
    bad_answers = [bad_unknown if row.question_id == 1 else bad_answered if row.question_id == 7 else row for row in answers]
    errors = v.validate_rows(questions, bad_answers, sources, events).errors
    assert any("MISSING source 'missing-one' нельзя использовать как evidence" in error for error in errors)
    assert any("UNKNOWN должен назвать неизвестный факт" in error for error in errors)
    assert any("UNKNOWN требует хотя бы один MISSING needed source" in error for error in errors)


def test_unknown_or_malformed_reference_is_rejected(tmp_path: Path) -> None:
    v, questions, answers, sources, events, _ = _write_bundle(tmp_path)
    bad = v.AnswerRow(7, "ANSWERED", "Ответ.", "[evidence:user-answer] [fake:x] [evidence:]", "", "REVIEWED", 8)
    rows = [bad if row.question_id == 7 else row for row in answers]
    errors = v.validate_rows(questions, rows, sources, events).errors
    assert any("неизвестная или повреждённая ссылка [fake:x]" in error for error in errors)
    assert any("неизвестная или повреждённая ссылка [evidence:]" in error for error in errors)


def test_question_rewrite_and_history_tamper_fail(tmp_path: Path) -> None:
    v, _, _, _, events, paths = _write_bundle(tmp_path)
    rows = list(csv.reader(paths[0].open(encoding="utf-8"), delimiter="\t"))
    rows[1][1] = "Совершенно другой вопрос?"
    with paths[0].open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, delimiter="\t").writerows(rows)
    assert any("question_fingerprint не совпадает" in error for error in v.validate_files(*paths).errors)

    _, _, _, _, _, fresh_paths = _write_bundle(tmp_path / "fresh")
    history = [json.loads(line) for line in fresh_paths[3].read_text(encoding="utf-8").splitlines()]
    history[0]["state"]["answer"] = "tampered"
    fresh_paths[3].write_text("".join(v.canonical_json(item) + "\n" for item in history), encoding="utf-8")
    assert any("event_hash не совпадает" in error for error in v.validate_files(*fresh_paths).errors)


def test_long_chain_is_iterative_and_huge_range_is_safe() -> None:
    v, _ = _modules()
    count = 1200
    questions = [v.QuestionRow(i, str(i), v.question_fingerprint(str(i)), i + 1) for i in range(1, count + 1)]
    missing = v.SourceRow("root-source", "expected_file", "MISSING", "expected:root", "", "", 2)
    answers = [
        v.AnswerRow(i, "PENDING_CONTEXT", v.PENDING_PREFIX + " Нужен следующий ID.", f"[decision:{i + 1}]", str(i + 1), "NOT_REQUIRED", i + 1)
        for i in range(1, count)
    ] + [v.AnswerRow(count, "UNKNOWN", "не знаю — нужен корневой файл.", "[needed:root-source]", "", "NOT_REQUIRED", count + 1)]
    events = []
    previous = v.GENESIS_HASH
    for question, answer in zip(questions, answers):
        event = v.build_history_event(sequence=len(events) + 1, recorded_at="2026-08-12T10:00:00Z", actor="fixture", action="BASELINE", question=question, state=v.answer_state(answer), previous_event_hash=previous)
        events.append(event)
        previous = event["event_hash"]
    assert v.validate_rows(questions, answers, [missing], events).errors == ()
    errors: list[str] = []
    assert v.expand_id_expression("1-999999999999999999999", valid_ids={1, 2}, label="range", errors=errors) == [1, 2]
    assert errors == []


def test_unreviewed_is_visible_and_require_reviewed_fails(tmp_path: Path) -> None:
    v, _, _, _, _, paths = _write_bundle(tmp_path, reviewed=False)
    base = v.validate_files(*paths)
    strict = v.validate_files(*paths, require_reviewed=True)
    assert base.errors == ()
    assert base.unreviewed_accepted_ids == (6, 7)
    assert any("semantic review не зафиксирован" in error for error in strict.errors)


def test_migration_creates_canonical_unreviewed_baseline(tmp_path: Path) -> None:
    v, manager = _modules()
    legacy_questions = tmp_path / "legacy-questions.tsv"
    legacy_answers = tmp_path / "legacy-answers.csv"
    with legacy_questions.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(manager.LEGACY_QUESTION_HEADER)
        writer.writerows(((1, "Кто утверждает?"), (2, "Какой факт неизвестен?")))
    with legacy_answers.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(manager.LEGACY_ANSWER_HEADER)
        writer.writerows(((1, "ANSWERED", "Назначенная роль.", "Прямой ответ в старом реестре.", ""), (2, "UNKNOWN", "не знаю — нужен внешний файл.", "Файл не получен.", "")))
    out_dir = tmp_path / "migrated"
    report = manager.migrate_legacy(legacy_questions.resolve(), legacy_answers.resolve(), out_dir.resolve(), actor="migration-agent", recorded_at="2026-08-12T10:00:00Z")
    assert report.errors == ()
    paths = tuple(out_dir / name for name in ("question-index.tsv", "answer-register.csv", "source-manifest.csv", "decision-history.jsonl"))
    assert v.validate_files(*paths).errors == ()
    assert v.validate_files(*paths).unreviewed_accepted_ids == (1,)
    assert (out_dir / "migration-report.tsv").exists()


def test_update_resets_review_and_review_appends_hash_chain(tmp_path: Path) -> None:
    v, manager = _modules()
    _, _, _, _, _, paths = _write_bundle(tmp_path, reviewed=True)
    updated = manager.change_row(
        tuple(path.resolve() for path in paths),
        question_id=7,
        status="ANSWERED",
        answer="Утверждает другая назначенная роль.",
        evidence="[evidence:user-answer]",
        depends_on="",
        actor="decision-agent",
        recorded_at="2026-08-12T10:02:00+05:00",
    )
    assert updated.unreviewed_accepted_ids == (7,)
    reviewed = manager.review_row(
        tuple(path.resolve() for path in paths),
        question_id=7,
        reviewer="authorized-reviewer",
        basis="Сверен буквальный вопрос и полный источник.",
        recorded_at="2026-08-12T10:03:00+05:00",
    )
    assert reviewed.errors == ()
    assert v.validate_files(*paths, require_reviewed=True).errors == ()
    actions = [json.loads(line)["action"] for line in paths[3].read_text(encoding="utf-8").splitlines()]
    assert actions[-2:] == ["UPDATE", "SEMANTIC_REVIEW"]


def test_cli_requires_absolute_paths_and_reports_readiness(tmp_path: Path) -> None:
    _, _, _, _, _, paths = _write_bundle(tmp_path, reviewed=False)
    relative = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), "--questions", "question-index.tsv", "--answers", "answer-register.csv", "--sources", "source-manifest.csv", "--history", "decision-history.jsonl"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert relative.returncode == 2
    assert "должен быть абсолютным" in relative.stderr
    absolute = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), "--questions", str(paths[0].resolve()), "--answers", str(paths[1].resolve()), "--sources", str(paths[2].resolve()), "--history", str(paths[3].resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    assert absolute.returncode == 0, absolute.stderr
    assert "STRUCTURALLY_VALID_SEMANTICALLY_UNREVIEWED" in absolute.stdout


def test_bad_input_files_fail_deterministically_without_traceback_or_mutation(tmp_path: Path) -> None:
    bad_questions = tmp_path / "bad-question-index.tsv"
    bad_questions.write_bytes(b"\xff\xfe\x00")
    directory_answers = tmp_path / "answer-register.csv"
    directory_answers.mkdir()
    missing_sources = tmp_path / "missing-source-manifest.csv"
    empty_history = tmp_path / "decision-history.jsonl"
    empty_history.write_text("", encoding="utf-8")
    command = [
        sys.executable,
        str(VALIDATOR_PATH),
        "--questions",
        str(bad_questions.resolve()),
        "--answers",
        str(directory_answers.resolve()),
        "--sources",
        str(missing_sources.resolve()),
        "--history",
        str(empty_history.resolve()),
    ]
    before = bad_questions.read_bytes(), empty_history.read_bytes()
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    second = subprocess.run(command, capture_output=True, text=True, check=False)

    assert first.returncode == second.returncode == 1
    assert first.stdout == second.stdout == ""
    assert first.stderr == second.stderr
    assert "Traceback" not in first.stderr
    assert "не удалось прочитать" in first.stderr
    assert "файл не найден" in first.stderr
    assert (bad_questions.read_bytes(), empty_history.read_bytes()) == before
