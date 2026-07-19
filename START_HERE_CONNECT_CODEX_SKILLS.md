# Начать Здесь: Подключить Командные Skills

Этот файл можно загрузить в Codex Desktop и написать: «Установи эту библиотеку skills и проверь результат».

Codex, подключи публичный plugin `team-skills` штатными командами marketplace. Не скачивай и не запускай установочные скрипты, не меняй настройки Defender и не добавляй исключения безопасности.

## Первый Шаг

В терминале выполни:

```powershell
codex --version
codex plugin --help
```

Нужен Codex `0.144.4` или новее и доступная группа команд `codex plugin`. Если условие не выполнено, остановись и попроси пользователя обновить Codex. Не используй запасной способ через удалённый скрипт.

Перед установкой проверь, нет ли признаков старого подключения: `~/plugins/team-skills`, управляемого блока `codex-team-skills`, старой фоновой задачи или старого каталога поддержки. Если признаки есть, перейди к [START_HERE_RECONNECT_CODEX_SKILLS.md](START_HERE_RECONNECT_CODEX_SKILLS.md).

## Чистая Установка

```powershell
codex plugin marketplace add kir-kopylov/codex-team-skills --ref main --json
codex plugin add team-skills@codex-team-skills --json
```

Ситуация успеха:

- первая команда вернула `marketplaceName` = `codex-team-skills`;
- вторая вернула `pluginId` = `team-skills@codex-team-skills`, путь установки и semver;
- команда `codex plugin list --json` показывает plugin как `installed` и `enabled`.

После этого попроси пользователя полностью закрыть и снова открыть Codex. Не называй runtime проверенным до перезапуска.

## Проверка После Перезапуска

В новой задаче проверь только список доступных skills: есть ли `team-skills:production-forensic-auditor`. Не подменяй эту проверку наличием файлов на диске.

## Обновление

```powershell
codex plugin marketplace upgrade codex-team-skills --json
codex plugin add team-skills@codex-team-skills --json
```

Успех: `errors` пуст, повторная установка вернула актуальную semver. Затем пользователь полностью перезапускает Codex и повторяет проверку skill.

## Удаление

```powershell
codex plugin remove team-skills@codex-team-skills --json
codex plugin marketplace remove codex-team-skills --json
```

После удаления `codex plugin list --json` не должен показывать установленный `team-skills`. Затем пользователь перезапускает Codex.

## Если Что-то Не Совпало

Покажи пользователю точную команду, код возврата и короткий вывод без секретов. Не удаляй неоднозначные каталоги, не отключай защиту и не повторяй установку вслепую.
