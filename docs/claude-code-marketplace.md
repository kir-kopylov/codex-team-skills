# Маркетплейс Claude Code

Этот репозиторий — нативный **маркетплейс Claude Code**. Витрина описана в
`.claude-plugin/marketplace.json` (имя маркетплейса — `codex-team-skills`), а
сами скилы лежат в плагине `team-skills` (`plugins/team-skills/`), откуда
Claude Code автоматически читает папку `skills/`.

Это отдельный, более чистый путь доставки в дополнение к Codex и к скрипту
`scripts/pull-skills.sh`. Менять старые механизмы не требуется — они продолжают
работать.

## Способ 1. Ручная установка (две команды)

Коллега один раз выполняет в Claude Code:

```
/plugin marketplace add kir-kopylov/codex-team-skills
/plugin install team-skills@codex-team-skills
```

Приватный репозиторий тоже работает: установка идёт по обычному git-доступу
пользователя, токены в манифест зашивать не нужно. Обновления подтягиваются
командой `/plugin marketplace update codex-team-skills`.

## Способ 2. Авто-раздача через settings.json (без действий пользователя)

Чтобы маркетплейс подключался и плагин включался сам, добавьте этот блок в
`settings.json`. Ключ включения плагина имеет вид `<plugin>@<marketplace>` —
здесь `team-skills@codex-team-skills`.

```json
{
  "extraKnownMarketplaces": {
    "codex-team-skills": {
      "source": { "source": "github", "repo": "kir-kopylov/codex-team-skills" }
    }
  },
  "enabledPlugins": {
    "team-skills@codex-team-skills": true
  }
}
```

Куда положить этот блок — по охвату:

- **Один проект/команда** — закоммитьте `.claude/settings.json` в рабочий
  репозиторий проекта. Скилы появляются у всех, кто его открывает.
- **Один человек** — его пользовательский `~/.claude/settings.json`.
- **Вся фирма (принудительно)** — managed settings, раскатываются
  централизованно (MDM/админ). Пользователь ничего не делает и не может
  отключить плагин. Путь файла зависит от ОС:
  - macOS: `/Library/Application Support/ClaudeCode/managed-settings.json`
  - Linux: `/etc/claude-code/managed-settings.json`
  - Windows: в новых версиях Claude Code —
    `C:\Program Files\ClaudeCode\managed-settings.json`; в старых сборках путь
    был `C:\ProgramData\ClaudeCode\managed-settings.json`. Перед раскаткой
    сверьтесь с актуальной докой Claude Code для вашей версии.

В managed-файл кладётся тот же JSON-блок, что и выше.

## Как проверить

После подключения в Claude Code:

- `/plugin` — открыть список маркетплейсов и плагинов; убедиться, что
  `codex-team-skills` подключён, а `team-skills` включён;
- спросить «какие командные скилы мне доступны» — модель перечислит скилы из
  `plugins/team-skills/skills/`.

## Почему у плагина нет поля `version`

В `plugins/team-skills/.claude-plugin/plugin.json` поле `version` намеренно
опущено. Claude Code определяет факт обновления плагина по `version` раньше, чем
по `git SHA`: при фиксированной версии правки в папке `skills/` не доходят до
уже установленных пользователей. Без `version` обновление определяется по
коммиту, и новые скилы доезжают сразу.

## Связь с Codex

Один репозиторий обслуживает два runtime. Файлы не конфликтуют:

- Claude Code читает `.claude-plugin/marketplace.json` и
  `plugins/team-skills/.claude-plugin/plugin.json`;
- Codex читает `.agents/plugins/marketplace.json` и
  `plugins/team-skills/.codex-plugin/plugin.json`;
- общими остаются папки скилов `plugins/team-skills/skills/<skill>/SKILL.md`.
