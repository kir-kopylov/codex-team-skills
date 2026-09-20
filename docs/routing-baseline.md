# Базовая Линия Маршрутизации

Эта таблица отвечает на один вопрос: находит ли обычная формулировка задачи
свой навык, если у модели есть только описания навыков и ничего больше.
Проверка по `natural_triggers` этого не показывает — описания собраны из тех же
фраз, поэтому там упирается в 100%. Здесь взят независимый набор: входы
хороших примеров, которые писались как рабочие запросы, а не как триггеры.

Замер ничего не меняет в навыках. Правка описаний по найденным парам — отдельная
задача.

## База Замера

- Commit: `56fa005` (`main`, «Merge pull request #183 from
  kir-kopylov/claude/skill-body-size-test-ea7ab2»), дата замера — 2026-09-20.
- Среда: macOS 26.6.2, Claude Code CLI 2.1.215, вызовы вида
  `claude -p --safe-mode --tools "" --strict-mcp-config --no-session-persistence`.
- Модель судьи: `claude-opus-5`. Идентификатор задан полностью: алиас `opus` в
  этом CLI разрешается в `claude-opus-4-8`, и первый прогон по ошибке ушёл туда.
- Объём: 198 входов × 3 прогона = 594 вызова, все с кодом возврата 0,
  неразобранных ответов нет. Отпечаток набора — `c621127ceebc`.
- Повторяемость: тот же набор прогонялся дважды по 594 вызова. Первый прогон дал
  172 попадания из 198, второй — 171; 26 промахов из 27 совпали, разошёлся один
  вход. Таблица ниже — по второму прогону, он же лежит в сырых ответах.
- Пока шёл замер, `main` продвинулся до `aca7677`, но описания навыков там не
  менялись: набор входов и список для выбора на новом `main` собираются
  байт-в-байт такими же, поэтому таблица остаётся действительной.

Соседний замер — «Базовая линия первого ответа навыков»
([docs/first-response-baseline.md](first-response-baseline.md)) — отвечает на
другой вопрос: как навык ведёт себя в первом ответе, когда он уже выбран. Здесь
измеряется только попадание в нужный навык.

## Как Считали

- Набор: секция `## Вход` каждого `examples/good-*.md` у навыков со статусами
  `team-ready` и `experimental`, кроме explicit-only `goal-contract-shaper-v3` —
  198 входов у 58 навыков, медиана длины 160 знаков. Ожидаемый навык — владелец
  примера.
- Вход помечен как «с дословным триггером», если содержит фразу из
  `natural_triggers` своего навыка после приведения к нижнему регистру и снятия
  пунктуации. Таких 33, остальные 165 — без.
- Список для выбора: все 64 навыка из `main` строками «Sxx: description». Имена
  обезличены, порядок перемешан фиксированным seed.
- Судья видит только этот список и один вход. Ожидаемого ответа, настоящих имён,
  памяти, `CLAUDE.md`, навыков и инструментов у него нет: каждый вызов — отдельный
  процесс в изолированном режиме. Проба чистоты контекста сохранена рядом с
  сырыми ответами.
- Попадание засчитано, если свой навык выбран минимум в двух прогонах из трёх.

Два факта из постановки задачи при пересчёте на этом commit не подтвердились:
входов с дословным триггером оказалось 33, а не 42, медиана — 160 знаков, а не
153. Объём набора совпал: 198 входов у 58 навыков.

## Результат

| Набор | Попаданий | Доля |
| --- | --- | --- |
| Без дословного триггера | 139 из 165 | 84,2% |
| С дословным триггером | 32 из 33 | 97,0% |
| Все входы | 171 из 198 | 86,4% |

Из 27 промахов 23 ушли в чужой навык и 4 — в ответ «ни один». Случаев без
большинства голосов нет: судья устойчив, почти все промахи — это три
одинаковых голоса за чужой навык.

## Промахи

| Вход | Навык-владелец | Файл примера | Куда ушёл |
| --- | --- | --- | --- |
| I004 | `daydzhest-proverennyh-izmeneniy` | [good-01-facts-before-advice.md](../plugins/team-skills/skills/daydzhest-proverennyh-izmeneniy/examples/good-01-facts-before-advice.md) | `proverka-izmeneniya-vozmozhnosti` |
| I005 | `daydzhest-proverennyh-izmeneniy` | [good-02-partial-coverage.md](../plugins/team-skills/skills/daydzhest-proverennyh-izmeneniy/examples/good-02-partial-coverage.md) | `proverka-izmeneniya-vozmozhnosti` |
| I029 | `kontrakt-tseli-do-starta` | [good-03-feedback-answer.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-03-feedback-answer.md) | `pravilo-iz-zhurnala-sboev` |
| I031 | `kontrakt-tseli-do-starta` | [good-05-format-limit-check.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-05-format-limit-check.md) | `otsev-lozhnogo-uspeha-operatsii` |
| I032 | `kontrakt-tseli-do-starta` | [good-06-partial-quote-confirmation.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-06-partial-quote-confirmation.md) | `kontrakt-navyka-do-sborki` |
| I033 | `kontrakt-tseli-do-starta` | [good-07-runtime-contract.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-07-runtime-contract.md) | `goal-contract-shaper-v3` |
| I034 | `kontrakt-tseli-do-starta` | [good-08-runtime-missing-fallback.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-08-runtime-missing-fallback.md) | `sverka-aktivnoy-versii-navykov` |
| I035 | `kontrakt-tseli-do-starta` | [good-09-real-question-gate.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-09-real-question-gate.md) | `karta-sistemy-do-pravok` |
| I036 | `kontrakt-tseli-do-starta` | [good-10-local-blocked-progress.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-10-local-blocked-progress.md) | `karta-sistemy-do-pravok` |
| I037 | `kontrakt-tseli-do-starta` | [good-11-checkpoint-tail-resume.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-11-checkpoint-tail-resume.md) | `shag-posle-prervannoy-tseli` |
| I038 | `kontrakt-tseli-do-starta` | [good-12-lifecycle-handoff.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-12-lifecycle-handoff.md) | `dobavlenie-navyka-v-biblioteku` |
| I039, дословный триггер | `kontrakt-tseli-do-starta` | [good-13-post-action-readback.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-13-post-action-readback.md) | `goal-contract-shaper-v3` |
| I073 | `peredelka-dogovorov-arendy` | [good-03.md](../plugins/team-skills/skills/peredelka-dogovorov-arendy/examples/good-03.md) | `verstka-docx-po-standartu` |
| I103 | `pr-semantic-verifier` | [good-04.md](../plugins/team-skills/skills/pr-semantic-verifier/examples/good-04.md) | `otsev-lozhnogo-uspeha-operatsii` |
| I115 | `provedenie-vetki-do-uborki` | [good-02.md](../plugins/team-skills/skills/provedenie-vetki-do-uborki/examples/good-02.md) | `sverka-git-pered-deystviem` |
| I119 | `proverka-aktualnosti-v-momente` | [good-02.md](../plugins/team-skills/skills/proverka-aktualnosti-v-momente/examples/good-02.md) | «ни один» |
| I120 | `proverka-aktualnosti-v-momente` | [good-03.md](../plugins/team-skills/skills/proverka-aktualnosti-v-momente/examples/good-03.md) | «ни один» |
| I126 | `proverka-lotov-perepiskoy` | [good-03.md](../plugins/team-skills/skills/proverka-lotov-perepiskoy/examples/good-03.md) | `dopusk-saytov-do-tsikla` |
| I128 | `proverka-prichin-sboya` | [good-02-ci-artifact-vs-runtime.md](../plugins/team-skills/skills/proverka-prichin-sboya/examples/good-02-ci-artifact-vs-runtime.md) | `otsev-lozhnogo-uspeha-operatsii` |
| I129 | `proverka-prichin-sboya` | [good-03-green-ui-vs-outcome.md](../plugins/team-skills/skills/proverka-prichin-sboya/examples/good-03-green-ui-vs-outcome.md) | `sloy-obryva-seti-windows` |
| I145 | `razgrom-plana-na-naivnost` | [good-03-experiment-design.md](../plugins/team-skills/skills/razgrom-plana-na-naivnost/examples/good-03-experiment-design.md) | `razbor-svoey-syroy-idei` |
| I146 | `razgrom-plana-na-naivnost` | [good-04-proportional-team-skills-remediation.md](../plugins/team-skills/skills/razgrom-plana-na-naivnost/examples/good-04-proportional-team-skills-remediation.md) | `stop-lishnemu-uslozhneniyu` |
| I147 | `razgrom-plana-na-naivnost` | [good-05-managed-fleet-justifies-platform.md](../plugins/team-skills/skills/razgrom-plana-na-naivnost/examples/good-05-managed-fleet-justifies-platform.md) | «ни один» |
| I148 | `razgrom-plana-na-naivnost` | [good-06-local-market-and-unavailable-sources.md](../plugins/team-skills/skills/razgrom-plana-na-naivnost/examples/good-06-local-market-and-unavailable-sources.md) | «ни один» |
| I160 | `shag-posle-prervannoy-tseli` | [good-03.md](../plugins/team-skills/skills/shag-posle-prervannoy-tseli/examples/good-03.md) | `narabotki-sessii-v-vetku` |
| I166 | `sloy-obryva-seti-windows` | [good-03.md](../plugins/team-skills/skills/sloy-obryva-seti-windows/examples/good-03.md) | `peresmotr-predposylok-posle-povtora` |
| I182 | `sverka-git-pered-deystviem` | [good-03.md](../plugins/team-skills/skills/sverka-git-pered-deystviem/examples/good-03.md) | `provedenie-vetki-do-uborki` |

## Путаемые Пары

Пары по убыванию числа промахов. Направление важно: слева навык, которому вход
принадлежит, справа — куда он ушёл.

| Навык-владелец | Куда ушёл | Промахов |
| --- | --- | --- |
| `daydzhest-proverennyh-izmeneniy` | `proverka-izmeneniya-vozmozhnosti` | 2 |
| `kontrakt-tseli-do-starta` | `goal-contract-shaper-v3` | 2 |
| `kontrakt-tseli-do-starta` | `karta-sistemy-do-pravok` | 2 |
| `kontrakt-tseli-do-starta` | `pravilo-iz-zhurnala-sboev` | 1 |
| `kontrakt-tseli-do-starta` | `otsev-lozhnogo-uspeha-operatsii` | 1 |
| `kontrakt-tseli-do-starta` | `kontrakt-navyka-do-sborki` | 1 |
| `kontrakt-tseli-do-starta` | `sverka-aktivnoy-versii-navykov` | 1 |
| `kontrakt-tseli-do-starta` | `shag-posle-prervannoy-tseli` | 1 |
| `kontrakt-tseli-do-starta` | `dobavlenie-navyka-v-biblioteku` | 1 |
| `peredelka-dogovorov-arendy` | `verstka-docx-po-standartu` | 1 |
| `pr-semantic-verifier` | `otsev-lozhnogo-uspeha-operatsii` | 1 |
| `provedenie-vetki-do-uborki` | `sverka-git-pered-deystviem` | 1 |
| `proverka-lotov-perepiskoy` | `dopusk-saytov-do-tsikla` | 1 |
| `proverka-prichin-sboya` | `otsev-lozhnogo-uspeha-operatsii` | 1 |
| `proverka-prichin-sboya` | `sloy-obryva-seti-windows` | 1 |
| `razgrom-plana-na-naivnost` | `razbor-svoey-syroy-idei` | 1 |
| `razgrom-plana-na-naivnost` | `stop-lishnemu-uslozhneniyu` | 1 |
| `shag-posle-prervannoy-tseli` | `narabotki-sessii-v-vetku` | 1 |
| `sloy-obryva-seti-windows` | `peresmotr-predposylok-posle-povtora` | 1 |
| `sverka-git-pered-deystviem` | `provedenie-vetki-do-uborki` | 1 |

Что видно по этой таблице:

- Десять промахов из 27 — у одного навыка `kontrakt-tseli-do-starta`, и уходят
  они каждый раз в разное место: семь разных адресов. Это не пара соседей, а
  описание, которое по входу не отличимо сразу от нескольких навыков.
- `provedenie-vetki-do-uborki` и `sverka-git-pered-deystviem` путаются взаимно,
  по одному промаху в каждую сторону.
- Два входа `kontrakt-tseli-do-starta` уходят в `goal-contract-shaper-v3`, а он
  explicit-only: по контракту запуска смысловое совпадение туда попадать не
  должно вообще.
- Все четыре ответа «ни один» приходятся на два навыка:
  `proverka-aktualnosti-v-momente` и `razgrom-plana-na-naivnost`.

Для сравнения: те же 594 вызова на `claude-opus-4-8` дали 160 из 198 (80,8%) и
38 промахов. Набор промахов частично другой, поэтому при правке описаний
опираться надо на ту модель, на которой замер повторяют.

Разброс между двумя прогонами на одной модели — один вход из 198, поэтому
разницу в один-два промаха нельзя считать результатом правки описания.

## Правка По Найденным Парам

Базовая линия выше — состояние до правки описаний. По её парам переписаны
`description` тринадцати навыков: двенадцати владельцев промахов и одного
навыка-магнита `goal-contract-shaper-v3`, который перетягивал смысловые запросы,
хотя по контракту запуска он explicit-only. Имена навыков, `skill.yaml` и тела
`SKILL.md` не менялись — только строка `description`.

| Проверка | Было | Стало |
| --- | --- | --- |
| Входы примеров, без дословного триггера | 139 из 165 (84,2%) | 156 из 165 (94,5%) |
| Входы примеров, с дословным триггером | 32 из 33 (97,0%) | 33 из 33 (100%) |
| Входы примеров, все | 171 из 198 (86,4%) | 189 из 198 (95,5%) |
| Фразы `natural_triggers` | 329 из 332 (99,1%) | 329 из 332 (99,1%) |

Условие правила из `CONTRIBUTING.md` выполнено на обеих проверках: ни один вход,
попадавший в свой навык до правки, не ушёл в чужой. Починено 18 входов примеров;
ни один вход примеров не съехал в «ни один».

По фразам `natural_triggers` доля не изменилась, но состав промахов другой:
ушёл промах «подходит ли это для /goal» — он попадал в explicit-only
`goal-contract-shaper-v3`, а теперь достаётся `kontrakt-tseli-do-starta`, как и
требует контракт запуска. Оставшиеся три промаха — короткие фразы одного навыка
`proverka-aktualnosti-v-momente` («проверь прямо сейчас», «проверь по моменту»,
«подтверди в моменте»); в них почти нет содержания, и судья отвечает «ни один».

Отпечатки наборов после правки: `9837e83baa0c` для входов примеров,
`7fdb558298a1` для фраз `natural_triggers`.

### Остаточные Промахи

| Вход | Навык-владелец | Файл примера | Куда ушёл |
| --- | --- | --- | --- |
| I032 | `kontrakt-tseli-do-starta` | [good-06-partial-quote-confirmation.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-06-partial-quote-confirmation.md) | `pravilo-iz-zhurnala-sboev` |
| I034 | `kontrakt-tseli-do-starta` | [good-08-runtime-missing-fallback.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-08-runtime-missing-fallback.md) | `sverka-aktivnoy-versii-navykov` |
| I035 | `kontrakt-tseli-do-starta` | [good-09-real-question-gate.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-09-real-question-gate.md) | `karta-sistemy-do-pravok` |
| I036 | `kontrakt-tseli-do-starta` | [good-10-local-blocked-progress.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-10-local-blocked-progress.md) | `karta-sistemy-do-pravok` |
| I037 | `kontrakt-tseli-do-starta` | [good-11-checkpoint-tail-resume.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-11-checkpoint-tail-resume.md) | `shag-posle-prervannoy-tseli` |
| I038 | `kontrakt-tseli-do-starta` | [good-12-lifecycle-handoff.md](../plugins/team-skills/skills/kontrakt-tseli-do-starta/examples/good-12-lifecycle-handoff.md) | `dobavlenie-navyka-v-biblioteku` |
| I115 | `provedenie-vetki-do-uborki` | [good-02.md](../plugins/team-skills/skills/provedenie-vetki-do-uborki/examples/good-02.md) | `sverka-git-pered-deystviem` |
| I166 | `sloy-obryva-seti-windows` | [good-03.md](../plugins/team-skills/skills/sloy-obryva-seti-windows/examples/good-03.md) | `peresmotr-predposylok-posle-povtora` |
| I182 | `sverka-git-pered-deystviem` | [good-03.md](../plugins/team-skills/skills/sverka-git-pered-deystviem/examples/good-03.md) | `provedenie-vetki-do-uborki` |

Шесть из девяти — у `kontrakt-tseli-do-starta`: его территория граничит сразу с
несколькими навыками библиотеки, и одной правкой описания она не разводится.
Вход I037 оставлен сознательно: восстановление состояния по журналу — работа
`shag-posle-prervannoy-tseli`, а не контракта цели. Пара
`provedenie-vetki-do-uborki` и `sverka-git-pered-deystviem` продолжает меняться
местами на двух входах: обе правки сохранили пересечение по словам «ветка» и
«дерево».

## Чего Эта Таблица Не Доказывает

- Это не оценка качества навыков: измеряется только различимость `description`
  по обычной формулировке.
- Это не гарантия для живой сессии: у настоящего агента в контексте есть
  переписка и файлы проекта, а у судьи — только список и один вход.
- Входы примеров писали авторы навыков, поэтому набор ближе к идеальной
  формулировке, чем реальный запрос коллеги.
- Числа привязаны к commit, модели и списку из 64 навыков: добавление навыка
  меняет базу, и сравнивать можно только повтор на том же наборе.

## Как Повторить

```bash
python scripts/routing_baseline.py --source examples build
python scripts/routing_baseline.py --source examples run --model claude-opus-5
python scripts/routing_baseline.py --source examples report --model claude-opus-5
```

Вторая проверка — по фразам `natural_triggers`: те же три шага с
`--source triggers`. Её набор на этом commit — 332 фразы тех же 58 навыков.

Сравнение «до и после» правки `description` делается тем же набором: после
`build` отпечаток меняется, старые ответы перестают считаться готовыми, и
`report` не смешивает их с новыми. Отчёт по незаконченному прогону не печатается
без явного `--allow-partial`, чтобы доля по куску набора не выглядела итогом.

Рабочая папка по умолчанию — `~/.codex/goal-runs/routing-baseline` вне
репозитория: там лежат набор, сырые ответы судьи и сводка. В репозиторий они не
коммитятся. `run` возобновляется после обрыва — уже полученные ответы не
переспрашиваются, поэтому прогон можно дробить.
