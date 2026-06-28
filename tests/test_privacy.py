from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import ROOT, load_registry, skill_dirs


# What this privacy gate DOES catch (regex-only, in the scanned docs/installer/
# plugin trees, and — for the reference-only patterns — under */references/**):
#   - OpenAI/GitHub-style tokens (sk-..., gh[opsu]_...);
#   - PEM "BEGIN ... PRIVATE KEY" blocks;
#   - secret env assignments (OPENAI_API_KEY=, GITHUB_TOKEN=, GH_TOKEN=,
#     SLACK_TOKEN=, GOOGLE_API_KEY= at start of line);
#   - personal macOS absolute paths under
#     /Users/<name>/(Downloads|Library|Desktop|Documents)/...;
#   - pasteboard / user-activity item paths;
#   - and, ONLY under reference dirs: email addresses, +7/8 phone numbers,
#     raw exception-log.jsonl mentions, private media file references
#     (.png/.jpg/.heic/.mov/.mp4/.webp), and OLX/Avito/Kaspi numeric ids.
#
# What this gate does NOT catch (a green run here is NOT a privacy clearance —
# human review is still required before publishing):
#   - real personal NAMES in arbitrary prose (there is no general NER here;
#     author names are allowed in `authors` when they are intentional public
#     attribution and do not include contact details or raw private context);
#   - any private context that does not match one of the literal patterns above.
#
# Narrowed since the original gate (see tests below):
#   - ~/ home-anchored personal CONTENT paths (~/Downloads|Desktop|Documents/<file>)
#     are now caught in addition to absolute /Users/<name>/...; the bare folder
#     mentions (`~/Downloads` without a trailing path) stay allowed because skills
#     legitimately tell the model not to touch them;
#   - skill.yaml `authors` is a public attribution surface: personal names are
#     allowed, but contact identifiers and private paths are not;
#   - an OPTIONAL, gitignored tests/private-denylist.txt lets a maintainer scan the
#     repo for known-private literal strings (client/person names) without ever
#     committing those strings.


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
    # ~/Downloads/<file> — реальный путь к личному файлу; голое `~/Downloads`
    # (без хвоста) разрешено: скилы законно просят его не трогать.
    "home-anchored personal path": re.compile(r"~/(?:Downloads|Desktop|Documents)/[^\s`)\]]+"),
    "pasteboard item path": re.compile(r"group\.com\.apple\.coreservices\.useractivityd|shared-pasteboard"),
}

CURATED_DENYLIST_FILE = ROOT / "tests" / "private-denylist.txt"
REPO_TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".txt", ".sh", ".ps1", ".cmd", ".command", ".py", ".pem"}
IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", "dist", "build", ".venv"}

REFERENCE_DENY_PATTERNS = {
    "email address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone number": re.compile(r"(?:\+7|8)[\s()-]*\d{3}[\s()-]*\d{3}[\s()-]*\d{2}[\s()-]*\d{2}"),
    "raw exception log": re.compile(r"\bexception-log\.jsonl\b"),
    "private media file reference": re.compile(r"\b\S+\.(?:png|jpe?g|heic|mov|mp4|webp)\b", re.IGNORECASE),
    "marketplace numeric id": re.compile(r"\b(?:OLX|Avito|Kaspi)\s*(?:ID|id|айди)\s*[:#-]?\s*\d{4,}\b"),
}

# `authors` is intentionally public attribution. It may contain a human name,
# but it must not become a place for contact details, handles or private paths.
AUTHOR_PRIVATE_PATTERNS = {
    "email address": REFERENCE_DENY_PATTERNS["email address"],
    "phone number": REFERENCE_DENY_PATTERNS["phone number"],
    "personal absolute path": DENY_PATTERNS["personal absolute path"],
    "home-anchored personal path": DENY_PATTERNS["home-anchored personal path"],
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


def test_authors_are_public_attribution_without_private_contact_details() -> None:
    # `authors` хранит публичное авторство. Имя автора допустимо, но contacts,
    # handles, личные пути и raw-контекст должны оставаться вне repo.
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        authors = registry.get("authors")
        if not authors:
            continue
        assert isinstance(authors, list)
        for author in authors:
            assert isinstance(author, str) and author.strip()
            # @-handles запрещены отдельно (test_registry); здесь проверяем
            # контактные и приватные идентификаторы.
            assert not author.startswith("@"), f"{skill_dir.name}: authors не должны быть @-handle"
            for label, pattern in AUTHOR_PRIVATE_PATTERNS.items():
                assert not pattern.search(author), f"{skill_dir.name}: authors=«{author}» содержит {label}"


# --- курируемый денилист (опциональный, не коммитится) ---------------------

def _load_curated_denylist() -> list[str]:
    if not CURATED_DENYLIST_FILE.exists():
        return []
    terms: list[str] = []
    for line in CURATED_DENYLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


def _find_denylisted(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def iter_repo_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path == CURATED_DENYLIST_FILE:  # сам денилист не сканируем — самосовпадение
            continue
        if path.is_file() and path.suffix.lower() in REPO_TEXT_SUFFIXES:
            files.append(path)
    return sorted(files)


def test_curated_denylist_mechanism_detects_planted_term() -> None:
    # Механизм работает независимо от наличия реального приватного файла.
    terms = ["Секрет-Клиент-Альфа", "Иванов"]
    assert _find_denylisted("договор для Секрет-клиент-альфа подписан", terms) == ["Секрет-Клиент-Альфа"]
    assert _find_denylisted("совершенно безопасный текст", terms) == []


def test_curated_denylist_terms_absent_from_repo() -> None:
    terms = _load_curated_denylist()
    if not terms:
        pytest.skip("нет локального tests/private-denylist.txt — приватные термины не заданы")
    offenders: dict[str, list[str]] = {}
    for path in iter_repo_text_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits = _find_denylisted(content, terms)
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits
    assert not offenders, f"в репозитории найдены приватные термины из денилиста: {offenders}"
