# Гид Для Организатора Onboarding

Эта инструкция для человека, который помогает коллегам подключиться к общему хранилищу Codex skills.

Коллеге по-прежнему отправляйте один файл: [SEND_TO_COLLEAGUE.md](SEND_TO_COLLEAGUE.md). Разница в том, что обычный пользователь больше не проходит ручное скачивание repo и не устанавливает plugin через отдельное desktop-приложение.

## Два Режима

**User mode** — для коллег, которые только пользуются skills. Им нужен Codex Desktop и один установщик. GitHub аккаунт, локальная копия repo и Pull Request не нужны.

**Author mode** — для коллег, которые хотят добавить свои skills в общее хранилище. Им нужен GitHub аккаунт, локальная рабочая копия repo, branch, tests и Pull Request.

## User Mode: Что Делает Коллега

1. Открывает Codex Desktop.
2. Загружает [SEND_TO_COLLEAGUE.md](SEND_TO_COLLEAGUE.md).
3. Отвечает, какая у него система: Windows или macOS.
4. Запускает одну команду, которую даст Codex.
5. Перезапускает Codex.
6. Проверяет фразой: `Покажи, какие командные skills доступны.`

Ситуация успеха: plugin `team-skills` установлен, автообновление включено, коллега видит доступные командные skills.

## Что Делает Установщик

Установщик скачивает не сырой `main`, а последний проверенный release-bundle:

- `manifest.json` — версия, commit, дата сборки и checksum;
- `team-skills-bundle.zip` — plugin `team-skills`;
- служебные scripts для обновления, статуса и удаления.

Перед заменой активного plugin установщик проверяет checksum, распаковывает bundle во временную папку, проверяет `.codex-plugin/plugin.json` и только потом заменяет локальную версию.

## Auto Update

Автообновление включается без выбора пользователя:

- Windows: user-level Windows Task Scheduler, задача `Codex Team Skills Auto Update`;
- macOS: user-level LaunchAgent `com.codex-team-skills.autoupdate`;
- интервал: раз в двое суток.

Если интернет недоступен или bundle повреждён, текущий рабочий plugin остаётся на месте. Следующая попытка будет при очередном запуске автообновления.

## Команды Поддержки

Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\team-skills-status.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\update-team-skills.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\uninstall-team-skills.ps1"
```

macOS:

```bash
"$HOME/Library/Application Support/CodexTeamSkills/bin/team-skills-status.command"
"$HOME/Library/Application Support/CodexTeamSkills/bin/update-team-skills.sh"
"$HOME/Library/Application Support/CodexTeamSkills/bin/uninstall-team-skills.command"
```

## Что Отправить Коллеге

Отправьте файл [SEND_TO_COLLEAGUE.md](SEND_TO_COLLEAGUE.md) и короткий текст:

```text
Загрузи этот .md файл в Codex Desktop, нажми отправить и следуй инструкциям.

Codex определит твою систему, даст одну команду для установки и включит автообновление командных skills.
```

## Author Mode: Если Коллега Хочет Добавлять Skills

Только для авторов нужен GitHub workflow:

1. GitHub аккаунт.
2. Локальная рабочая копия repo `codex-team-skills`.
3. Branch для изменения.
4. Черновик через `python scripts/new_skill.py`.
5. Заполненные `SKILL.md`, `skill.yaml`, `examples/`.
6. `python -m pytest`.
7. Pull Request.

Ситуация успеха: Pull Request создан, CI проходит, ревьюер видит цель skill, аудиторию, ограничения и примеры.

## Короткое Объяснение Для Коллег

```text
Система сама раз в двое суток ставит последнюю проверенную версию командных skills. Если обновление не удалось, старая рабочая версия остаётся на месте.
```
