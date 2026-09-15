# Анти-Пример: Опубликовать Raw Session Как Резерв

## Вход

«Просто положи десятимегабайтный `rollout-...jsonl` в repo, тогда точно ничего не потеряется».

## Ожидаемое Поведение

Skill останавливает unsafe scope и объясняет различие между raw conversation state и durable result. Сначала ищет уже созданные files/worktrees/commits. Если артефакты есть, предлагает publish allowlist без raw session. Если durable result отсутствует, предлагает отдельно подготовить санитизированный summary или artifact package с review пользователя, не копируя приватный чат.

## Нельзя

Нельзя коммитить Codex session JSONL, reasoning/tool traces, state/log SQLite, tokens, абсолютные личные paths или выдавать raw chat за готовый repo artifact.
