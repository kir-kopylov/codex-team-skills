# Гид Для Организатора Onboarding

Эта инструкция для человека, который помогает коллегам подключиться к общему хранилищу Codex skills.

Коллеге по-прежнему отправляйте один файл: [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md). Разница в том, что обычный пользователь больше не проходит ручное скачивание repo и не устанавливает plugin через отдельное desktop-приложение.

## Два Режима

**User mode** — для коллег, которые только пользуются skills. Им нужен Codex Desktop и один установщик. GitHub аккаунт, локальная копия repo и Pull Request не нужны.

**Author mode** — для коллег, которые хотят добавить свои skills в общее хранилище. Им нужен GitHub аккаунт, локальная рабочая копия repo, branch, tests и Pull Request.

## User Mode: Что Делает Коллега

1. Открывает Codex Desktop.
2. Загружает [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md).
3. Отвечает, какая у него система: Windows или macOS.
4. Запускает одну команду, которую даст Codex.
5. Перезапускает Codex.
6. Проверяет фразой: `Покажи, какие командные skills доступны.`

Ситуация успеха: plugin `team-skills` установлен, автообновление включено, коллега видит доступные командные skills.

## Что Делает Установщик

Установщик скачивает не сырой `main`, а последний подписанный release:

- `latest.json` — подписанный pointer на последний проверенный подписанный release (неизменяемый тег не гарантируется платформой);
- `manifest.json` — подписанная schema с `product_version`, `runtime_version`, `release_id`, commit, channel и checksum assets;
- `team-skills-bundle.zip` — plugin `team-skills`;
- служебные scripts для bootstrap, обновления, repair, статуса и удаления.

Перед заменой активного plugin установщик проверяет подпись metadata, checksum assets, распаковывает bundle во временную папку, проверяет `.codex-plugin/plugin.json`, регистрирует local marketplace в Codex config и только потом заменяет локальную версию. После успешной замены updater инвалидирует snapshot `~/.codex/plugins/cache/codex-team-skills`, потому что перезапуск Codex должен перечитывать свежий plugin, а не старый persistent cache.

## Auto Update

Автообновление включается без выбора пользователя:

- Windows: user-level Windows Task Scheduler, задача `Codex Team Skills Auto Update`;
- macOS: user-level LaunchAgent `com.codex-team-skills.autoupdate`;
- интервал: раз в двое суток.

Если интернет недоступен, подпись невалидна или bundle повреждён, текущий рабочий plugin остаётся на месте. Следующая попытка будет при очередном запуске автообновления.

## Release Signing

Публикация release после merge требует GitHub Actions secret `TEAM_SKILLS_SIGNING_KEY_PEM`. Он должен содержать приватный ключ, соответствующий публичному ключу `installer/team-skills-public-key.pem`. Без этого CI должен падать на publish-step, потому что unsigned release не должен становиться источником автообновления.

Честно про bus-factor: приватный ключ хранится только офлайн и как GitHub Actions secret `TEAM_SKILLS_SIGNING_KEY_PEM`, и сейчас до него дотягивается только владелец repo. Это единая точка отказа: если ключ потерян или скомпрометирован, новые подписанные release выпускать некем. Восстановление — это смена доверенного якоря, а не починка старого ключа. Порядок такой: сгенерировать новую пару ключей, заменить значение secret `TEAM_SKILLS_SIGNING_KEY_PEM` в настройках repo, закоммитить новый публичный ключ `installer/team-skills-public-key.pem`, обновить закреплённый отпечаток `EXPECTED_PUBLIC_KEY_SHA256` в `installer/update-team-skills.sh` и `installer/update-team-skills.ps1` на sha256 нового ключа (иначе после переустановки обновления упрут в проверку якоря доверия) и опубликовать свежий подписанный release. Коллеги подхватят новый якорь доверия, заново запустив установщик; до этого их клиент остаётся на старой подписи. Деградация при этом штатная: как уже описано выше, если подпись невалидна, старый рабочий plugin остаётся на месте, так что подмена ключа не ломает текущие установки, а лишь откладывает новые обновления до повторного запуска установщика.

## Команды Поддержки

Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\team-skills-status.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\update-team-skills.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\update-team-skills.ps1" -RepairInstall
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\uninstall-team-skills.ps1"
```

macOS:

```bash
"$HOME/Library/Application Support/CodexTeamSkills/bin/team-skills-status.command"
"$HOME/Library/Application Support/CodexTeamSkills/bin/update-team-skills.sh"
"$HOME/Library/Application Support/CodexTeamSkills/bin/update-team-skills.sh" --repair-install
"$HOME/Library/Application Support/CodexTeamSkills/bin/uninstall-team-skills.command"
```

## Что Отправить Коллеге

Отправьте файл [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md) и короткий текст:

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
Система сама раз в двое суток ставит последнюю подписанную версию командных skills. Если обновление не удалось, старая рабочая версия остаётся на месте. После успешного обновления нужен перезапуск Codex, чтобы новая runtime-версия skill стала видна.
```
