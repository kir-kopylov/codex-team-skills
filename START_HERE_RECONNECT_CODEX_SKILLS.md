# Начать Здесь: Перевести Старую Установку

Этот путь нужен только компьютеру, где Team Skills раньше подключались локальной копией или фоновым обновлением. Переход выполняет агент локальными командами. Новый скачиваемый очиститель не используется.

## 1. Снимок Без Изменений

Сначала сохрани в ответе пользователю:

- вывод `codex --version` и `codex plugin list --json`;
- наличие в `~/.codex/config.toml` точного управляемого блока от `# BEGIN codex-team-skills managed block` до соответствующего `END`;
- наличие `~/plugins/team-skills`, `~/.codex/plugins/cache/codex-team-skills` и marketplace-файла;
- на Windows — задачу `Codex Team Skills Auto Update` и `%LOCALAPPDATA%\CodexTeamSkills`;
- на macOS — LaunchAgent `com.codex-team-skills.autoupdate` и `~/Library/Application Support/CodexTeamSkills`.

Не публикуй содержимое личных файлов, токены и абсолютный домашний путь.

## 2. Сначала Штатное Удаление

Если команды доступны, выполни:

```powershell
codex plugin remove team-skills@codex-team-skills --json
codex plugin marketplace remove codex-team-skills --json
```

Отсутствующий объект допустим. Ошибка разбора конфигурации не разрешает массовое удаление: переходи к точечной проверке ниже.

## 3. Проверка Владения Перед Очисткой

Для каждого объекта сначала докажи принадлежность:

- управляемый блок должен иметь точные границы и содержать только marketplace `codex-team-skills` и plugin `team-skills@codex-team-skills`;
- `~/plugins/team-skills` должен быть обычным каталогом, а `.codex-plugin/plugin.json` внутри — иметь `name` = `team-skills`;
- cache удаляется только по точному пути `~/.codex/plugins/cache/codex-team-skills` после доказанной идентичности plugin;
- Windows-задача должна иметь точное имя `Codex Team Skills Auto Update`, а её действие — указывать внутрь `%LOCALAPPDATA%\CodexTeamSkills`;
- macOS plist должен иметь точный `Label` = `com.codex-team-skills.autoupdate`, а `ProgramArguments` — указывать внутрь `~/Library/Application Support/CodexTeamSkills`;
- каталог поддержки не должен быть ссылкой или reparse point; допустимы только доказанные файлы старого Team Skills updater.

Если имя, путь, границы, manifest, действие задачи или состав каталога не совпали, остановись без удаления и покажи расхождение пользователю.

## 4. Конфигурация Codex

Если штатная команда не удалила старую запись, работай только с `~/.codex/config.toml`. Должна существовать ровно одна пара точных границ `# BEGIN codex-team-skills managed block` и `# END codex-team-skills managed block`, а внутри — только секции marketplace `codex-team-skills` и plugin `team-skills@codex-team-skills`.

Сохрани резервную копию рядом с файлом, удали весь доказанный блок вместе с его границами и атомарно замени исходный файл. Остальной TOML сохрани байт-в-байт. При второй паре границ, незакрытом блоке, дополнительных секциях или ошибке записи остановись без удаления.

## 5. Marketplace JSON

Читай старый `~/.agents/plugins/marketplace.json` как `UTF-8` с допустимым BOM. Удали только запись с `name` = `team-skills`, если её source указывает на доказанный старый plugin.

Если в файле есть другие plugins, сохрани их без изменений. Результат запиши атомарно как `UTF-8 без BOM`. Перед заменой сохрани локальную резервную копию рядом с исходным файлом. Если JSON повреждён или source неоднозначен, остановись без удаления.

## 6. Подключение Штатного Marketplace

После доказанного удаления старых следов выполни:

```powershell
codex plugin marketplace add kir-kopylov/codex-team-skills --ref main --json
codex plugin add team-skills@codex-team-skills --json
```

Проверь `codex plugin list --json`, полностью перезапусти Codex и в новой задаче проверь наличие `team-skills:production-forensic-auditor`.
