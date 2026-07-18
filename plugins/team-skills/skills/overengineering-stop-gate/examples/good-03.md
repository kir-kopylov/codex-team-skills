# Хороший Пример: Scope Сужен До Одной CI-Проверки

## Вход

Для маленького repo предлагают постоянный validation service с очередью, database, dashboard, retries и on-call. Исходная потребность: не принимать pull request, если `skill.yaml` не соответствует схеме. Пользователь просит оставить только неизбежное.

## Ожидаемое Поведение

Codex возвращает outcome одним предложением: невалидный skill package не должен попадать в `main`.

В ledger постоянный service получает `simplify`: боль доказана, но daemon, database и on-call не создают отдельной ценности для проверки на merge boundary. Узкая schema-проверка в существующем CI сохраняет outcome с меньшей стоимостью владения.

Surviving invariant: pull request с невалидным `skill.yaml` получает красный обязательный check. Единственный следующий шаг — заменить service одной CI-проверкой и прогнать одну валидную и одну невалидную fixture.

## Нельзя

Нельзя удалять validation целиком: потребность доказана. Нельзя переносить dashboard, queue и retries в новый «облегчённый» сервис и называть это simplification.
