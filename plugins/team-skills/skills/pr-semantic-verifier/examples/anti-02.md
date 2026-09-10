# Общий Архитектурный Аудит Без PR

## Вход

Пользователь просит разобрать архитектурную идею, риски и production gaps. Нет GitHub PR, diff, base/head или конкретного проверяемого обещания изменения.

## Ожидаемое Поведение

```yaml
decision:
  run_verifier: false
  route_to: production-forensic-auditor
  mutation_allowed: false
```

Не запускать `pr-semantic-verifier`. Передать исходный текст и заявленную цель в `production-forensic-auditor` либо выполнить обычный code review, если запрос относится к коду.

## Нельзя

Нельзя придумывать PR, SHA или test evidence. Нельзя сводить широкий архитектурный аудит к одному `semantic_verdict`.
