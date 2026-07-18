# Гид Для Организатора Onboarding

Эта инструкция для человека, который помогает коллегам подключиться к общему хранилищу Codex skills. Коллеге отправляйте [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md).

## Два Режима

**User mode** — Codex Desktop и одна команда одноразового migrator. На macOS нужен Python 3.11 или новее. GitHub аккаунт и локальная копия repo не нужны.

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

Пользователь не запускает этот внутренний installer напрямую. Ручное обновление или repair — повторный запуск той же команды migrator. Отдельных update/status-команд нет.

## Граница Доверия

Клиент доверяет публичному GitHub repository, GitHub Releases и HTTPS. SHA-256 обнаруживает повреждение bundle при скачивании, но не является независимой подписью и не защищает от компрометации GitHub или аккаунта владельца repo. Собственная RSA-подпись, локальный public key и signing secret не используются.

## Одноразовая Миграция Старых Машин

Сначала публикуется release без фонового updater. После этого коллеге отправляется только [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md): Codex запускает одну OS-specific команду migrator.

Migrator сам скачивает cleanup и installer одного exact release, выполняет безопасную проверку, при необходимости удаляет доказанный legacy updater, ставит plugin один раз и повторно проверяет, что updater не вернулся. Единственный успешный итог — `MIGRATED_RESTART_REQUIRED`; после него коллега полностью перезапускает Codex и выполняет проверочную фразу из стартового файла.

Если итог другой, ничего вручную не удаляйте:

- `BLOCKED_PREFLIGHT` — переход не начинался; устраните указанную предпосылку;
- `REFUSED_UNSAFE` — объект неоднозначен; передайте вывод maintainer-у;
- `CLEANUP_INCOMPLETE` — cleanup мог начаться, но postcondition не доказан;
- `LEGACY_REMOVED_INSTALL_PENDING` — updater уже отсутствует, но установка не завершена; повторно запустите ту же команду после устранения указанной причины;
- `INSTALLER_REGRESSION_CLEANED` — после installer снова появился updater; rollout этого release остановить.

Отдельные `remove-team-skills-autoupdate.ps1` и `remove-team-skills-autoupdate.command` нужны только maintainer-у для разбора `REFUSED_UNSAFE` или `CLEANUP_INCOMPLETE`. Это не второй пользовательский протокол и не команда для импровизированного ручного удаления.

## Установка, Обновление И Удаление

Для установки или обновления повторно используйте ту же OS-specific команду migrator из [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md), затем перезапустите Codex.

Для полного удаления скачайте из последнего Release и запустите:

- Windows — `uninstall-team-skills.ps1`;
- macOS — `uninstall-team-skills.command`.

Uninstaller не выполняет legacy cleanup. Если старая задача или root ещё существуют, сначала запустите обычный migrator; при `REFUSED_UNSAFE` или `CLEANUP_INCOMPLETE` передайте вывод maintainer-у.

## Что Отправить Коллеге

```text
Загрузи этот .md файл в Codex Desktop, нажми отправить и следуй инструкциям.

Codex определит твою систему и даст одну команду для установки командных skills.
```

## Author Mode

Автор создаёт branch, добавляет или меняет skill, запускает `python -m pytest` и открывает Pull Request. Обычному пользователю этот workflow не нужен.
