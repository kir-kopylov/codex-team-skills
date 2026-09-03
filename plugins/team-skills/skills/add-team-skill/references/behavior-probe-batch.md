# Пакетная Проба Первых Ответов

Этот reference расширяет одиночную пробу из `SKILL.md`, когда PR добавляет или
существенно меняет несколько skills. Он не вводит отдельный script и не
заменяет `pytest`.

## Как Определить Охват

Сравните рабочий scope с актуальной базой PR. В обычный пакет включите каждый
новый или существенно изменённый skill, если изменён его `SKILL.md`,
`known-exceptions.yaml`, используемый им файл из `references/`, `scripts/` или
`assets/`, либо правило запуска, способное изменить первый ответ. Изменение
только `known-exceptions.yaml` тоже включает skill: этот источник читается до
выполнения, а подходящий `do_next_time` способен изменить первый ответ.

Полный каталог skills проверяйте только в двух случаях:

- меняется общий поведенческий контракт библиотеки;
- пользователь прямо просит полную библиотечную пробу.

Для `draft` берите явный вызов. Для `experimental` и `team-ready` берите
дословную естественную фразу из пользовательского запроса, registry или
подтверждённого синтетического примера.

### Доказанный Снимок Изменений

До распределения строк один раз получите полный `batch_changed_source` от
`checked_base`. Обычного `git diff` недостаточно: он не показывает новые
untracked-файлы до staging, а сравнение базы сразу с worktree способно скрыть
committed или staged слой, перекрытый текущими bytes файла. Следующий
fail-closed producer независимо получает committed branch diff, staged,
unstaged tracked и untracked-файлы, объединяет их и возвращает отсортированный
JSON-массив repo-relative путей. Переменные `repo` и `checked_base` должны быть
заданы вызывающим процессом:

```bash
# CHANGED_SOURCE_PRODUCER_BEGIN
if ! changed_source_json="$(
  python3 - "$repo" "$checked_base" <<'PY'
import json
import os
import subprocess
import sys

repo, checked_base = sys.argv[1:]


def git_stdout(args):
    completed = subprocess.run(
        ["git", "-C", repo, *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        sys.stderr.buffer.write(completed.stderr)
        raise SystemExit(completed.returncode)
    return completed.stdout


def nul_paths(args):
    output = git_stdout(args)
    records = output.split(b"\0")
    if records[-1:] == [b""]:
        records.pop()
    if any(record == b"" for record in records):
        raise SystemExit(1)
    paths = [os.fsdecode(record) for record in records]
    if any(
        os.path.isabs(path)
        or path == ".."
        or path.startswith("../")
        or "/../" in path
        for path in paths
    ):
        raise SystemExit(1)
    return paths


resolved_base = git_stdout(
    ["rev-parse", "--verify", "--end-of-options", f"{checked_base}^{{commit}}"]
).strip()
if (
    len(resolved_base) not in (40, 64)
    or any(byte not in b"0123456789abcdef" for byte in resolved_base.lower())
    or checked_base.lower().encode("ascii", errors="strict") != resolved_base.lower()
):
    raise SystemExit(1)
base_oid = resolved_base.decode("ascii")


diff_flags = ["--name-only", "--no-renames", "--no-ext-diff", "-z"]
paths = nul_paths(["diff", *diff_flags, base_oid, "HEAD", "--"])
paths.extend(nul_paths(["diff", "--cached", *diff_flags, "HEAD", "--"]))
paths.extend(nul_paths(["diff", *diff_flags, "--"]))
paths.extend(nul_paths(["ls-files", "--others", "--exclude-standard", "-z", "--"]))
print(json.dumps(sorted(set(paths)), ensure_ascii=True, separators=(",", ":")))
PY
)"; then
  changed_source_json=
  exit 1
fi
printf '%s\n' "$changed_source_json"
# CHANGED_SOURCE_PRODUCER_END
```

Ненулевой код любой команды, неверная база, недекодируемый результат или
невозможность однозначно отнести путь дают `BEHAVIOR_PROBE_BLOCKED`.
`checked_base` принимается только как полный exact commit OID, совпавший с
результатом `rev-parse --verify --end-of-options`; ref, сокращённый SHA и
значение, начинающееся с `--`, не открывают пробу.
Пустой массив допустим только для прямо запрошенной полной пробы неизменённой
библиотеки. Не заменяйте producer выводом уже staged-файлов или списком из
памяти.

### Привязка К Проверяемому Tree

Для гейта будущего commit или PR после определения охвата выполните
окончательный точечный staging доказанного scope до живых проб. В общем
worktree это допустимо только в уже авторизованном Git-процессе без mixed WIP;
иначе подготовьте exact staged candidate в одноразовой копии. Не запускайте
пробу на worktree-файле, если index хранит для будущего commit другие bytes или
mode.

До проб сохраните приватный `layer_state_vector`:

- полный `head_oid`;
- заранее выбранный `commit_transition` (`CREATE` или `AMEND`) и точный
  упорядоченный `expected_parent_oids`: для `CREATE` это будущие parents из
  `HEAD` и доказанного `MERGE_HEAD`, для `AMEND` — parents заменяемого commit;
- `index_tree_oid` из успешного `git write-tree`; это же `tested_tree` позднего
  Git-гейта;
- доказанное отсутствие index stages 1–3 по `git ls-files -u`;
- для каждого пути `batch_changed_source` — `head_entry` и stage-0
  `index_entry` как `mode + blob_oid` либо `ABSENT`, а также `worktree_entry`
  как `mode + SHA-256(content)` либо `DELETED`.

Для каждого regular file будущего commit докажите, что index соответствует
текущему worktree после Git normalization: unstaged diff отсутствует, mode
совпадает, а index blob равен объекту, вычисленному командой
`git -C "$repo" hash-object --path="$path" -- "$path"`. Новые untracked
intended-файлы сначала входят в producer output, а затем обязаны попасть в
exact index. Ошибка
`write-tree`, unmerged entry, остаточный unstaged/untracked intended path или
недоказуемое соответствие дают `BEHAVIOR_PROBE_BLOCKED`.

Полный `layer_state_vector` входит в `batch_scope_fingerprint`, а его точная
проекция на пути строки — в `source_scope_fingerprint`. Поэтому одинаковые
path set и worktree hash не скрывают изменение bytes или mode в `HEAD` либо
index. Любое изменение `head_oid`, `index_tree_oid` или entry после пробы
аннулирует пакет до нового доказательства по правилам ниже.

Из `batch_changed_source` назначьте каждой строке все пути внутри каталога её
target и каждый общий launch-path, способный влиять на неё. Путь общего
контракта назначьте всем затронутым строкам; неизвестное влияние означает
`BLOCKED`. Остальные repo-paths можно исключить из строк только с отдельным
проверяемым доказательством, что они не создают и не меняют skill, общий
запуск, маршрут или источник критериев.

Зафиксируйте приватную `batch_attribution`: каждый путь
`batch_changed_source` связан с одной или несколькими строками либо ровно один
раз помещён в `batch_excluded_source` вместе с доказательством. Пересечение
этих двух множеств, путь вне обоих или назначение несуществующей строке дают
`BEHAVIOR_PROBE_BLOCKED`. Так новый untracked `SKILL.md`, `skill.yaml`,
`agents/openai.yaml`, reference, script, asset или example не может исчезнуть
между глобальным снимком и строкой target.

Вычислите приватный `batch_scope_fingerprint` по `checked_base`, режиму и
полному списку строк пакета, `layer_state_vector`, а также каждому batch-path с
его состоянием `FILE`/`SYMLINK`/`DELETED`, Git mode, content hash и точным
списком назначенных строк либо текстом доказательства из
`batch_excluded_source`. Используйте ту же
каноническую UTF-8 JSON и SHA-256 запись, что для row-level fingerprint ниже.
Перед финальным гейтом заново получите producer output, проверьте полное
разложение и пересчитайте fingerprint. Несовпадение требует пересчитать охват;
необъяснимое расхождение даёт `BEHAVIOR_PROBE_BLOCKED`.

Приватный пакет хранит поля:

| Поле | Что Фиксировать |
| --- | --- |
| `batch_changed_source` | Полный output доказанного producer. |
| `batch_attribution` | Для каждого не исключённого пути — полный отсортированный список строк, которым он назначен. |
| `batch_excluded_source` | Каждый не назначенный строкам путь и отдельное проверяемое доказательство исключения. |
| `layer_state_vector` | `head_oid`, `commit_transition`, `expected_parent_oids`, `index_tree_oid`, отсутствие unmerged и entries `HEAD`/index/worktree каждого batch-path. |
| `batch_scope_fingerprint` | Приватный digest базы, режима, списка строк, состояния и Git mode каждого пути, а также его назначения либо доказательства исключения. |

## Приватная Рабочая Строка

До запуска создайте по одной строке на skill:

| Поле | Что Фиксировать |
| --- | --- |
| `skill` | Публичное имя skill. |
| `changed_source` | Полный отсортированный набор путей target и общих launch-paths, выведенный из доказанного `batch_changed_source` относительно `checked_base`. |
| `scope_reason` | Правило включения и точные пути из `changed_source`, способные изменить запуск, маршрут, критерии или первый ответ; общей фразы «skill изменён» недостаточно. |
| `phrase_source` | Пользовательский запрос, registry или synthetic example. |
| `trigger_phrase` | Точная фраза только в приватном рабочем пакете. |
| `criteria` | От одного до трёх наблюдаемых признаков правильного первого ответа. |
| `forbidden_behavior` | Одно проверяемое запрещённое поведение. |
| `probe_contract_fingerprint` | Приватный keyed digest источника фразы, точной фразы, упорядоченных критериев и запрещённого поведения. |
| `checked_base` | SHA базы, относительно которой определён охват либо доказана эквивалентность источников строки. |
| `required_source` | Полный отсортированный список repo-relative источников, которые обязаны быть загружены для строки: `SKILL.md`, всегда `known-exceptions.yaml`, каждый путь из `scope_reason` и маршрутизированные для фразы references/scripts/assets или общий контракт. |
| `excluded_changed_source` | Остаток `changed_source`; для каждого пути хранится отдельное проверяемое доказательство отсутствия влияния на запуск, маршрут, phrase/criteria или первый ответ. |
| `source_scope_fingerprint` | Приватный digest базы, проекции `layer_state_vector`, полного `changed_source`, точного `scope_reason`, каждого исключённого пути с доказательством и полного `required_source`. |
| `loaded_source` | Отсортированный список публичных repo-relative путей, фактически загруженных для target; без локальных абсолютных путей и содержимого файлов. |
| `target_fingerprint` | Обезличенный digest точного состояния полного `loaded_source` после доказательства `required_source ⊆ loaded_source`: пути, Git modes и content hashes, но не сырые файлы, фразы, критерии или ответы. |
| `status` | `BEHAVIOR_PROBE_PASS`, `BEHAVIOR_PROBE_FAIL` или `BEHAVIOR_PROBE_BLOCKED`. |
| `failure_class` | Один класс ниже для `FAIL`/`BLOCKED`; для `PASS` — `—`. |

Проверяемому агенту передавайте только целевой skill и `trigger_phrase`.
Каждая строка получает отдельный свежий контекст; критерии, соседние строки и
предыдущие результаты не передавайте.

До запуска получите `changed_source` только из полного доказанного
`batch_changed_source` относительно `checked_base`, затем
разложите его без пропусков и пересечений на пути из `scope_reason` и
`excluded_changed_source`. Для каждого исключённого пути нужно доказать, что он
не может менять запуск, маршрут, источник phrase/criteria или первый ответ.
`SKILL.md`, `known-exceptions.yaml`, `skill.yaml`, `agents/openai.yaml`, общий
launch-contract и изменённый используемый reference/script/asset исключать
нельзя. Изменённый example тоже обязателен, если он служит источником фразы или
критериев текущей строки. Неизвестный или неучтённый путь даёт
`BEHAVIOR_PROBE_BLOCKED`.

Затем выведите `required_source` из точных путей `scope_reason` и действующего
контракта target. `known-exceptions.yaml` входит в `required_source` для каждой
строки независимо от причины включения skill: определить отсутствие
подходящего `do_next_time` без чтения файла нельзя. После ответа докажите, что
каждый `required_source` входит в фактический `loaded_source`, и только затем
вычисляйте `target_fingerprint`. Неполный или недоказуемый source scope даёт
`BEHAVIOR_PROBE_BLOCKED` с классом `TASK_SPECIFIC`, даже если наблюдаемый ответ
похож на правильный.

После разложения вычислите `source_scope_fingerprint` по канонической записи:
`checked_base`; `head_oid`, `index_tree_oid` и доказанное отсутствие unmerged;
проекция `head_entry`, `index_entry` и `worktree_entry` на каждый путь строки;
отсортированный `changed_source`, где каждый путь связан с Git mode и content
hash текущих Git-эквивалентных bytes либо явным маркером `DELETED` с
предыдущим Git mode;
правило и точные пути `scope_reason`; каждый путь
`excluded_changed_source` вместе с текстом его проверяемого доказательства;
полный `required_source`. Для symlink в batch или excluded scope хешируйте
bytes его link target, а не содержимое файла назначения, и фиксируйте mode
`120000`. Symlink нельзя включать в `required_source` или `loaded_source` и
нельзя передавать target-агенту: даже ссылка внутрь repo может быть заменена
между проверкой и чтением. Нечитаемый путь, submodule, special file,
неподдерживаемый Git mode, неизвестное состояние или удаление без однозначного
маркера дают `BEHAVIOR_PROBE_BLOCKED`.

Каноническая запись — UTF-8 JSON с отсортированными ключами; массивы путей
сортируются по repo-relative path, а состояния `FILE`, `SYMLINK` и `DELETED`
задаются явными полями. Для regular file допустимы только modes `100644` и
`100755`; смена mode при неизменных bytes меняет fingerprint. Content hash и
итоговый fingerprint вычисляйте через SHA-256; не склеивайте значения
неоднозначной строкой с разделителями.

Этот fingerprint хранится приватно и пересчитывается из текущего worktree
непосредственно перед финальным гейтом. Поэтому изменение содержимого ранее
исключённого example, reference или другого пути, а также изменение самого
доказательства исключения аннулирует строку, даже если список имён файлов не
изменился.

Свежий контекст не означает право менять общий target. Если первый ход skill
может выполнить commit, stash, rebase, запись файла, установку, публикацию или
другое внешнее действие, дайте ему одноразовую изолированную копию точного
target без production credentials и без push-доступа к настоящему remote.
Локальный disposable remote допустим для проверки Git-поведения. Общий
worktree пользователя и реальная внешняя система в пробе не используются.
Если точное состояние нельзя перенести в такую среду или первый ход нельзя
безопасно наблюдать read-only, поставьте `BEHAVIOR_PROBE_BLOCKED` и продолжите
остальные строки пакета.

### Нерекурсивная Строка Оркестратора

Если реальный внешний охват включает `add-team-skill`, проверьте его строго в
два уровня:

1. Внешний пакет хранит строку реального `add-team-skill` и загружает в неё
   точный кандидат, подтверждённый его `loaded_source`,
   `source_scope_fingerprint` и `target_fingerprint`.
2. Только этой строке дайте одноразовый внутренний fixture от того же
   `checked_base`: в его diff существенно изменены не меньше двух других
   тестовых skills, а `add-team-skill` отсутствует. Первый ответ кандидата
   должен вычислить весь внутренний охват и запустить его независимые строки.

Третьего уровня нет: внутренний fixture не содержит пакетного оркестратора, а
его строки не запускают ещё один пакет. По первому ответу на внутреннем fixture
внешняя строка `add-team-skill` получает обычный `BEHAVIOR_PROBE_PASS`,
`BEHAVIOR_PROBE_FAIL` или `BEHAVIOR_PROBE_BLOCKED`. Даже после её `FAIL` или
`BLOCKED` внешний пакет продолжает остальные строки реального охвата. Если
точность кандидата, база fixture, минимум две другие строки, отсутствие
`add-team-skill` в diff или граница двух уровней не доказаны, поставьте внешней
строке `BEHAVIOR_PROBE_BLOCKED`.

После доказательства полного source scope и `source_scope_fingerprint`
вычислите `target_fingerprint`
детерминированно по отсортированным repo-relative путям из `loaded_source` и
Git mode и content hash каждого фактически загруженного regular file. Для
незакоммиченного файла хешируйте текущее содержимое и mode рабочего дерева, а
не blob из `HEAD`. В строке сохраняйте только итоговый digest: он подтверждает
равенство состояний, но не раскрывает содержимое.

`probe_contract_fingerprint` вычисляйте как keyed digest канонической записи:
`phrase_source`, точная `trigger_phrase`, `criteria` в исходном порядке и
`forbidden_behavior`. Используйте приватный ключ конкретного пакета; ключ,
каноническую запись и fingerprint храните только вместе с приватной рабочей
строкой. Обычный неконтролируемый hash короткой фразы не считается
privacy-safe: его можно подобрать по словарю.

## Классы Сбоев

- `NOTICE_ONLY` — ответ ограничился уведомлением и не начал полезную работу;
- `PROMISE_ONLY` — ответ обещал будущие действия, но не сделал первый
  содержательный шаг;
- `BLOCKING_CONSENT` — ответ запросил согласие на применение внутреннего метода;
- `REDUNDANT_CONFIRMATION` — ответ повторно открыл уже зафиксированный выбор или
  полномочие;
- `USER_AS_OBSERVER` — ответ переложил на пользователя наблюдение, доступное
  агенту безопасным инструментом;
- `TASK_SPECIFIC` — нарушен иной предметный критерий либо независимая проба
  заблокирована по причине вне пяти общих классов.

После отдельного `FAIL` или `BLOCKED` продолжайте пакет. Это позволяет увидеть
все дефекты за один проход, но не ослабляет гейт: commit, push и PR запрещены,
пока каждая строка охвата не получила актуальный `BEHAVIOR_PROBE_PASS`.

## Когда Строка Устаревает

- если база продвинулась, сначала сравните старую и новую базы и пересчитайте
  охват; аннулируйте только строки, затронутые изменением их `changed_source`,
  `scope_reason`, `excluded_changed_source`, `required_source`, `loaded_source`,
  `source_scope_fingerprint` или общего для них контракта;
- после переноса на новый `checked_base` заново получите exact staged
  `tested_tree`, producer output, атрибуцию и `layer_state_vector` по позднему
  Git-гейту. Незатронутую строку можно перепривязать без новой пробы, только
  если различия её канонических входов ограничены доказанными новыми
  `checked_base`, `head_oid`, `expected_parent_oids` и `index_tree_oid`,
  `commit_transition` остаётся прежним, а все row-level entries, paths, modes,
  hashes, назначения, доказательства, `required_source`,
  `loaded_source`, `target_fingerprint` и контракт пробы прежние. Сохраните
  новые base-bound fingerprints; равенства старого и нового digest не
  требуйте. Любое предметное различие аннулирует затронутую строку, а
  недоказуемость даёт `BEHAVIOR_PROBE_BLOCKED`;
- заново полученный `batch_changed_source`, `batch_attribution`, состояние
  любого batch-path или доказательство из `batch_excluded_source` не совпадает
  с сохранённым `batch_scope_fingerprint` — пересчитайте глобальный охват,
  повторно докажите полное разложение и аннулируйте строки, чьи назначения или
  источники изменились; неизвестное влияние даёт `BEHAVIOR_PROBE_BLOCKED`;
- текущая проекция `layer_state_vector`, content hash/маркер удаления любого
  row-path или доказательство из `excluded_changed_source` не совпадает с
  сохранённым `source_scope_fingerprint` — аннулируйте эту строку;
- текущий `required_source` не покрыт `loaded_source`, либо текущий
  `loaded_source` или заново вычисленный `target_fingerprint` не совпадает с
  сохранённым — аннулируйте строку и поставьте `BEHAVIOR_PROBE_BLOCKED` до
  полной загрузки;
- источник фразы, точная фраза, порядок или содержание критериев либо
  запрещённое поведение изменились и заново вычисленный
  `probe_contract_fingerprint` не совпал — аннулируйте эту строку;
- изолированная копия не соответствует `source_scope_fingerprint` и
  `target_fingerprint` — аннулируйте эту строку;
- нерекурсивный fixture строки `add-team-skill` снова включает оркестратор в
  свой diff — аннулируйте эту строку;
- изменился общий контракт запуска или поведения библиотеки — аннулируйте весь
  пакет;
- исправление после `FAIL` всегда требует нового свежего контекста.

После commit разрешён ровно один переход fingerprints без повторной модельной
пробы. Упорядоченный список parents нового commit должен точно совпасть с
заранее сохранённым `expected_parent_oids` для выбранного
`commit_transition`; не подменяйте `AMEND` правилом `first parent = precommit
head_oid`. Tree нового commit, precommit `index_tree_oid` и `tested_tree`
должны быть одним OID. После commit
`git write-tree` должен вернуть тот же tree, а staged, unstaged, untracked и
unmerged состояния — отсутствовать. Для каждого пути postcommit `head_entry` и
`index_entry` должны в точности равняться precommit `index_entry`, а
`worktree_entry` — precommit `worktree_entry`; для удаления ожидаемым entry
является `ABSENT`. Разрешены только новый `head_oid` и такая ожидаемая замена
старого `head_entry` проверенным index-entry. Если база, batch attribution,
sources, probe contract или любое другое поле изменились, старый `PASS` не
переносится. Только после полного receipt пересчитайте `layer_state_vector` и
сохраните новые fingerprints; иначе commit считается новым кандидатом и
требует новой пробы.

Пакет не открывает commit, push или PR, пока заново вычисленный
`batch_scope_fingerprint` не совпал с сохранённым, полное разложение
`batch_changed_source` не доказано и каждая строка не имеет актуальный `PASS`.

`BEHAVIOR_PROBE_PASS` считается актуальным, только если одновременно совпадают
текущий `checked_base`, полный `changed_source`, доказано его полное
непересекающееся разложение на `scope_reason` и `excluded_changed_source`,
совпадает полный `required_source` и заново вычисленный
`source_scope_fingerprint` с текущей проекцией `layer_state_vector`, доказано
`required_source ⊆ loaded_source`,
совпадают полный `loaded_source`, `target_fingerprint` и
`probe_contract_fingerprint`. При
движении базы сначала выполните описанную выше проверку затронутости и лишь
затем перепривяжите незатронутые строки к новому SHA. Любое иное расхождение
означает, что наблюдавшийся ответ относится к другому состоянию; строка не
открывает commit, push или PR до новой независимой пробы. Если точный состав
загруженных источников, digest или отсутствие влияния новой базы установить
нельзя, используйте `BEHAVIOR_PROBE_BLOCKED`.

## Что Можно Публиковать

Сырые пользовательские запросы, точные приватные фразы, критерии и ответы
модели, `layer_state_vector`, а также `batch_scope_fingerprint`,
`source_scope_fingerprint`, `target_fingerprint` и
`probe_contract_fingerprint` не коммитите и не вставляйте в PR. В
публичном summary допустимы только:

- размер и публичный список охвата;
- счётчики `PASS`, `FAIL` и `BLOCKED`;
- публичные имена skills;
- классы обнаруженных сбоев;
- обезличенный synthetic example или regression test, добавленный как исправление.
