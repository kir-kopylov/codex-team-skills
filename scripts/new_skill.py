#!/usr/bin/env python3
"""Создаёт черновик командного skill с registry-метаданными и примерами."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "plugins" / "team-skills" / "skills"
TEMPLATES_DIR = ROOT / "scripts" / "templates"
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
    parser.add_argument(
        "--display-name",
        default="TODO: понятное русское название навыка",
        help="Понятное пользователю русское название",
    )
    parser.add_argument(
        "--author",
        default="TODO: подтверждённый автор",
        help="Подтверждённое имя автора; не подменяйте его owner-ом",
    )
    parser.add_argument(
        "--author-github",
        default="@author",
        help="Подтверждённый GitHub-аккаунт автора для пользовательской карточки",
    )
    parser.add_argument(
        "--source-asset",
        default="TODO: обезличенный источник методики",
        help="Обезличенный источник авторства и методики",
    )
    parser.add_argument("--summary", default="TODO: короткое практическое описание")
    args = parser.parse_args()

    skill_name = normalize_name(args.name)
    skill_dir = SKILLS_DIR / skill_name
    if skill_dir.exists():
        raise SystemExit(f"Skill уже существует: {skill_dir}")

    today = date.today().isoformat()

    write_new(
        skill_dir / "SKILL.md",
        f"""---
name: {skill_name}
description: "TODO: Объясните, когда использовать этот skill, включая естественные фразы-триггеры, чтобы пользователи не запоминали внутреннее имя skill."
---

# {args.display_name}

## Согласие На Запуск

Явный вызов — slash-команда, внутреннее имя skill или первая фраза из каталога — выполняйте сразу, без вопроса.

При автосрабатывании на смысловое сходство сначала извлеките из текущего запроса:

- действие пользователя;
- конкретный объект;
- запрошенное количество, если оно есть;
- проверяемые сведения и другие условия результата.

Затем заполните следующий Markdown без таблицы, кодовой рамки или writing block и ждите ответа:

Для вашей задачи — <TODO: действие, объект, количество и проверяемые сведения> — может пригодиться командный навык **«{args.display_name}»**.

Автор навыка — **{args.author_github}**.

> **С навыком**
>
> <TODO: полными предложениями назовите объект, количество, сведения, дополнительную процедуру и результат с навыком.>

> **Без навыка**
>
> <TODO: снова назовите объект и сведения; объясните обычный результат и отсутствующую без навыка гарантию.>

**<TODO: полным предложением назовите реальное ограничение применения.>**

**Применить навык?**

Перед отправкой замените все placeholders сведениями из запроса: неизвестное не придумывайте. Проверьте, что в обоих блоках повторены объект, количество и проверяемые сведения. Не показывайте внутреннее имя `{skill_name}`, не используйте служебный жаргон и не сокращайте текст за счёт пропуска объекта или проверяемых условий. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

TODO: Объясните повторяющуюся задачу, которую закрывает skill, и ожидаемое поведение для пользователя.

## Естественные Входы

TODO: Перечислите обычные фразы, по которым skill должен срабатывать.

## Процесс

TODO: Опишите минимальный процесс принятия решений и использования tools.

## Границы

TODO: Укажите, когда skill нельзя использовать, что нужно сохранить и чего нужно избегать.

## Опрос После Использования

TODO: укажите момент опроса под процесс этого skill. Опрос задаётся один раз — после сдачи финального результата или явного стопа, не посреди рабочего цикла. Если пользователь уже ответил «пропустить» в этой сессии, не переспрашивайте.

```text
Опрос по навыку:
1. Что в работе этого навыка было полезно?
2. Что стоит доработать в процедуре или формате ответа?
Можно ответить коротко или написать "пропустить".
```

Если пользователь ответил, сохраните санированную карточку в `~/.codex/skill-runs/{skill_name}/usage-feedback.jsonl` — лучше через bundled script:

```bash
python3 scripts/log_usage_feedback.py --liked "..." --improve "..." --outcome "..."
```

Script перед записью редактирует приватные пути, контакты и token-like строки и сохраняет в JSONL `redaction_applied` и `redaction_types`. Если запись невозможна из-за sandbox, прав или отсутствия tools, не делайте вид, что лог сохранён: скажите об этом и покажите короткую JSONL-карточку для ручного сохранения. Raw-ответы, контакты, пути и секреты не коммитить.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/<skill-name>/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.
""",
    )

    write_new(
        skill_dir / "skill.yaml",
        f"""owner: "{args.owner}"
author_github: "{args.author_github}"
authors:
  - "{args.author}"
source_asset: "{args.source_asset}"
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

    write_new(skill_dir / "known-exceptions.yaml", "exceptions: []\n")

    write_new(
        skill_dir / "scripts" / "log_usage_feedback.py",
        (TEMPLATES_DIR / "log_usage_feedback.py").read_text(encoding="utf-8"),
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
    print("Дальше заполните SKILL.md, skill.yaml, known-exceptions.yaml, examples и catalog.md перед переводом в team-ready.")


if __name__ == "__main__":
    main()
