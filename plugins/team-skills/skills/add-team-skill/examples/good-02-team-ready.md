# Хороший Пример: Довести До Team-Ready

## Вход

Пользователь пишет: “Я уже сделал draft skill `invoice-checker`. Доведи его до team-ready по правилам repo.”

## Ожидаемое Поведение

Codex читает существующую папку skill, `skill.yaml`, examples, `catalog.md` и тесты. Он исправляет frontmatter, description, registry-поля, добавляет недостающие good/anti examples, убирает шаблонные заглушки, добавляет строку в catalog и запускает `python3 -m pytest`. В финале Codex кратко перечисляет, что изменилось и прошли ли проверки.

## Нельзя

Нельзя пересоздавать существующий skill поверх текущих файлов. Нельзя менять несвязанные skills. Нельзя переводить технические ключи `owner`, `status`, `example_files`, `SKILL.md` или `plugin.json`.
