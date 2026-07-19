# Быстрый Старт

Для обычного подключения можно передать Codex файл [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md). Ниже — те же команды для уверенного пользователя терминала.

## Проверить Codex

```powershell
codex --version
codex plugin --help
```

Нужен Codex `0.144.4` или новее. Если `codex plugin` отсутствует, сначала обновите Codex; не переходите к скачиванию установочных скриптов.

## Установить

```powershell
codex plugin marketplace add kir-kopylov/codex-team-skills --ref main --json
codex plugin add team-skills@codex-team-skills --json
```

## Обновить

```powershell
codex plugin marketplace upgrade codex-team-skills --json
codex plugin add team-skills@codex-team-skills --json
```

## Удалить

```powershell
codex plugin remove team-skills@codex-team-skills --json
codex plugin marketplace remove codex-team-skills --json
```

После установки, обновления или удаления полностью перезапустите Codex. Проверяйте runtime по списку skills новой сессии, а не только по файлам на диске.

Если на компьютере осталась старая локальная установка или фоновая задача, не удаляйте её по совпадению имени. Используйте [START_HERE_RECONNECT_CODEX_SKILLS.md](START_HERE_RECONNECT_CODEX_SKILLS.md).

## Claude Code

Для Claude Code действует отдельный нативный marketplace:

```text
/plugin marketplace add kir-kopylov/codex-team-skills
/plugin install team-skills@codex-team-skills
```

Подробности — в [docs/claude-code-marketplace.md](docs/claude-code-marketplace.md).

## Добавить Новый Skill

```bash
python scripts/new_skill.py my-skill --owner @yourname --summary "Коротко: что делает скилл"
python -m pytest
```

Обычное изменение skill требует повышения patch-версии Codex plugin. Перед статусом `team-ready` обновите `catalog.md` и откройте Pull Request.
