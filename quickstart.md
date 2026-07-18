# Быстрый Старт

Если вы просто хотите пользоваться командными skills, начните с [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md). Codex определит вашу систему и даст одну команду для установки.

## User Mode: Подключить Или Перевести Старую Установку

Windows:

Эта команда запускает одноразовый migrator. Он безопасно удаляет только доказанное старое автообновление, ставит проверенный release и ничего не оставляет работать в фоне.

```powershell
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $u="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/migrate-team-skills.cmd"; $p=Join-Path $env:TEMP ("migrate-team-skills-"+[guid]::NewGuid().ToString("N")+".cmd"); $c=1; try{(New-Object System.Net.WebClient).DownloadFile($u,$p); & $p; $c=$LASTEXITCODE}finally{Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue}; exit $c
```

macOS:

Migrator до изменений сам проверяет `Python 3.11+`, права и доступность release.

```bash
( p="$(mktemp -t migrate-team-skills.XXXXXX)" && trap 'rm -f "$p"' EXIT && curl -fsSL -o "$p" https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/migrate-team-skills.command && chmod +x "$p" && "$p" )
```

Migrator привязан к конкретному release tag и принимает решения по стабильным результатам cleanup и installer. Успешный результат — `MIGRATED_RESTART_REQUIRED`. Доверие строится на GitHub Releases и HTTPS; SHA-256 обнаруживает повреждение bundle, но не является независимой подписью.

## Проверить Установку

После перезапуска Codex напишите:

```text
Проверь только по списку skills этой новой сессии: доступен ли `team-skills:production-forensic-auditor`? Не ищи файлы на диске. Ответь «да» или «нет».
```

Ожидаемый ответ — `да`. Это проверяет, что новая сессия увидела plugin; exact release на диске до перезапуска уже проверил migrator.

## Обновление И Удаление

Автообновления нет. Чтобы получить новые skills, повторно запустите ту же команду migrator для своей системы и перезапустите Codex. Отдельных пользовательских команд update, status и repair нет.

Если после переустановки новые skills не появились, полностью закройте и снова откройте Codex, затем повторите проверочную фразу из раздела выше.

Для удаления скачайте из последнего Release одноразовый `uninstall-team-skills.ps1` или `uninstall-team-skills.command`. Если сохранилось старое автообновление, сначала запустите обычную команду migrator, затем повторите uninstaller.

## Claude Code: Подключить Через Маркетплейс

Если вы работаете в `Claude Code`, а не в Codex, подключите скилы нативным маркетплейсом — без установщика и клона repo:

```text
/plugin marketplace add kir-kopylov/codex-team-skills
/plugin install team-skills@codex-team-skills
```

Подробности и авто-раздача на всю команду — в [docs/claude-code-marketplace.md](docs/claude-code-marketplace.md).

Когда что выбирать: Codex → одноразовый migrator GitHub Release (выше); `Claude Code` → нативный маркетплейс.

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
