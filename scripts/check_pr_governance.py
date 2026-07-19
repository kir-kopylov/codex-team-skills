#!/usr/bin/env python3
"""PR-level metadata gates that local pytest cannot see."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9+-]{2,}\b")

ALLOWED_LATIN_WORDS = {
    "api", "branch", "catalog", "check", "checks", "ci", "claude",
    "code", "codex", "gate", "gates", "git", "github", "http", "https", "json",
    "local", "logs", "main", "managed", "markdown", "marketplace",
    "macos", "mcp", "metadata", "md", "native", "only", "openai", "paths",
    "plugin", "policy", "pr", "pytest", "raw", "ready", "repo",
    "scripts", "semver", "skill", "skills", "smoke", "sync", "team",
    "team-ready", "todo", "ui", "url", "windows", "yaml", "yml",
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
        if word.lower() not in ALLOWED_LATIN_WORDS:
            offenders.append(word)
    return sorted(set(offenders), key=str.lower)


def find_private_material(value: str) -> list[str]:
    errors = []
    for label, pattern in {**DENY_PATTERNS, **RAW_LOG_PATTERNS}.items():
        if pattern.search(value):
            errors.append(label)
    return errors


def extract_when_not_to_use(body: str) -> str:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        marker = re.match(r"^\s*(?:[-*]\s*)?Когда\s+не\s+использовать\s*:\s*(.*)$", line, flags=re.I)
        if not marker:
            continue
        collected = [marker.group(1).strip()]
        for next_line in lines[index + 1 :]:
            stripped = next_line.strip()
            if not stripped:
                if any(collected):
                    break
                continue
            if re.match(r"^\s*(?:[-*]\s*)?(?:Какую\s+боль|Для\s+кого|Какие\s+примеры)[^:]*:", stripped, flags=re.I):
                break
            if re.match(r"^\s*#{1,6}\s+", next_line):
                break
            collected.append(stripped)
        return "\n".join(part for part in collected if part).strip()

    heading = re.search(r"(?ims)^#{1,6}\s*Когда\s+не\s+использовать\s*$\s*(?P<body>.*?)(?=^#{1,6}\s|\Z)", body)
    return heading.group("body").strip() if heading else ""


def check_russian_text(label: str, value: str) -> list[str]:
    if not value or not value.strip():
        return [f"{label}: поле не должно быть пустым"]
    errors = []
    if not CYRILLIC_RE.search(value):
        errors.append(f"{label}: нужен русский пользовательский текст")
    offenders = latin_offenders(value)
    if offenders:
        errors.append(f"{label}: найдены англоязычные слова вне allowlist: {', '.join(offenders[:12])}")
    for private_label in find_private_material(value):
        errors.append(f"{label}: найден запрещённый приватный/log marker: {private_label}")
    return errors


def check_pr_metadata(event: dict) -> list[str]:
    if "pull_request" not in event:
        return []
    pr = event["pull_request"]
    title = pr.get("title") or ""
    body = pr.get("body") or ""
    errors = [*check_russian_text("PR title", title), *check_russian_text("PR body", body)]
    when_not_to_use = extract_when_not_to_use(body)
    if len(when_not_to_use) < 12 or not CYRILLIC_RE.search(when_not_to_use):
        errors.append("PR body: явно заполните поле «Когда не использовать» русским текстом")
    return errors


def load_event(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("metadata",))
    parser.add_argument("--event-path", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", "")))
    args = parser.parse_args(argv)
    if not args.event_path:
        parser.error("GITHUB_EVENT_PATH is required")
    errors = check_pr_metadata(load_event(args.event_path))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("PR title/body governance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
