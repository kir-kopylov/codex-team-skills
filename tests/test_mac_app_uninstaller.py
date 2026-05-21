from __future__ import annotations

from pathlib import Path

from conftest import ROOT


SCRIPT = ROOT / "plugins" / "team-skills" / "skills" / "mac-app-uninstaller" / "scripts" / "scan_mac_app_footprint.py"


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
