# Быстрый Старт

Если вы просто хотите пользоваться командными skills, начните с [SEND_TO_COLLEAGUE.md](SEND_TO_COLLEAGUE.md). Codex определит вашу систему и даст одну команду для установки.

## User Mode: Установить Готовый Plugin

Windows:

```powershell
$u="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.ps1"; $p="$env:TEMP\install-team-skills.ps1"; Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $p; powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p
```

macOS:

```bash
curl -fsSL -o /tmp/install-team-skills.command https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.command && chmod +x /tmp/install-team-skills.command && /tmp/install-team-skills.command
```

После установки перезапустите Codex, чтобы он перечитал локальный plugin и скиллы.

## Проверить Установку

После перезапуска Codex напишите:

```text
Покажи, какие командные skills доступны.
```

Ожидаемое поведение: Codex видит plugin `team-skills`, кратко объясняет доступные skills и показывает первую фразу для запуска каждого готового skill.

## Обновление И Удаление

Автообновление включается установщиком и запускается раз в двое суток. Если обновление не удалось, старая рабочая версия остаётся на месте.

Для проверки статуса:

- Windows: `%LOCALAPPDATA%\CodexTeamSkills\bin\team-skills-status.ps1`
- macOS: `~/Library/Application Support/CodexTeamSkills/bin/team-skills-status.command`

Для удаления:

- Windows: `%LOCALAPPDATA%\CodexTeamSkills\bin\uninstall-team-skills.ps1`
- macOS: `~/Library/Application Support/CodexTeamSkills/bin/uninstall-team-skills.command`

## Author Mode: Добавить Новый Skill

Если вы хотите добавлять свои skills в общее repo, нужен GitHub workflow:

```bash
python scripts/new_skill.py my-skill --owner @yourname --summary "Коротко: что делает скилл"
python -m pytest
```

Перед переводом скилла в статус `team-ready` обновите `catalog.md` и откройте Pull Request.

## Локальная Разработка Plugin

Если вы уже работаете из локальной копии repo и хотите переустановить plugin напрямую:

```bash
./scripts/install_plugin.sh
```

Этот путь нужен авторам и разработчикам repo, а не обычным пользователям.

## Приватность

Этот repo рассчитан на публичный доступ для чтения. Не добавляйте сюда сырые данные клиентов, токены, приватные ключи, pasteboard/download paths, личные файлы и случайно вставленный приватный контекст.
