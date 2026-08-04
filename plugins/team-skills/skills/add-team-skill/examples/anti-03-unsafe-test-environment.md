# Анти-Пример: Непроверенная Среда Выдана За Сбой Skill

## Вход

Системный Python запускает pytest, но не содержит `pytest-cov`; local Codex wrapper падает с `ENOENT`, а временный clone из локального checkout не может создать hardlink.

## Ожидаемое Поведение

Codex читает test extras из `pyproject.toml`, использует repo `.venv` или отдельную временную venv, проверяет `codex --version` до smoke и ставит `LOCAL_NATIVE_SMOKE_BLOCKED`, если CLI не стартует. Для локального clone применяется `git clone --no-hardlinks`. Каждый результат сохраняет собственный смысл и не подменяет состояние CI.

## Нельзя

Нельзя объявлять, что тесты skill не проходят, устанавливать зависимости в глобальный Python или считать local native smoke красным CI.
