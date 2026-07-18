# Гид Для Организатора Onboarding

Эта инструкция для человека, который помогает коллегам подключиться к общему хранилищу Codex skills. Коллеге отправляйте [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md).

## Два Режима

**User mode** — Codex Desktop и одноразовый installer. На macOS нужен Python 3.11 или новее. GitHub аккаунт и локальная копия repo не нужны.

**Author mode** — GitHub аккаунт, локальная рабочая копия repo, branch, tests и Pull Request.

## Что Делает Installer

Installer скачивается из последнего GitHub Release, но внутри привязан к конкретному immutable release tag. Он:

1. во временной папке скачивает `manifest.json` и `team-skills-bundle.zip` этого release;
2. сверяет release tag, размер и SHA-256 bundle;
3. проверяет имя, версию и release ID в `.codex-plugin/plugin.json`;
4. транзакционно заменяет plugin с rollback при ошибке;
5. обновляет только записи `codex-team-skills` в marketplace и Codex config;
6. удаляет только cache `codex-team-skills` и временные файлы;
7. завершается, не оставляя updater root, scheduler, LaunchAgent, state или logs.

Повторный запуск того же installer — ручное обновление или repair. Отдельных update/status-команд нет.

## Граница Доверия

Клиент доверяет публичному GitHub repository, GitHub Releases и HTTPS. SHA-256 обнаруживает повреждение bundle при скачивании, но не является независимой подписью и не защищает от компрометации GitHub или аккаунта владельца repo. Собственная RSA-подпись, локальный public key и signing secret не используются.

## Одноразовая Миграция Старых Машин

Сначала должен быть опубликован release без фонового updater. После этого на каждой старой машине:

1. скачайте cleanup из того же Release;
2. запустите только `dry-run`;
3. проверьте, что результат — `DRY_RUN_SAFE` либо `NOT_FOUND`;
4. при `DRY_RUN_SAFE` запустите `apply`;
5. ожидайте `CLEANED` и exit code `0`;
6. только затем запустите новый one-shot installer и перезапустите Codex;
7. повторный `apply` должен вернуть `NOT_FOUND`.

Windows:

```powershell
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $u="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/remove-team-skills-autoupdate.ps1"; $p="$env:TEMP\remove-team-skills-autoupdate.ps1"; $b=(New-Object System.Net.WebClient).DownloadData($u); $s=[System.Text.Encoding]::UTF8.GetString($b); if($s.Length -gt 0 -and $s[0] -eq [char]0xFEFF){$s=$s.Substring(1)}; $enc=New-Object System.Text.UTF8Encoding($true); [System.IO.File]::WriteAllText($p,$s,$enc); powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p -DryRun
```

После безопасного отчёта замените последний `-DryRun` на `-Apply`.

macOS:

```bash
curl -fsSL -o /tmp/remove-team-skills-autoupdate.command https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/remove-team-skills-autoupdate.command && chmod +x /tmp/remove-team-skills-autoupdate.command && /tmp/remove-team-skills-autoupdate.command --dry-run
```

После безопасного отчёта замените последний `--dry-run` на `--apply`.

Cleanup удаляет только доказанную старую задачу/plist, процессы updater, legacy root и два точных macOS updater-лога. Он не удаляет plugin, marketplace, Codex config, active cache или recovery-копии. Нестандартный orphan-root без живого scheduler автоматически не удаляется.

Промпт для Codex на машине:

> Запусти официальный `remove-team-skills-autoupdate` сначала в `dry-run`. Покажи найденные объекты. Если скрипт вернул `DRY_RUN_SAFE`, запусти `apply` и покажи before/after report. Ничего вне скрипта не удаляй.

## Установка, Обновление И Удаление

Для установки или обновления повторно используйте OS-specific команду из [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md), затем перезапустите Codex.

Для полного удаления скачайте из последнего Release и запустите:

- Windows — `uninstall-team-skills.ps1`;
- macOS — `uninstall-team-skills.command`.

Uninstaller не выполняет legacy cleanup. Если старая задача или root ещё существуют, он откажется и потребует сначала выполнить предыдущий раздел.

## Что Отправить Коллеге

```text
Загрузи этот .md файл в Codex Desktop, нажми отправить и следуй инструкциям.

Codex определит твою систему и даст одну команду для установки командных skills.
```

## Author Mode

Автор создаёт branch, добавляет или меняет skill, запускает `python -m pytest` и открывает Pull Request. Обычному пользователю этот workflow не нужен.
