#!/usr/bin/env python3
"""Проверяет локальные следы macOS-приложения без удаления файлов."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


HOME = Path.home()

SEARCH_ROOTS = [
    ("applications", Path("/Applications")),
    ("user-applications", HOME / "Applications"),
    ("application-support", HOME / "Library" / "Application Support"),
    ("containers", HOME / "Library" / "Containers"),
    ("group-containers", HOME / "Library" / "Group Containers"),
    ("caches", HOME / "Library" / "Caches"),
    ("preferences", HOME / "Library" / "Preferences"),
    ("webkit", HOME / "Library" / "WebKit"),
    ("httpstorages", HOME / "Library" / "HTTPStorages"),
    ("saved-state", HOME / "Library" / "Saved Application State"),
    ("cookies", HOME / "Library" / "Cookies"),
]

NEVER_DEFAULT_ROOTS = [
    HOME / "Downloads",
    HOME / "Documents",
    HOME / "Desktop",
]


@dataclass(frozen=True)
class Finding:
    path: Path
    category: str
    size_bytes: int
    confidence: str
    reason: str
    suggested_action: str


def normalize(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def readable_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{size} B"


def measure_size(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        output = subprocess.run(
            ["du", "-sk", str(path)],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.split()
        if output:
            return int(output[0]) * 1024
    except (OSError, ValueError):
        pass
    try:
        return path.stat().st_size
    except OSError:
        return 0


def direct_children(root: Path) -> list[Path]:
    try:
        return sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return []


def classify(path: Path, category: str, matched_hint: str) -> tuple[str, str, str]:
    path_text = str(path)
    if any(path_text.startswith(str(root)) for root in NEVER_DEFAULT_ROOTS):
        return (
            "low",
            f"путь находится в пользовательской папке; совпало с {matched_hint}",
            "never-delete",
        )
    if category in {"applications", "user-applications"}:
        return (
            "high",
            f"найден app bundle или приложение; совпало с {matched_hint}",
            "review",
        )
    if category in {"application-support", "caches", "preferences", "webkit", "httpstorages", "saved-state", "cookies"}:
        return (
            "high",
            f"типовой локальный след приложения; совпало с {matched_hint}",
            "safe-after-confirm",
        )
    if category in {"containers", "group-containers"}:
        return (
            "medium",
            f"контейнер приложения macOS; совпало с {matched_hint}",
            "review",
        )
    return (
        "low",
        f"совпало с {matched_hint}, но категория не является типовой для удаления",
        "review",
    )


def scan(app_name: str, hints: list[str]) -> list[Finding]:
    tokens = [token for token in [app_name, *hints] if token.strip()]
    normalized = [(token, normalize(token)) for token in tokens if normalize(token)]
    findings: dict[Path, Finding] = {}

    for category, root in SEARCH_ROOTS:
        for child in direct_children(root):
            child_key = normalize(child.name)
            match = next((raw for raw, key in normalized if key in child_key), None)
            if not match:
                continue
            confidence, reason, action = classify(child, category, match)
            findings[child] = Finding(
                path=child,
                category=category,
                size_bytes=measure_size(child),
                confidence=confidence,
                reason=reason,
                suggested_action=action,
            )

    return sorted(findings.values(), key=lambda item: (item.suggested_action, item.category, str(item.path).lower()))


def print_markdown(app_name: str, findings: list[Finding]) -> None:
    print(f"# Локальные следы: {app_name}")
    print()
    print("Сканирование только читает файловую систему и ничего не удаляет.")
    print()
    if not findings:
        print("Совпадений в типовых macOS-папках не найдено.")
        return

    total = sum(item.size_bytes for item in findings)
    print(f"Найдено объектов: {len(findings)}")
    print(f"Суммарный размер: {readable_size(total)}")
    print()
    print("| Действие | Уверенность | Размер | Категория | Путь | Причина |")
    print("| --- | --- | ---: | --- | --- | --- |")
    for item in findings:
        print(
            "| "
            f"{item.suggested_action} | "
            f"{item.confidence} | "
            f"{readable_size(item.size_bytes)} | "
            f"{item.category} | "
            f"`{item.path}` | "
            f"{item.reason} |"
        )


def print_json(findings: list[Finding]) -> None:
    print(
        json.dumps(
            [
                {
                    "path": str(item.path),
                    "category": item.category,
                    "size_bytes": item.size_bytes,
                    "confidence": item.confidence,
                    "reason": item.reason,
                    "suggested_action": item.suggested_action,
                }
                for item in findings
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Проверяет локальные следы macOS-приложения без удаления файлов.")
    parser.add_argument("app_name", help="Название приложения, например Telegram, Zoom или Slack.")
    parser.add_argument("--hint", action="append", default=[], help="Дополнительный bundle id или часть имени папки.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Формат отчёта.")
    args = parser.parse_args()

    findings = scan(args.app_name, args.hint)
    if args.format == "json":
        print_json(findings)
    else:
        print_markdown(args.app_name, findings)


if __name__ == "__main__":
    main()
