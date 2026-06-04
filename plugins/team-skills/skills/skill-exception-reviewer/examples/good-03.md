# Хороший Пример: Patch Proposal Без Применения

## Вход

Пользователь пишет: "Вот два sanitized exception packets по `invoice-checker`. Сгруппируй и покажи, что нужно добавить в skill, но пока ничего не меняй в repo."

## Ожидаемое Поведение

Codex анализирует packets, выделяет один кандидат в правило и один слабый единичный сбой. Он выдаёт markdown proposal с секциями `known-exceptions.yaml`, `SKILL.md`, `references/domain-playbook.md` при интерфейсном сбое, `examples/`, `tests/` и `Gate`. В конце явно пишет, что patch не применён, а следующий шаг - human approval, затем отдельное внесение изменений и `python3 -m pytest`.

## Нельзя

Нельзя запускать `apply_patch`, менять файлы или делать commit в рамках reviewer-запроса, если пользователь просил только proposal.
