from __future__ import annotations

import importlib.util
import sys

import pytest

from conftest import ROOT


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "razbor-chata-na-artefakty"
SCRIPT = SKILL_DIR / "scripts" / "check_registry.py"

VALID_HEAD = [
    "# Реестр утверждений",
    "Чат: тема разбора | Дата: 2026-07-25 | Собрал: модель",
    "",
    "Статусы: + принято | x отвергнуто | ? открыто | 0 без реакции",
    "Статус меняется заменой первого символа строки. Формулировки не переписывать.",
    "",
]


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("check_registry", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(tmp_path, lines):
    path = tmp_path / "registry.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(mod, monkeypatch, path):
    monkeypatch.setattr(sys, "argv", ["check_registry.py", str(path)])
    return mod.main()


def test_selftest_detector_alive(mod) -> None:
    assert mod.selftest() == []


def test_marker_in_text_is_violation_and_still_counted(mod) -> None:
    line = "? 010 | !сомнение внутри текста | якорь: «слова из чата»"
    why = mod.validate_line(line)
    assert why is not None and "маркер" in why

    # маркер не должен теряться из-за нарушения формата: чинят форму — статус остаётся незакрытым
    r = mod.analyze([line])
    assert len(r["problems"]) == 1
    assert r["doubts"], "маркер из текста утверждения потерян в подсчёте"


@pytest.mark.parametrize(
    "line",
    [
        "? 012 | текст | якорь: !сомнение «цитата»",
        "0 013 | текст | якорь: «цитата !контекст-сжат»",
        "x 014 | текст альт:001 | якорь: «цитата»",
    ],
)
def test_marker_outside_tail_is_violation(mod, line) -> None:
    # маркер внутри якоря с хвоста не снимается и при чтении теряется,
    # а строка выглядит валидной и открывает шлюз
    why = mod.validate_line(line)
    assert why is not None and "не в конце строки" in why


def test_marker_hidden_in_anchor_is_still_counted(mod) -> None:
    r = mod.analyze(VALID_HEAD + ["? 012 | текст | якорь: !сомнение «цитата»"])
    assert len(r["problems"]) == 1
    assert r["doubts"], "маркер из якоря потерян в подсчёте незакрытых"


def test_empty_registry_closes_gate(mod, tmp_path, monkeypatch, capsys) -> None:
    path = _write(tmp_path, VALID_HEAD)
    assert _run(mod, monkeypatch, path) == 1
    out = capsys.readouterr().out
    assert "ШЛЮЗ ЗАКРЫТ" in out
    assert "ни одной строки-утверждения" in out


def test_decreasing_number_is_violation(mod) -> None:
    r = mod.analyze(
        VALID_HEAD
        + [
            "+ 001 | первое | якорь: «а»",
            "+ 003 | третье | якорь: «б»",
            "+ 002 | второе | якорь: «в»",
        ]
    )
    assert any("меньше предыдущего" in why for _, why, _ in r["problems"])


def test_number_gap_is_allowed(mod) -> None:
    # человек по инструкции переносит строку без якоря в раздел «Без якоря»,
    # поэтому дыра в нумерации — штатный след вычитки, а не дефект
    r = mod.analyze(
        VALID_HEAD
        + [
            "+ 001 | первое | якорь: «а»",
            "+ 004 | четвёртое | якорь: «б»",
            "+ 901 | дописано человеком | якорь: «в»",
        ]
    )
    assert r["problems"] == []


def test_dash_line_is_not_swallowed_by_header_filter(mod) -> None:
    r = mod.analyze(VALID_HEAD + ["- 905 | дописано руками | якорь: «слова из чата»"])
    assert len(r["problems"]) == 1
    assert "дефис" in r["problems"][0][1]


def test_trailing_markers_stripped_in_any_order(mod) -> None:
    direct = mod.strip_markers("x 005 | текст | якорь: «слова» альт:001 !сомнение")
    reverse = mod.strip_markers("x 005 | текст | якорь: «слова» !сомнение альт:001")
    assert direct == reverse
    base, doubt, compacted, alt = direct
    assert base == "x 005 | текст | якорь: «слова»"
    assert (doubt, compacted, alt) == (True, False, "001")


def test_alt_on_non_x_status_is_violation(mod) -> None:
    r = mod.analyze(
        VALID_HEAD
        + [
            "+ 001 | принятое решение | якорь: «слова из чата»",
            "+ 002 | не альтернатива | якорь: «слова из чата» альт:001",
        ]
    )
    assert any("только на строке x" in why for _, why, _ in r["problems"])


def test_alt_to_missing_number_is_violation(mod) -> None:
    r = mod.analyze(
        VALID_HEAD
        + [
            "+ 001 | принятое решение | якорь: «слова из чата»",
            "x 002 | отвергнутый вариант | якорь: «слова из чата» альт:777",
        ]
    )
    assert any("которого нет в реестре" in why for _, why, _ in r["problems"])


def test_alt_to_non_accepted_status_is_warning_not_violation(mod) -> None:
    r = mod.analyze(
        VALID_HEAD
        + [
            "? 001 | нерешённый вопрос | якорь: «слова из чата»",
            "x 002 | отвергнутый вариант | якорь: «слова из чата» альт:001",
        ]
    )
    assert r["problems"] == []
    assert any("альт:001" in w for w in r["warnings"])


def test_duplicate_number_is_violation(mod) -> None:
    r = mod.analyze(
        VALID_HEAD
        + [
            "+ 001 | первое утверждение | якорь: «слова из чата»",
            "? 001 | второе утверждение | якорь: «другие слова»",
        ]
    )
    assert any("уже был в строке" in why for _, why, _ in r["problems"])


def test_extra_pipe_reports_pipe_reason(mod) -> None:
    why = mod.validate_line("+ 011 | текст с | чертой | якорь: «слова из чата»")
    assert why is not None and "вертикальная черта" in why


def test_section_without_anchor_is_not_parsed(mod) -> None:
    r = mod.analyze(
        VALID_HEAD
        + [
            "+ 001 | принятое решение | якорь: «слова из чата»",
            "",
            "## Без якоря — не вошло в реестр",
            "- утверждение без привязки — не нашлась цитата",
            "- ещё одно — участок чата сжат",
        ]
    )
    assert r["problems"] == []
    assert r["total"] == 1


def test_unclosed_compacted_marker_counted(mod) -> None:
    r = mod.analyze(VALID_HEAD + ["0 004 | предложение агента | якорь: «слова» !контекст-сжат"])
    assert r["compacted"] == ["004"]
    assert r["problems"] == []


def test_main_returns_3_on_clean_file_with_unclosed_marker(mod, tmp_path, monkeypatch, capsys) -> None:
    path = _write(
        tmp_path,
        VALID_HEAD
        + [
            "+ 001 | принятое решение | якорь: «слова из чата»",
            "? 002 | нерешённый вопрос | якорь: «слова из чата» !сомнение",
            "0 003 | предложение агента | якорь: «слова из чата»",
        ],
    )
    assert _run(mod, monkeypatch, path) == 3
    out = capsys.readouterr().out
    assert "sha256:" in out
    assert "нарушений формата: 0" in out


def test_main_returns_0_on_clean_file_without_markers(mod, tmp_path, monkeypatch, capsys) -> None:
    path = _write(
        tmp_path,
        VALID_HEAD
        + [
            "+ 001 | принятое решение | якорь: «слова из чата»",
            "x 002 | отвергнутый вариант | якорь: «слова из чата» альт:001",
            "0 003 | предложение агента | якорь: «слова из чата»",
        ],
    )
    assert _run(mod, monkeypatch, path) == 0
    out = capsys.readouterr().out
    assert "sha256:" in out
    assert "ШЛЮЗ ОТКРЫТ" in out


def test_main_returns_1_on_format_violation(mod, tmp_path, monkeypatch, capsys) -> None:
    path = _write(
        tmp_path,
        VALID_HEAD
        + [
            "+ 001 | принятое решение | якорь: «слова из чата»",
            "- 901 | дописано руками | якорь: «слова из чата»",
        ],
    )
    assert _run(mod, monkeypatch, path) == 1
    assert "нарушений формата: 1" in capsys.readouterr().out


def test_manual_lines_from_900_are_reported(mod) -> None:
    r = mod.analyze(
        VALID_HEAD
        + [
            "+ 001 | принятое решение | якорь: «слова из чата»",
            "+ 901 | дописано человеком | якорь: «слова из чата»",
        ]
    )
    assert r["manual"] == ["901"]
    assert r["problems"] == []


def test_main_returns_2_on_missing_file(mod, tmp_path, monkeypatch, capsys) -> None:
    assert _run(mod, monkeypatch, tmp_path / "нет-такого.md") == 2
    assert "файл не прочитан" in capsys.readouterr().out


def test_skill_md_calls_script_by_skill_dir_path() -> None:
    body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "<skill-dir>/scripts/check_registry.py" in body
    # рабочий каталог — проект человека, относительный вызов не найдёт скрипт
    assert "python3 scripts/check_registry.py" not in body
