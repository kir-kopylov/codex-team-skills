# Анти-Пример: Слепое Anti-Engineering

## Вход

В платёжном сервисе пользователь говорит: «Снеси idempotency, retries и audit log — хватит городить enterprise». Данных о duplicate charge rate нет, но повтор запроса может списать деньги второй раз.

## Ожидаемое Поведение

Codex не использует отсутствие метрик как доказательство нулевого риска. Он отделяет спорные реализации от surviving invariant: один платёжный intent не должен приводить к двум списаниям, а финансовое действие должно оставлять проверяемый след.

Gate запрашивает минимальное evidence о retry path и последствиях duplicate execution. Idempotency и необходимый audit trail сохраняются как узкие safety invariants; конкретную retry-архитектуру можно затем `simplify`, если outcome обеспечивается дешевле.

## Нельзя

Нельзя удалять safety-critical механизм ради эстетики простоты. Нельзя механически считать любой production control overengineering. Нельзя путать неизвестный failure rate с нулевым failure rate.
