from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from conftest import ROOT


SCRIPT = ROOT / "plugins" / "team-skills" / "skills" / "mac-app-uninstaller" / "scripts" / "scan_mac_app_footprint.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("scan_mac_app_footprint", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # нужен dataclass-декоратору для резолва аннотаций
    spec.loader.exec_module(mod)
    return mod


MOD = _load_module()


def test_mac_app_uninstaller_scanner_is_scan_only() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    forbidden = [
        "rm -",
        ".unlink(",
        ".rmdir(",
        "rmtree",
        "send2trash",
        "trash-put",
        "osascript delete",
        "Finder\" to delete",
    ]
    for marker in forbidden:
        assert marker not in content


def test_mac_app_uninstaller_scanner_declares_expected_roots() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "Application Support",
        "Containers",
        "Group Containers",
        "Caches",
        "Preferences",
        "WebKit",
        "HTTPStorages",
        "Saved Application State",
        "Cookies",
    ):
        assert marker in content


# --- инвариант области сканирования ----------------------------------------

def test_search_roots_never_include_personal_folders() -> None:
    # Сканер обязан смотреть только в типовые системные/Library-папки и никогда
    # в Downloads/Documents/Desktop — это и есть гарантия безопасности.
    sensitive = {str(root) for root in MOD.NEVER_DEFAULT_ROOTS}
    for _category, root in MOD.SEARCH_ROOTS:
        assert str(root) not in sensitive, f"{root} — личная папка, её нет места в SEARCH_ROOTS"
        assert not any(str(root).startswith(s + "/") for s in sensitive)


# --- чистые функции ---------------------------------------------------------

def test_normalize_strips_non_alnum_and_lowercases() -> None:
    assert MOD.normalize("Telegram Desktop!") == "telegramdesktop"
    assert MOD.normalize("org.telegram.desktop") == "orgtelegramdesktop"
    assert MOD.normalize("   ") == ""


def test_readable_size_formats_units() -> None:
    assert MOD.readable_size(0) == "0 B"
    assert MOD.readable_size(512) == "512 B"
    assert MOD.readable_size(1536) == "1.5 KB"
    assert MOD.readable_size(5 * 1024 * 1024) == "5.0 MB"


def test_classify_assigns_action_per_category() -> None:
    assert MOD.classify(Path("/Applications/X.app"), "applications", "X")[2] == "review"
    assert MOD.classify(Path("/x"), "caches", "X")[2] == "safe-after-confirm"
    assert MOD.classify(Path("/x"), "containers", "X") == ("medium", MOD.classify(Path("/x"), "containers", "X")[1], "review")
    assert MOD.classify(Path("/x"), "unknown-category", "X")[0] == "low"


def test_classify_protects_personal_folders(monkeypatch, tmp_path) -> None:
    downloads = tmp_path / "Downloads"
    monkeypatch.setattr(MOD, "NEVER_DEFAULT_ROOTS", [downloads])
    confidence, _reason, action = MOD.classify(downloads / "Telegram", "caches", "Telegram")
    assert confidence == "low"
    assert action == "never-delete"


# --- поведение scan() на синтетической ФС ----------------------------------

def _fake_home(tmp_path) -> Path:
    home = tmp_path / "home"
    (home / "Applications" / "Telegram.app").mkdir(parents=True)
    (home / "Library" / "Application Support" / "Telegram").mkdir(parents=True)
    (home / "Library" / "Caches" / "org.telegram.desktop").mkdir(parents=True)
    (home / "Library" / "Containers" / "ru.keepcoder.Telegram").mkdir(parents=True)
    (home / "Library" / "Preferences").mkdir(parents=True)
    (home / "Library" / "Preferences" / "com.zoom.xos.plist").write_text("x")
    # личная папка с совпадающим именем — НЕ корень поиска, не должна попасть в отчёт
    (home / "Downloads" / "Telegram").mkdir(parents=True)
    return home


def _patch_roots(monkeypatch, home: Path) -> None:
    monkeypatch.setattr(MOD, "SEARCH_ROOTS", [
        ("applications", home / "Applications"),
        ("application-support", home / "Library" / "Application Support"),
        ("caches", home / "Library" / "Caches"),
        ("containers", home / "Library" / "Containers"),
        ("preferences", home / "Library" / "Preferences"),
    ])


def test_scan_matches_app_footprint_across_roots(monkeypatch, tmp_path) -> None:
    home = _fake_home(tmp_path)
    _patch_roots(monkeypatch, home)

    findings = MOD.scan("Telegram", [])
    by_path = {str(f.path): f for f in findings}

    assert str(home / "Applications" / "Telegram.app") in by_path
    assert str(home / "Library" / "Application Support" / "Telegram") in by_path
    assert str(home / "Library" / "Caches" / "org.telegram.desktop") in by_path
    assert str(home / "Library" / "Containers" / "ru.keepcoder.Telegram") in by_path

    assert by_path[str(home / "Library" / "Containers" / "ru.keepcoder.Telegram")].suggested_action == "review"
    assert by_path[str(home / "Library" / "Caches" / "org.telegram.desktop")].suggested_action == "safe-after-confirm"
    assert all(isinstance(f.size_bytes, int) and f.size_bytes >= 0 for f in findings)


def test_scan_ignores_non_matching_and_personal_folders(monkeypatch, tmp_path) -> None:
    home = _fake_home(tmp_path)
    _patch_roots(monkeypatch, home)

    paths = {str(f.path) for f in MOD.scan("Telegram", [])}
    # не наш плейлист (zoom) — нет совпадения
    assert str(home / "Library" / "Preferences" / "com.zoom.xos.plist") not in paths
    # Downloads никогда не сканируется (его нет в SEARCH_ROOTS)
    assert str(home / "Downloads" / "Telegram") not in paths


def test_scan_returns_empty_on_missing_roots_without_crashing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(MOD, "SEARCH_ROOTS", [
        ("caches", tmp_path / "does-not-exist" / "Caches"),
    ])
    assert MOD.scan("Telegram", []) == []


def test_scan_with_blank_query_returns_empty(monkeypatch, tmp_path) -> None:
    home = _fake_home(tmp_path)
    _patch_roots(monkeypatch, home)
    assert MOD.scan("", []) == []
    assert MOD.scan("   ", ["  "]) == []


# --- форматы вывода ---------------------------------------------------------

def test_print_markdown_includes_no_delete_disclaimer(monkeypatch, tmp_path, capsys) -> None:
    home = _fake_home(tmp_path)
    _patch_roots(monkeypatch, home)
    MOD.print_markdown("Telegram", MOD.scan("Telegram", []))
    out = capsys.readouterr().out
    assert "ничего не удаляет" in out
    assert "| Действие | Уверенность |" in out


def test_print_markdown_reports_no_matches(capsys) -> None:
    MOD.print_markdown("Nothing", [])
    out = capsys.readouterr().out
    assert "не найдено" in out


def test_print_json_emits_parseable_records(monkeypatch, tmp_path, capsys) -> None:
    home = _fake_home(tmp_path)
    _patch_roots(monkeypatch, home)
    MOD.print_json(MOD.scan("Telegram", []))
    records = json.loads(capsys.readouterr().out)
    assert records and all(
        {"path", "category", "size_bytes", "confidence", "reason", "suggested_action"} <= set(r)
        for r in records
    )
