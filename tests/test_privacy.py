from __future__ import annotations

import re
from pathlib import Path

from conftest import ROOT


SCAN_PATHS = [
    ROOT / "README.md",
    ROOT / "catalog.md",
    ROOT / "quickstart.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "START_HERE_CONNECT_CODEX_SKILLS.md",
    ROOT / "admin-onboarding-guide.md",
    ROOT / "docs",
    ROOT / "installer",
    ROOT / ".github",
    ROOT / "plugins",
]

DENY_PATTERNS = {
    "OpenAI or GitHub token": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[opsu]_[A-Za-z0-9_]{20,})\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "env assignment": re.compile(r"(?m)^(?:OPENAI_API_KEY|GITHUB_TOKEN|GH_TOKEN|SLACK_TOKEN|GOOGLE_API_KEY)="),
    "personal absolute path": re.compile(r"/Users/[^/\s]+/(?:Downloads|Library|Desktop|Documents)/(?:[^)\]\s]+)"),
    "pasteboard item path": re.compile(r"group\.com\.apple\.coreservices\.useractivityd|shared-pasteboard"),
}


def iter_scanned_files() -> list[Path]:
    files: list[Path] = []
    for path in SCAN_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                child
                for child in path.rglob("*")
                if child.is_file()
                and child.suffix.lower() in {".md", ".yaml", ".yml", ".json", ".ps1", ".cmd", ".command", ".sh"}
            )
    return sorted(files)


def test_no_obvious_private_material_or_secrets() -> None:
    for path in iter_scanned_files():
        content = path.read_text(encoding="utf-8")
        for label, pattern in DENY_PATTERNS.items():
            assert not pattern.search(content), f"{path} appears to contain {label}"


def test_no_raw_exception_logs_are_committed() -> None:
    ignored_dirs = {".git", ".pytest_cache", "__pycache__", "dist"}
    for path in ROOT.rglob("*"):
        if any(part in ignored_dirs for part in path.parts):
            continue
        if not path.is_file():
            continue
        assert path.name != "exception-log.jsonl", f"{path} выглядит как сырой приватный exception log"
        assert "skill-runs" not in path.parts, f"{path} выглядит как приватная директория skill-runs"
