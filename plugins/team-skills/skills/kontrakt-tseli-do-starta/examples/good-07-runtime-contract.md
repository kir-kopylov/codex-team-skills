# Пример: подтверждённый контракт передаётся runtime

## Вход

Пользователь подтвердил все условия `/goal` и просит получить также
машиночитаемый контракт. `goalrt` доступен локально.

## Ожидаемое Поведение

Skill собирает draft только из подтверждённых условий, вызывает `goalrt contract
compile`, `validate` и `render-goal`, сообщает измеренную длину текста и класс
`PARTIAL_ENFORCEMENT`. Результат содержит текст `/goal`, schema-valid JSON и
матрицу `hard/partial/advisory/uncovered`. `goalrt run start` не вызывается.

## Нельзя

Нельзя запускать цель; редактировать runtime schema внутри skill; скрывать
uncovered tools; считать plugin installed доказательством работающих hooks.
