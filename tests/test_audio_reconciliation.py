import json
import subprocess
import sys

import pytest

from conftest import ROOT


CHECKER = (
    ROOT / "plugins/team-skills/skills/razbor-video-po-taymkodam"
    / "scripts/check_audio_reconciliation.py"
)
TRANSCRIPT = """[00:00:00] Спикер 1: Файл не найден.
[00:00:05] Спикер 2: А где копия файла?
[00:00:08] Спикер 1: Копия должна быть в архиве.

Примечания редактора
Отрицание и тихий вопрос восстановлены по аудио.
"""


@pytest.fixture
def ledger():
    return {
        "duration_ms": 12643,
        "intervals": [
            {"start_ms": 0, "end_ms": 7000, "state": "checked", "basis": "Распознано по звуку."},
            {"start_ms": 7000, "end_ms": 8139, "state": "unclear", "basis": "Звук проверен, слова неразборчивы."},
            {"start_ms": 8139, "end_ms": 12643, "state": "checked", "basis": "Распознано по звуку."},
        ],
        "draft_ids": ["1", "2"],
        "decisions": [{"id": "1", "lines": [1]}, {"id": "2", "lines": [3]}],
    }


def check(tmp_path, ledger, transcript=TRANSCRIPT):
    ledger_path = tmp_path / "ledger.json"
    transcript_path = tmp_path / "transcript.txt"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
    transcript_path.write_text(transcript, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(CHECKER), "--ledger", str(ledger_path), "--transcript", str(transcript_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_checked_but_unclear_interval_and_added_utterance_allow_complete_review(tmp_path, ledger):
    result = check(tmp_path, ledger)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "complete"
    assert report["draft_fragments"] == 2
    assert report["utterances"] == 3
    assert report["unverified_intervals_ms"] == []


def test_unread_tail_remains_partial_even_with_all_draft_ids_accounted_for(tmp_path, ledger):
    ledger["intervals"][-1] = {
        "start_ms": 8139,
        "end_ms": 9000,
        "state": "unverified",
        "basis": "Конец файла недоступен.",
    }
    ledger["decisions"][1] = {"id": "2", "unverified": "Конец файла недоступен."}
    transcript = TRANSCRIPT.replace("[00:00:08] Спикер 1: Копия должна быть в архиве.\n", "")
    result = check(tmp_path, ledger, transcript)
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "partial"
    assert report["unverified_intervals_ms"] == [[8139, 12643]]
    assert report["unverified_fragment_ids"] == ["2"]


def test_omitted_internal_interval_cannot_be_hidden_by_matching_all_draft_lines(tmp_path, ledger):
    del ledger["intervals"][1]
    result = check(tmp_path, ledger)
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["unverified_intervals_ms"] == [[7000, 8139]]


def test_missing_or_invalid_draft_mapping_does_not_pass(tmp_path, ledger):
    missing = ledger["decisions"].pop()
    result = check(tmp_path, ledger)
    assert result.returncode == 2
    assert "Не учтены фрагменты" in result.stderr

    missing["lines"] = [4]
    ledger["decisions"].append(missing)
    result = check(tmp_path, ledger)
    assert result.returncode == 2
    assert "Некорректные номера реплик" in result.stderr


def test_overlapping_ledger_intervals_are_rejected(tmp_path, ledger):
    ledger["intervals"][1]["start_ms"] -= 1
    result = check(tmp_path, ledger)
    assert result.returncode == 2
    assert "перекрываются" in result.stderr


@pytest.mark.parametrize(
    "transcript",
    [
        TRANSCRIPT.replace("[00:00:05]", "[00:00:59]"),
        TRANSCRIPT.replace("[00:00:08]", "[00:00:04]"),
        TRANSCRIPT.replace("Примечания редактора\n", ""),
    ],
)
def test_malformed_transcript_cannot_pass(tmp_path, ledger, transcript):
    result = check(tmp_path, ledger, transcript)
    assert result.returncode == 2
    assert result.stderr.startswith("Проверка не пройдена.")
