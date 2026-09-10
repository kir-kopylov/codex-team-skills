# Хороший Пример: Проверка Telemetry

## Вход

Пользователь просит: "Проверь local sanitized trace krupnee_lift: mode=soft_hint, microstep_count=2, user_choice=ignored, final_krupnee_prompt_created=false."

## Ожидаемое Поведение

Codex фиксирует `trace_source: local_sanitized_trace`, сверяет trace с `references/telemetry-schema.md`, проверяет допустимые значения и говорит, соответствует ли запись второму связанному микрошагу.

## Нельзя

Нельзя сохранять или просить raw-приватные сообщения, если для проверки хватает минимального trace.
