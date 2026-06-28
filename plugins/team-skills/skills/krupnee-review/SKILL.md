---
name: krupnee-review
description: "Используйте этот skill как offline/manual evaluator, когда пользователь, maintainer или eval runner явно передал диалог, sanitized trace, dissatisfaction feedback packet, строку из Team Codex Skill Feedback Inbox, GitHub Issue body или eval fixture и нужно проверить, правильно ли сработал krupnee Lift: режим observe / soft_hint / offer_lift / risk_override / do_not_intervene, telemetry, eval cases и риск утяжелить runtime. Не использовать как автоматический наблюдатель чужих эпизодов."
---

# Krupnee Review

## Согласие На Запуск

Явный вызов — slash-команда, имя skill или первая фраза из каталога — выполняйте сразу, без вопроса. При автосрабатывании на смысловое сходство сначала спросите одной строкой: «Задача похожа на team skill `krupnee-review` — offline/manual evaluator для срабатываний krupnee Lift и feedback автора skill. Применить или решить без него?» — и ждите ответа. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

Этот skill нужен не для вмешательства в живую работу пользователя, а для offline/manual аудита применения `krupnee_lift`. Он может быть длинным, аналитическим и проверочным, потому что не должен попадать в короткий runtime.

Review не является автоматическим наблюдателем. Он работает только на материале, который явно передали в запросе: фрагмент диалога, sanitized trace, dissatisfaction feedback packet, строка из `Team Codex Skill Feedback Inbox`, GitHub Issue body или eval fixture.

## Процесс

1. Проверь `trace_source`: откуда взят материал для review.
2. Если материала нет, запроси один минимальный источник: фрагмент диалога, trace, feedback packet или eval case.
3. Определи, был ли один общий объект, цель, артефакт или рабочий эпизод.
4. Отдели единичную просьбу от серии связанных микрошагов.
5. Восстанови `krupnee_buffer` по короткому окну сообщений.
6. Проверь scoring и ожидаемый режим вмешательства.
7. Сравни ожидаемое поведение с фактическим ответом агента.
8. Если материал пришёл из feedback inbox, проверь `dissatisfaction_signal`, `expected_behavior`, `actual_behavior`, `suspected_issue` и `review_packet`.
9. Выдай review output: verdict, причину, telemetry, optional eval case, optional patch proposal и указание, нужен ли changelog.

## References

- `references/review-intake-contract.md` - trace sources, review triggers, access policy и output contract.
- `references/review-prompt.md` - полный audit prompt и failure labels.
- `references/telemetry-schema.md` - минимальный trace применения.
- `references/eval-cases.md` - eval-набор для проверки поведения.
- `references/version-history.md` - история версии 0.2.0.

## Границы

Не используй review вместо runtime. Если пользователь просит просто выполнить маленькую задачу, нужен `krupnee-runtime` или обычное выполнение, а не аналитический аудит.

Не делай вид, что review может сам посмотреть чужие диалоги, командную telemetry или историю срабатываний. Без явно переданного материала review должен остановиться на запросе источника. Не добавляй в review raw-приватный контекст; достаточно коротких labels и обезличенных фрагментов.

Не меняй runtime, examples или changelog автоматически без подтверждения maintainer. Review может предложить patch proposal, но repo-правка - отдельное действие.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/<skill-name>/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.
