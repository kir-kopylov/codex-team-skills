#!/usr/bin/env python3
"""Создаёт черновик командного skill с registry-метаданными и примерами."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "plugins" / "team-skills" / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_name(raw: str) -> str:
    name = raw.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    if not name or not NAME_RE.match(name):
        raise SystemExit(f"Некорректное имя skill после нормализации: {name!r}")
    return name


def write_new(path: Path, content: str) -> None:
    if path.exists():
        raise SystemExit(f"Не перезаписываю существующий файл: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Имя skill; будет нормализовано в kebab-case")
    parser.add_argument("--owner", default="@owner", help="GitHub handle владельца skill")
    parser.add_argument("--summary", default="TODO: короткое практическое описание")
    args = parser.parse_args()

    skill_name = normalize_name(args.name)
    skill_dir = SKILLS_DIR / skill_name
    if skill_dir.exists():
        raise SystemExit(f"Skill уже существует: {skill_dir}")

    title = " ".join(part.capitalize() for part in skill_name.split("-"))
    today = date.today().isoformat()

    write_new(
        skill_dir / "SKILL.md",
        f"""---
name: {skill_name}
description: TODO: Объясните, когда использовать этот skill, включая естественные фразы-триггеры, чтобы пользователи не запоминали внутреннее имя skill.
---

# {title}

## Обзор

TODO: Объясните повторяющуюся задачу, которую закрывает skill, и ожидаемое поведение для пользователя.

## Естественные Входы

TODO: Перечислите обычные фразы, по которым skill должен срабатывать.

## Процесс

TODO: Опишите минимальный процесс принятия решений и использования tools.

## Границы

TODO: Укажите, когда skill нельзя использовать, что нужно сохранить и чего нужно избегать.
""",
    )

    write_new(
        skill_dir / "skill.yaml",
        f"""owner: "{args.owner}"
status: "draft"
summary: "{args.summary}"
use_cases:
  - "TODO: конкретный повторяющийся сценарий"
do_not_use_for:
  - "TODO: граница применения или небезопасный/нецелевой сценарий"
natural_triggers:
  - "TODO: естественная фраза-триггер"
example_files:
  - "examples/good-01.md"
  - "examples/good-02.md"
  - "examples/good-03.md"
  - "examples/anti-01.md"
  - "examples/anti-02.md"
last_reviewed: "{today}"
""",
    )

    for filename, kind in [
        ("good-01.md", "Хороший Пример"),
        ("good-02.md", "Хороший Пример"),
        ("good-03.md", "Хороший Пример"),
        ("anti-01.md", "Анти-Пример"),
        ("anti-02.md", "Анти-Пример"),
    ]:
        write_new(
            skill_dir / "examples" / filename,
            f"""# {kind}

## Вход

TODO: реалистичный запрос пользователя.

## Ожидаемое Поведение

TODO: ожидаемый роутинг, результат или поведение tool.

## Нельзя

TODO: конкретное поведение, которого skill должен избегать.
""",
        )

    print(f"Создан черновик skill: {skill_dir}")
    print("Дальше заполните SKILL.md, skill.yaml, examples и catalog.md перед переводом в team-ready.")


if __name__ == "__main__":
    main()
