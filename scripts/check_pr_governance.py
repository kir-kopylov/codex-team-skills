#!/usr/bin/env python3
"""PR-level governance gates that local pytest cannot see."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9+-]{2,}\b")

ALLOWED_LATIN_WORDS = {
    "api",
    "branch",
    "bundle",
    "catalog",
    "check",
    "checks",
    "ci",
    "claude",
    "codex",
    "download",
    "downloads",
    "gate",
    "gates",
    "github",
    "http",
    "https",
    "installer",
    "json",
    "local",
    "logs",
    "main",
    "managed",
    "manifest",
    "markdown",
    "mcp",
    "metadata",
    "md",
    "only",
    "openai",
    "paths",
    "plugin",
    "policy",
    "powershell",
    "pr",
    "pytest",
    "raw",
    "ready",
    "release",
    "repo",
    "scripts",
    "skill",
    "skills",
    "smoke",
    "sync",
    "team",
    "team-ready",
    "todo",
    "ui",
    "url",
    "validateonly",
    "windows",
    "yaml",
    "yml",
}

DENY_PATTERNS = {
    "OpenAI/GitHub token": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[opsu]_[A-Za-z0-9_]{20,})\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "secret env assignment": re.compile(r"(?m)^(?:OPENAI_API_KEY|GITHUB_TOKEN|GH_TOKEN|SLACK_TOKEN|GOOGLE_API_KEY)="),
    "personal absolute path": re.compile(r"/Users/[^/\s]+/(?:Downloads|Library|Desktop|Documents)/(?:[^)\]\s]+)"),
    "home-anchored personal path": re.compile(r"~/(?:Downloads|Desktop|Documents)/[^\s`)\]]+"),
    "pasteboard item path": re.compile(r"group\.com\.apple\.coreservices\.useractivityd|shared-pasteboard"),
}

RAW_LOG_PATTERNS = {
    "traceback": re.compile(r"Traceback \(most recent call last\):"),
    "timestamped log lines": re.compile(r"(?m)^\s*(?:DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\s+\d{4}-\d{2}-\d{2}"),
    "raw exception log file": re.compile(r"\bexception-log\.jsonl\b"),
}

PROTECTED_PATH_PREFIXES = ("installer/",)
PROTECTED_PATHS = {
    ".github/workflows/tests.yml",
    "scripts/build_release_bundle.py",
    "scripts/pull-skills.sh",
}


def strip_markdown_noise(value: str) -> str:
    value = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    value = re.sub(r"`[^`]+`", " ", value)
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", value)
    value = re.sub(r"[@#][A-Za-z0-9_-]+", " ", value)
    value = re.sub(r"\b[\w./-]+\.(?:md|yaml|yml|json|py|sh|ps1|cmd|command)\b", " ", value, flags=re.I)
    return value


def latin_offenders(value: str) -> list[str]:
    cleaned = strip_markdown_noise(value)
    offenders = []
    for word in LATIN_WORD_RE.findall(cleaned):
        normalized = word.lower()
        if normalized not in ALLOWED_LATIN_WORDS:
            offenders.append(word)
    return sorted(set(offenders), key=str.lower)


def find_private_material(value: str) -> list[str]:
    errors = []
    for label, pattern in DENY_PATTERNS.items():
        if pattern.search(value):
            errors.append(label)
    for label, pattern in RAW_LOG_PATTERNS.items():
        if pattern.search(value):
            errors.append(label)
    return errors


def extract_when_not_to_use(body: str) -> str:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        marker = re.match(r"^\s*(?:[-*]\s*)?Когда\s+не\s+использовать\s*:\s*(.*)$", line, flags=re.I)
        if marker:
            collected = [marker.group(1).strip()]
            for next_line in lines[index + 1 :]:
                stripped = next_line.strip()
                if not stripped:
                    if any(collected):
                        break
                    continue
                if re.match(r"^\s*(?:[-*]\s*)?(?:Какую\s+боль|Для\s+кого|Какие\s+примеры)[^:]*:", stripped, flags=re.I):
                    break
                if re.match(r"^\s*(?:[-*]\s*)?[А-ЯЁ][^:]{1,80}:\s*$", next_line):
                    break
                if re.match(r"^\s*#{1,6}\s+", next_line):
                    break
                collected.append(stripped)
            return "\n".join(part for part in collected if part).strip()

    heading = re.search(r"(?ims)^#{1,6}\s*Когда\s+не\s+использовать\s*$\s*(?P<body>.*?)(?=^#{1,6}\s|\Z)", body)
    if heading:
        return heading.group("body").strip()
    return ""


def check_russian_text(label: str, value: str) -> list[str]:
    errors = []
    if not value or not value.strip():
        return [f"{label}: поле не должно быть пустым"]
    if not CYRILLIC_RE.search(value):
        errors.append(f"{label}: нужен русский пользовательский текст")
    offenders = latin_offenders(value)
    if offenders:
        sample = ", ".join(offenders[:12])
        errors.append(f"{label}: найдены англоязычные слова вне allowlist: {sample}")
    for private_label in find_private_material(value):
        errors.append(f"{label}: найден запрещённый приватный/log marker: {private_label}")
    return errors


def check_pr_metadata(event: dict) -> list[str]:
    if "pull_request" not in event:
        return []

    pr = event["pull_request"]
    title = pr.get("title") or ""
    body = pr.get("body") or ""
    errors = []
    errors.extend(check_russian_text("PR title", title))
    errors.extend(check_russian_text("PR body", body))

    when_not_to_use = extract_when_not_to_use(body)
    if len(when_not_to_use) < 12 or not CYRILLIC_RE.search(when_not_to_use):
        errors.append("PR body: явно заполните поле «Когда не использовать» русским текстом")

    return errors


def normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def protected_changed_paths(paths: Iterable[str]) -> list[str]:
    changed = []
    for raw in paths:
        path = normalize_path(raw)
        if path in PROTECTED_PATHS or any(path.startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES):
            changed.append(path)
    return sorted(set(changed))


def git_changed_paths(revspec: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", revspec],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def changed_paths_from_git(event: dict) -> list[str]:
    if "pull_request" not in event:
        return []

    base_ref = os.environ.get("GITHUB_BASE_REF")
    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if base_ref and head_ref:
        for revspec in (f"origin/{base_ref}...origin/{head_ref}", f"{base_ref}...{head_ref}"):
            try:
                return git_changed_paths(revspec)
            except subprocess.CalledProcessError:
                continue

    pr = event["pull_request"]
    base_sha = pr["base"]["sha"]
    head_sha = pr["head"]["sha"]
    return git_changed_paths(f"{base_sha}...{head_sha}")


def extract_hard_check_section(body: str) -> str:
    heading = re.search(
        r"(?ims)^#{1,6}\s*Ж[её]сткая\s+проверка\s+installer/release\s*$\s*(?P<body>.*?)(?=^#{1,6}\s|\Z)",
        body,
    )
    if heading:
        return heading.group("body").strip()

    inline = re.search(
        r"(?ims)^Ж[её]сткая\s+проверка\s+installer/release\s*:\s*(?P<body>.*?)(?=^#{1,6}\s|\Z)",
        body,
    )
    if inline:
        return inline.group("body").strip()
    return ""


def check_installer_release_hard_section(body: str) -> list[str]:
    section = extract_hard_check_section(body)
    if not section:
        return ["нужен отдельный раздел «Жёсткая проверка installer/release» в PR body"]

    checked_items = re.findall(r"(?im)^\s*[-*]\s*\[[xXхХ]\]\s+\S", section)
    lower = section.lower()
    errors = []
    if len(checked_items) < 3:
        errors.append("раздел installer/release должен иметь минимум 3 отмеченных пункта проверки")
    if not any(marker in lower for marker in ("powershell 5.1", "validateonly", "windows powershell")):
        errors.append("раздел installer/release должен явно покрывать Windows PowerShell 5.1/ValidateOnly")
    if not any(marker in lower for marker in ("manifest.json", "latest.json", "подпис", "signature")):
        errors.append("раздел installer/release должен явно покрывать manifest/latest или подпись release metadata")
    if not any(marker in lower for marker in ("откат", "rollback", "переустанов", "повторная установка")):
        errors.append("раздел installer/release должен явно покрывать rollback/переустановку")
    return errors


def check_protected_paths(event: dict, changed_paths: list[str] | None = None) -> list[str]:
    if "pull_request" not in event:
        return []

    changed_paths = changed_paths if changed_paths is not None else changed_paths_from_git(event)
    protected = protected_changed_paths(changed_paths)
    if not protected:
        return []

    body = event["pull_request"].get("body") or ""
    errors = check_installer_release_hard_section(body)
    if errors:
        return [f"изменены защищённые installer/release пути: {', '.join(protected)}", *errors]
    return []


def release_checks_required(
    event: dict,
    *,
    event_name: str | None = None,
    ref: str | None = None,
    changed_paths: list[str] | None = None,
) -> bool:
    if event_name == "push" and ref == "refs/heads/main":
        return True
    if "pull_request" not in event:
        return False

    changed_paths = changed_paths if changed_paths is not None else changed_paths_from_git(event)
    return bool(protected_changed_paths(changed_paths))


def print_release_scope(required: bool) -> int:
    print(f"run_release_checks={'true' if required else 'false'}")
    return 0


def load_event(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def print_result(errors: list[str], success_message: str) -> int:
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(success_message)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("metadata", "protected-paths", "release-scope"))
    parser.add_argument("--event-path", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", "")))
    args = parser.parse_args(argv)

    if not args.event_path:
        raise SystemExit("GITHUB_EVENT_PATH is required")

    event = load_event(args.event_path)
    if args.mode == "metadata":
        return print_result(check_pr_metadata(event), "PR title/body governance passed")
    if args.mode == "protected-paths":
        return print_result(check_protected_paths(event), "Installer/release protected paths gate passed")
    return print_release_scope(
        release_checks_required(
            event,
            event_name=os.environ.get("GITHUB_EVENT_NAME"),
            ref=os.environ.get("GITHUB_REF"),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
