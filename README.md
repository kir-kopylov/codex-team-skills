# Codex Team Skills Registry

Это командное хранилище Codex skills. Оно упаковано как plugin `team-skills` и подключается штатным marketplace Codex из публичного Git-репозитория. Репозиторий публично читаемый, но не open-source: все права защищены, внутреннее использование командой. Условия — в файле [LICENSE](LICENSE).

Смысл проекта — понятный рабочий процесс для команды:

- коллега находит нужный skill по задаче;
- понимает, какой обычной фразой его запустить;
- видит владельца, границы применения и примеры;
- устанавливает и обновляет библиотеку штатными командами Codex;
- может предложить новый skill через Pull Request;
- CI защищает структуру, приватность, язык и версию plugin.

Обычному пользователю нужен один файл: [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md). Его можно загрузить в Codex и попросить агента установить библиотеку. Если на компьютере уже была старая установка, используйте [START_HERE_RECONNECT_CODEX_SKILLS.md](START_HERE_RECONNECT_CODEX_SKILLS.md).

Дополнительные входы:

- [quickstart.md](quickstart.md) — короткие команды установки, обновления и удаления;
- [admin-onboarding-guide.md](admin-onboarding-guide.md) — инструкция организатору подключения;
- [docs/claude-code-marketplace.md](docs/claude-code-marketplace.md) — отдельный путь для Claude Code;
- [catalog.md](catalog.md) — каталог доступных skills.

## Как Устроен Проект

```text
plugins/team-skills/
  .codex-plugin/plugin.json        # паспорт plugin для Codex
  .claude-plugin/plugin.json       # паспорт plugin для Claude Code
  skills/<skill-name>/             # инструкции, примеры и метаданные skills
.agents/plugins/marketplace.json   # штатный marketplace Codex
.claude-plugin/marketplace.json    # штатный marketplace Claude Code
catalog.md                         # каталог для людей
scripts/                           # создание skills, проверки и Claude sync
tests/                             # проверки структуры, доставки и приватности
```

## User Mode И Author Mode

Пользователь не скачивает и не запускает удалённые скрипты. Codex подключает Git marketplace, устанавливает `team-skills`, а после обновления пользователь полностью перезапускает приложение.

Автор работает через Pull Request: создаёт branch, меняет skill, повышает semver plugin, запускает `python -m pytest` и отправляет изменения на review.

## Как Добавляется Новый Skill

1. Проверьте, что задача повторяемая, входы и результат понятны, а границы применения известны.
2. Создайте черновик:

   ```bash
   python scripts/new_skill.py <skill-name> --owner @github-login
   ```

3. Заполните `SKILL.md`, `skill.yaml`, `known-exceptions.yaml` и `examples/`.
4. Добавьте строку в `catalog.md`.
5. Повышайте patch-версию `plugins/team-skills/.codex-plugin/plugin.json` для обычного изменения skill.
6. Запустите `python -m pytest` и откройте Pull Request.

## Приватность

Не добавляйте в repo токены, личные пути, сырые логи, скриншоты, приватные переписки и данные клиентов. В публичную историю переносится только обезличенная механика, синтетические примеры и проверяемые правила.
