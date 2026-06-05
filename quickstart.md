# Быстрый Старт

Если вы просто хотите пользоваться командными skills, начните с [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md). Codex определит вашу систему и даст одну команду для установки.

## User Mode: Установить Готовый Plugin

Windows:

```powershell
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $u="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.ps1"; $p="$env:TEMP\install-team-skills.ps1"; $b=(New-Object System.Net.WebClient).DownloadData($u); $s=[System.Text.Encoding]::UTF8.GetString($b); if($s.Length -gt 0 -and $s[0] -eq [char]0xFEFF){$s=$s.Substring(1)}; $enc=New-Object System.Text.UTF8Encoding($true); [System.IO.File]::WriteAllText($p,$s,$enc); powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p
```

macOS:

```bash
curl -fsSL -o /tmp/install-team-skills.command https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.command && chmod +x /tmp/install-team-skills.command && /tmp/install-team-skills.command
```

Установщик берёт signed `latest.json`, signed `manifest.json`, проверяет checksum assets, регистрирует локальный marketplace в Codex config и просит перезапустить Codex. После установки перезапустите Codex, чтобы он перечитал локальный plugin и скиллы.

## Проверить Установку

После перезапуска Codex напишите:

```text
Покажи, какие командные skills доступны.
```

Ожидаемое поведение: Codex видит plugin `team-skills`, кратко объясняет доступные skills и показывает первую фразу для запуска каждого готового skill.

## Обновление И Удаление

Автообновление включается установщиком и запускается раз в двое суток. Если обновление не удалось, старая рабочая версия остаётся на месте. Runtime-видимость skill подтверждается только после перезапуска Codex; status-команда проверяет файлы, registry и состояние обновления.

Для проверки статуса:

- Windows: `%LOCALAPPDATA%\CodexTeamSkills\bin\team-skills-status.ps1`
- macOS: `~/Library/Application Support/CodexTeamSkills/bin/team-skills-status.command`

Для полного refresh на macOS: обновить локальные team-skills, синхронизировать Claude skills folder и перезапустить Codex/Claude:

- macOS: `~/Library/Application Support/CodexTeamSkills/bin/refresh-team-skills.command`

Если plugin установлен, но Codex не видит новые skills, выполните one-time repair:

- Windows: `%LOCALAPPDATA%\CodexTeamSkills\bin\update-team-skills.ps1 -RepairInstall`
- macOS: `~/Library/Application Support/CodexTeamSkills/bin/update-team-skills.sh --repair-install`

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
