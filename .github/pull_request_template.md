# Чеклист Pull Request Для Скилла

## Зачем

- Какую боль решает:
- Для кого:
- Когда не использовать:
- Какие примеры доказывают полезность:

## Жёсткая Проверка installer/release

Заполнять и отмечать только если менялись `installer/`, `scripts/build_release_bundle.py`, `scripts/pull-skills.sh` или `.github/workflows/tests.yml`.

- [ ] Windows PowerShell 5.1 / `ValidateOnly` проверены.
- [ ] `manifest.json` / `latest.json` / подпись release metadata проверены.
- [ ] Откат или повторная установка проверены.

## Проверки

- [ ] Заголовок, описание и комментарии PR написаны на русском; технические имена, пути и команды оставлены как есть.
- [ ] `python -m pytest` проходит.
- [ ] `catalog.md` обновлён, если skill имеет статус `team-ready`.
- [ ] Заголовок и описание PR на русском.
- [ ] Пользовательский слой на русском: `README.md`, `catalog.md`, `quickstart.md`, документы подключения, `CONTRIBUTING.md`, шаблон PR, описания plugin и skills, примеры, сообщения scripts.
- [ ] Технические ключи и команды не переведены: `owner`, `status`, `SKILL.md`, `plugin.json`, `pytest`, пути и команды сохранены.
- [ ] Нет приватных данных, токенов, `pasteboard`/`download paths` или сырого клиентского контекста.
- [ ] Для `team-ready` есть хорошие примеры и анти-примеры.
- [ ] Claude sync smoke проходит: skills из repo копируются через `scripts/pull-skills.sh`, локальные skills не удаляются.
