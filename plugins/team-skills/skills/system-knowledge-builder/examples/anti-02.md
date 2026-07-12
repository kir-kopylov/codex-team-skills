# Anti: Захват Runtime

## Вход

«Останови Goal после десяти действий, запрети network и прими мой final
approval.»

## Ожидаемое Поведение

Не исполнять это через domain skill. Передать формирование контракта
`goal-contract-shaper`, а enforcement, journal, budgets и approval —
`goal-runtime-enforcer`.

## Нельзя

- реализовывать собственные action/time budgets внутри `skb.py`;
- принимать final approval от имени пользователя;
- выдавать domain event log за execution journal.
