# Runtime Handoff

## Граница Ответственности

`goal-contract-shaper` владеет диалогом формирования и подтверждения условий.
`goal-runtime-enforcer` владеет JSON Schema, проверкой контракта, journal,
budgets, retries, recovery и hook enforcement. Shaper не копирует schema и не
обещает, что установка plugin сама по себе означает работающие hooks.

## Команды Передачи

```text
goalrt contract compile goal-contract.draft.json --output goal-contract.json
goalrt contract validate goal-contract.json
goalrt contract render-goal goal-contract.json --output goal.txt
```

Если команды нет в `PATH`, допускается вызвать тот же `goalrt.py` по пути,
который сообщил установленный runtime skill. Нельзя искать случайную копию
schema или собирать несовместимый JSON вручную.

## Поля Draft

Передавайте как минимум:

- `goal_id` и `objective`;
- требования completion gate, отдельные approval/resume tokens;
- allow/deny capabilities;
- action, elapsed и identical-retry budgets;
- token/cash budget только с фактическим классом enforcement;
- retry и BLOCKED policy;
- paths для journal, state, metrics и evidence;
- freshness и evidence requirements;
- domain profile.

Runtime дополняет draft своей enforcement matrix и отклоняет неизвестную schema,
ложный hard token budget, выход paths за state root и неподдерживаемый режим.

## Классы Гарантий

- `hard`: runtime наблюдает вызов до side effect и может его запретить;
- `partial`: покрыт только конкретный наблюдённый tool path;
- `advisory`: значение записано в контракте, но runtime не имеет точного
  счётчика или stop API;
- `uncovered`: hook не получает этот вызов или среда не была проверена.

`PARTIAL_ENFORCEMENT` не является дефектом формулировки. Это честное описание
границы платформы. Текст shaper не может повысить эту гарантию.

## Fallback Без Runtime

Верните только текст `/goal` и отчёт:

```text
Runtime: отсутствует.
Enforcement: текстовый, supervised.
Hard guarantees: нет автоматически проверенных.
```

Не создавайте `goal-contract.json`, который никто не валидировал, и не называйте
его машиночитаемым контрактом runtime.
