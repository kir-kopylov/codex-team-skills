# Хороший Пример: Удаление Adapter

## Вход

Пользователь просит удалить заброшенный provider adapter. Единственным поддерживаемым путём остаётся основной provider; миграции внешних машин нет.

## Ожидаемое Поведение

Codex фиксирует остаточный контракт и находит implementation, dependency, config schema, secrets documentation, feature flag, factory registration, test fixtures, examples и package metadata старого adapter. Он удаляет только подтверждённую поверхность, обновляет проверки контракта и не создаёт абстрактный compatibility layer.

После negative scan Codex запускает основной provider через настоящий entrypoint, затем targeted и полный suite. В результате `migrate once` честно равен «ничего», потому что доказанного deployed legacy-следа нет.

## Нельзя

Нельзя оставлять dead config и dependency «на всякий случай». Нельзя ограничиваться import test: остаточный основной путь должен пройти реальную пробу.
