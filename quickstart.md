# Быстрый Старт

Если вы просто хотите пользоваться командными skills, начните с [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md). Codex определит вашу систему и даст одну команду для установки.

## User Mode: Установить Готовый Plugin

Windows:

Эта команда скачивает одноразовый установщик из последнего проверенного GitHub Release и ставит `team-skills`.

```powershell
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $u="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.ps1"; $p="$env:TEMP\install-team-skills.ps1"; $b=(New-Object System.Net.WebClient).DownloadData($u); $s=[System.Text.Encoding]::UTF8.GetString($b); if($s.Length -gt 0 -and $s[0] -eq [char]0xFEFF){$s=$s.Substring(1)}; $enc=New-Object System.Text.UTF8Encoding($true); [System.IO.File]::WriteAllText($p,$s,$enc); powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p
```

macOS:

Для этого пути нужен `Python 3.11+`; macOS не гарантирует его наличие. Проверьте `python3 --version` до запуска. Команда ниже скачивает одноразовый установщик из последнего проверенного GitHub Release и ставит `team-skills`.

```bash
curl -fsSL -o /tmp/install-team-skills.command https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.command && chmod +x /tmp/install-team-skills.command && /tmp/install-team-skills.command
```

Установщик привязан к конкретному release tag, берёт из него `manifest.json` и bundle, сверяет размер и SHA-256, регистрирует локальный marketplace в Codex config и просит перезапустить Codex. Доверие строится на GitHub Releases и HTTPS; SHA-256 обнаруживает повреждение файла, но не является независимой подписью.

## Проверить Установку

После перезапуска Codex напишите:

```text
Покажи, какие командные skills доступны.
```

Ожидаемое поведение: Codex видит plugin `team-skills`, кратко объясняет доступные skills и показывает первую фразу для запуска каждого готового skill.

## Обновление И Удаление

Автообновления нет. Чтобы получить новые skills, повторно запустите ту же команду установки из раздела `User Mode`, затем перезапустите Codex. Отдельных команд update, status и repair нет.

Если после переустановки новые skills не появились, полностью закройте и снова откройте Codex, затем повторите проверочную фразу из раздела выше.

Для удаления скачайте из последнего Release одноразовый `uninstall-team-skills.ps1` или `uninstall-team-skills.command`. Если сохранилось старое автообновление, uninstaller остановится и потребует сначала выполнить legacy cleanup из [admin-onboarding-guide.md](admin-onboarding-guide.md).

## Claude Code: Подключить Через Маркетплейс

Если вы работаете в `Claude Code`, а не в Codex, подключите скилы нативным маркетплейсом — без установщика и клона repo:

```text
/plugin marketplace add kir-kopylov/codex-team-skills
/plugin install team-skills@codex-team-skills
```

Подробности и авто-раздача на всю команду — в [docs/claude-code-marketplace.md](docs/claude-code-marketplace.md).

Когда что выбирать: Codex → одноразовый установщик GitHub Release (выше); `Claude Code` → нативный маркетплейс.

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
