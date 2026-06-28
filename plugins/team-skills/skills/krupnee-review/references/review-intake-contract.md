# Review Intake Contract

`krupnee-review` - offline/manual evaluator. Он не является watcher, telemetry daemon, CI service или автоматическим наблюдателем runtime.

## trace_source

Review может работать только с явно переданным материалом:

- `pasted_dialogue` - пользователь вставил фрагмент диалога;
- `local_sanitized_trace` - maintainer передал очищенный local trace;
- `feedback_packet` - пользователь описал жалобу, missed trigger или false positive;
- `dissatisfaction_feedback` - runtime сформировал `krupnee_review_packet` после недовольства пользователя вмешательством;
- `feedback_inbox_row` - maintainer или connector передал строку из `Team Codex Skill Feedback Inbox`;
- `eval_fixture` - maintainer или eval runner передал тестовый case;
- `runtime_self_report` - runtime сам вывел минимальный trace в текущем диалоге, если это было явно предусмотрено.

Если source не передан, review не должен реконструировать эпизод по догадке.

## review_trigger

Кто может запускать review:

- пользователь после жалобы на поведение runtime;
- maintainer при разборе sanitized trace;
- author review после новых rows в `Team Codex Skill Feedback Inbox`;
- автор skill при добавлении eval cases;
- eval runner, если он явно передал fixture;
- runtime только в форме минимального self-report или feedback packet, а не через скрытое чтение истории.

## access_policy

По умолчанию нет доступа к:

- чужим диалогам;
- командной telemetry;
- локальным traces других пользователей;
- скрытой истории срабатываний;
- внешним системам, если пользователь не передал конкретный источник.

Не запрашивай raw private logs, если хватает короткого обезличенного фрагмента. Не сохраняй private paths, tokens, contacts, private URLs или raw client text в repo.

## feedback_channel

Есть два равноценных feedback channels для доставки материала автору skill. Оба используют один и тот же `krupnee_review_packet`.

### Team Codex Skill Feedback Inbox

Канал для нетехнических пользователей и командного inbox:

```text
Team Codex Skill Feedback Inbox
repo: codex-team-skills
```

Это единый Sheet на repo/team skill package. Не отдельный Sheet на каждый skill и не общий Sheet на все взаимодействия команды с Codex.

### GitHub Issue

Канал для более продвинутых участников команды и maintainers. Это равноценный channel, а не второстепенный fallback. Issue body должен содержать тот же `krupnee_review_packet`, что и Sheet row.

Строка feedback или issue body должны содержать:

```yaml
created_at: ""
repo: codex-team-skills
skill_name: ""
skill_version: ""
feedback_channel: team_codex_skill_feedback_inbox # team_codex_skill_feedback_inbox | github_issue
user_signal: ""
dissatisfaction_signal: ""
what_happened: ""
expected_behavior: ""
actual_behavior: ""
suspected_issue: unknown
minimal_dialogue_excerpt: []
privacy_level: sanitized
owner: ""
status: new
next_action: ""
review_packet: {}
author_notified: false
```

Не утверждай, что Sheet, GitHub connector или auto-notification существуют, пока они не подключены. Не утверждай, что row записана или issue создан, пока connector не выполнил действие.

## runtime_trace_mechanism

В текущем MVP нет автоматического механизма записи telemetry. `telemetry-schema.md` описывает формат записи, а не место хранения.

Допустимые варианты для будущей реализации:

- in-message self-report, когда пользователь просит показать trace;
- локальный private sink вне repo, например maintainer-controlled log;
- CI/eval fixture, созданный вручную;
- feedback packet, который пользователь вставляет в review.
- строка из `Team Codex Skill Feedback Inbox`, если Sheet и connector подключены;
- GitHub Issue body, если GitHub channel и connector подключены или maintainer явно передал issue content.

Пока конкретный sink не реализован, review должен говорить: "могу разобрать только переданный материал".

## review_output

После анализа review должен выдать один или несколько результатов:

- `verdict` - `good_runtime`, `needs_adjustment` или failure label;
- `expected_mode` - ожидаемый режим intervention;
- `trace` - минимальный telemetry object;
- `eval_case` - новый или уточнённый eval case, если failure повторяемый;
- `patch_proposal` - точечная правка runtime/review docs, если проблема системная;
- `changelog_needed` - нужен ли changelog update;
- `no_action` - если поведение корректно или данных недостаточно.

Review не должен сам менять runtime, changelog или eval cases без отдельного явного запроса на правку файлов.

## author_workflow

Codex может сказать автору:

```text
У тебя новые feedback rows по krupnee-runtime. Разобрать?
```

После согласия автора:

1. Сгруппировать похожие жалобы.
2. Предложить eval cases.
3. Предложить patch в runtime/review docs.
4. Предложить changelog update.
5. Подготовить изменения в repo.

Без согласия maintainer не меняй runtime автоматически.

## connector_boundary

Schema - это формат packet, row или issue body. Channel - это Sheet или GitHub Issue. Connector - это техническая возможность записи в выбранный channel. Review - это разбор переданного материала.

Automatic write и notification являются optional capability. Без connector review всё равно может разобрать вручную переданный packet, row или issue body.
