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

REFERENCE_DENY_PATTERNS = {
    "email address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone number": re.compile(r"(?:\+7|8)[\s()-]*\d{3}[\s()-]*\d{3}[\s()-]*\d{2}[\s()-]*\d{2}"),
    "raw exception log": re.compile(r"\bexception-log\.jsonl\b"),
    "private media file reference": re.compile(r"\b\S+\.(?:png|jpe?g|heic|mov|mp4|webp)\b", re.IGNORECASE),
    "marketplace numeric id": re.compile(r"\b(?:OLX|Avito|Kaspi)\s*(?:ID|id|айди)\s*[:#-]?\s*\d{4,}\b"),
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


def iter_reference_files() -> list[Path]:
    references: list[Path] = []
    skills_dir = ROOT / "plugins" / "team-skills" / "skills"
    for path in skills_dir.glob("*/references/**/*"):
        if path.is_file() and path.suffix.lower() in {".md", ".yaml", ".yml", ".json"}:
            references.append(path)
    return sorted(references)


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


def test_references_do_not_store_private_artifacts() -> None:
    for path in iter_reference_files():
        content = path.read_text(encoding="utf-8")
        for label, pattern in REFERENCE_DENY_PATTERNS.items():
            assert not pattern.search(content), f"{path} appears to contain {label}"
