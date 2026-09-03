# Уже Локализованный Корректный CI-Сбой

## Вход

Корректный unit test проходит на base, падает на head и напрямую проверяет документированный product-инвариант. Пользователь просит найти root cause и исправить код.

## Ожидаемое Поведение

```yaml
decision:
  run_verifier: false
  route_to: gh-fix-ci
  mutation_allowed: false
```

Не запускать полный `pr-semantic-verifier`: сомнения в test oracle и доказательном слое уже сняты. Передать exact check, failing assertion, base/head и изменённый scope в `gh-fix-ci`.

## Нельзя

Нельзя раздувать локализованный bugfix до общего аудита доказательств. Нельзя менять тест вместо дефектной реализации.
