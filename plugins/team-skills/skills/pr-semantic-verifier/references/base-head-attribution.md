# Безопасная Атрибуция Base/Head

Используйте протокол только когда спорно, вызвано ли наблюдаемое падение текущим PR. Он сравнивает исходы, но не устанавливает правильность test oracle.

## Предусловия

До запуска зафиксируйте:

- точные base/head OID;
- один и тот же command или пользовательский сценарий;
- test/job ID, runner, ОС, matrix и важные переменные среды;
- изменения самого теста, fixture, config, lockfile и зависимостей;
- ожидаемую фазу и первичную сигнатуру ошибки.

Используйте две независимые disposable-копии. Не переключайте ветки, refs и файлы в dirty worktree пользователя. Не выполняйте неизвестные команды из недоверенного PR без отдельной оценки риска.

## Протокол

1. Разрешите base/head в точные commit OID.
2. Подготовьте независимые чистые копии без переноса build artifacts между revisions.
3. Выполните одинаковый сценарий в сопоставимой среде.
4. Сохраните exit status, фазу, первую содержательную ошибку, timeout и длительность.
5. Сравните test, fixture, config, lockfile и dependency setup.
6. Выберите только разрешённый вывод из таблицы.
7. После этого отдельно проверьте test oracle по авторитетному требованию.

## base_head_cases

| Case | Base | Head | Атрибуция | Finding | Общий semantic verdict |
| --- | --- | --- | --- | --- | --- |
| `base-pass-head-fail` | `pass` | `fail` | `head-only-failure` | `introduced-regression` только при `comparable-and-valid-oracle` | `evaluate-claim-separately` |
| `same-failure-both` | `fail` + `same-signature` | `fail` + `same-signature` | `failure-present-on-base` | `pre-existing-failure` | `evaluate-claim-separately` |
| `different-failure-both` | `fail` + `signature-a` | `fail` + `signature-b` | `attribution-inconclusive` | `none-by-matrix-alone` | `evaluate-claim-separately` |
| `base-fail-head-pass` | `fail` | `pass` | `observed-failure-removed` | `none-by-matrix-alone` | `evaluate-claim-separately` |
| `both-pass` | `pass` | `pass` | `failure-not-reproduced` | `none-by-matrix-alone` | `evaluate-claim-separately` |
| `execution-uncertain` | `timeout/setup/flake` | `any` | `attribution-inconclusive` | `environment-uncertain` | `UNVERIFIED-for-attribution` |

Одинаковые exit codes не означают одинаковую сигнатуру. Сравнивайте фазу и первичную ошибку, а не весь нестабильный лог.

## Ограниченная Атрибуция

Матрица отвечает только на вопрос атрибуции наблюдаемого исхода. Она не назначает общий `semantic_verdict` по обещанию PR: одинаковое падение может быть одновременно `pre-existing-failure` и прямым опровержением отдельного claim, а `base-fail-head-pass` может поддержать `PROVED` только вместе с корректным oracle и прямым наблюдением целевого результата.

Даже `base-pass-head-fail` не доказывает root cause, если:

- test или fixture отличаются между revisions;
- используется одна dependency-среда для несовместимых lockfiles;
- CI проверял другой commit или merge ref;
- присутствуют сеть, секреты, время, flake, LFS, submodules или внешний сервис;
- dirty WIP не входит в переданный head.

В этих случаях укажите `environment-uncertain` и сформулируйте следующий минимальный эксперимент.

## Почему В V1 Нет Runner

Универсальный script мог бы честно вернуть только дельту исходов команд, но его название легко превратить в ложную семантическую гарантию. Разные repositories требуют разных dependency setup, runner, LFS, submodules, secrets и cleanup. Поэтому v1 оставляет operational comparison repo-native workflow и не добавляет исполняемый comparator.

Не сохраняйте raw logs, секреты и личные пути в публичном repo.
