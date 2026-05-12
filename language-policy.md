# Языковая Политика Проекта

Проект должен быть понятен русскоязычным коллегам, которые не обязаны быть инженерами.

## Что Должно Быть На Русском

- `README.md`
- `catalog.md`
- `quickstart.md`
- `SEND_TO_COLLEAGUE.md`
- `admin-onboarding-guide.md`
- `CONTRIBUTING.md`
- `.github/pull_request_template.md`
- человекочитаемые описания в `plugin.json`
- человекочитаемые описания в `skill.yaml`
- body и `description` в `SKILL.md`
- `examples/*.md`
- сообщения скриптов, которые видит пользователь

## Что Не Переводить

Эти элементы являются техническим контрактом и должны оставаться стабильными:

- имена файлов: `SKILL.md`, `plugin.json`, `skill.yaml`, `catalog.md`;
- YAML/JSON keys: `owner`, `status`, `summary`, `use_cases`, `example_files`;
- статусы: `draft`, `team-ready`, `deprecated`, `internal-only`;
- команды: `python -m pytest`, `./scripts/install_plugin.sh`;
- пути, имена plugin/skill, branch names, repo names;
- термины Codex/GitHub, если их перевод делает инструкцию менее точной.

## Как Это Защищено

CI запускает `pytest` на каждом Pull Request. Тест `test_language_policy.py` проверяет, что пользовательский слой проекта остаётся русскоязычным, а технические ключи и команды не переводятся.
