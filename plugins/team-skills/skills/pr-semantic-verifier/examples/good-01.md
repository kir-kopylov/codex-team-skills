# Зелёный CI Проверяет Только Строку

## Вход

GitHub PR обещает, что новый skill виден и запускается в Desktop. Все checks зелёные, но профильный тест только ищет нужную фразу в `SKILL.md`. Свежего запуска Desktop на точном `head` нет.

## Ожидаемое Поведение

```yaml
decision:
  run_verifier: true
  semantic_verdict: PROXY_ONLY
  finding_types:
    - evidence-scope-gap
    - coverage-gap
  highest_proven_layer: repository
  unverified_layers:
    - installation
    - runtime
    - user-outcome
  mutation_allowed: false
```

Skill фиксирует точные base/head, обещанный пользовательский результат и целевую поверхность `runtime`. Наличие строки признаётся прямым доказательством только слоя `repository`.

Итог:

- `semantic_verdict`: `PROXY_ONLY`;
- `finding_types`: `evidence-scope-gap`, `coverage-gap`;
- доказано: файл содержит ожидаемую инструкцию на точном head;
- не доказано: discovery, запуск и сохранение поведения в Desktop;
- внешний `runtime` остаётся `UNVERIFIED`;
- следующее действие — безопасная проба на целевой поверхности, а не новая строковая проверка.

## Нельзя

Нельзя объявлять пользовательский результат доказанным по зелёному CI, наличию файла, строке, mock или установленному plugin. Нельзя придумывать состояние компьютера пользователя.
