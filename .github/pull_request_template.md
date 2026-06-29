# Чеклист Pull Request Для Скилла

## Зачем

- Какую боль решает:
- Для кого:
- Когда не использовать:
- Какие примеры доказывают полезность:

## Проверки

- [ ] Заголовок, описание и комментарии PR написаны на русском; технические имена, пути и команды оставлены как есть.
- [ ] `python -m pytest` проходит.
- [ ] `catalog.md` обновлён, если skill имеет статус `team-ready`.
- [ ] Пользовательский слой на русском: README/catalog/quickstart/onboarding/contribution guide/PR template/plugin descriptions/skill descriptions/examples/script messages.
- [ ] Технические ключи и команды не переведены: `owner`, `status`, `SKILL.md`, `plugin.json`, `pytest`, пути и команды сохранены.
- [ ] Нет приватных данных, токенов, pasteboard/download paths или сырого клиентского контекста.
- [ ] Для `team-ready` есть хорошие примеры и анти-примеры.
- [ ] Claude sync smoke проходит: repo-managed skills копируются через `scripts/pull-skills.sh`, local-only skills не удаляются.
