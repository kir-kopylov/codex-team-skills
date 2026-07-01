# Review Prompt

Используй этот prompt для аудита явно переданных разговоров, sanitized traces, dissatisfaction feedback packets, feedback inbox rows, eval fixtures или proposed runtime behavior для `krupnee_lift`.

Цель review - защитить главный design tension:

- runtime должен быть коротким и почти незаметным;
- review может быть аналитическим и явным;
- единичная маленькая просьба не является микроменеджментом;
- повторяющиеся связанные микрошаги должны стать видимыми, когда цельный рабочий эпизод уже присутствует;
- высокорисковые неполные задачи могут требовать вмешательства сразу.

## Audit Procedure

1. Определи `trace_source` по `review-intake-contract.md`.
2. Если source не передан, запроси один минимальный материал и не делай вид, что есть доступ к истории.
3. Найди общий объект, цель, артефакт или workflow, если он есть.
4. Отдели one-off tasks от связанных microstep sequences.
5. Восстанови `krupnee_buffer` для релевантного окна.
6. Примени scoring из `krupnee-runtime/references/trigger-rules.md`.
7. Выбери ожидаемый режим:
   - `observe`;
   - `soft_hint`;
   - `offer_lift`;
   - `risk_override`;
   - `do_not_intervene`.
8. Проверь, выполнил ли агент настоящую просьбу пользователя до meta-guidance.
9. Проверь, сохранил ли `offer_lift` выбор пользователя и не звучал ли как обвинение.
10. Если lift принят, проверь, что агент задавал только один вопрос за раз.
11. Если пользователь выбрал работу по кускам, проверь, что агент не повторял offer в том же эпизоде без нового повода.
12. Запиши минимальную telemetry по `telemetry-schema.md`.
13. Если source - `dissatisfaction_feedback` или `feedback_inbox_row`, проверь, что пользователь не должен был вручную копировать trace или знать GitHub.
14. Выдай `review_output`: verdict, trace, optional eval case, optional patch proposal, `changelog_needed` или `no_action`.

## Failure Labels

- `false_positive_first_microstep` - lift предложен на первом низкорисковом запросе.
- `false_positive_unrelated_topics` - разные темы ошибочно собраны в один эпизод.
- `missed_lift_pattern` - три связанных микрошагa были, но offer не появился.
- `missed_risk_override` - рискованная неполная задача выполнена без ключевого уточнения.
- `gatekeeper_behavior` - агент заблокировал простое выполнение лишней методологией.
- `overlong_runtime` - runtime-ответ стал аналитическим и тяжёлым.
- `ignored_user_preference` - пользователь попросил по кускам или без вопросов, но агент продолжил вмешиваться.
- `missing_trace_source` - review запрошен без диалога, trace, feedback packet или eval fixture.
- `pretended_access` - review сделал вид, что имеет доступ к чужим эпизодам или командной telemetry.
- `feedback_packet_incomplete` - dissatisfaction feedback не содержит enough expected/actual behavior для verdict.
- `manual_burden_leak` - runtime переложил на пользователя copy-paste trace, GitHub issue или repo-структуру.
- `good_runtime` - вмешательство было минимальным, уместным и вовремя.

## Output Format

```markdown
## Verdict
[good_runtime | needs_adjustment | failure_label]

## Expected Mode
[observe | soft_hint | offer_lift | risk_override | do_not_intervene]

## Buffer Reconstruction
- trace source:
- shared object:
- suspected goal:
- microstep count:
- coherence score:
- risk level:

## Reason
[короткое объяснение]

## Correction
[минимальная правка runtime-поведения, если нужна]

## Trace
[минимальный telemetry object]

## Review Output
[verdict | eval_case | patch_proposal | changelog_needed | no_action]
```
