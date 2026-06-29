# Языковая Политика Проекта

Проект должен быть понятен русскоязычным коллегам, которые не обязаны быть инженерами.

## Что Должно Быть На Русском

- `README.md`
- `catalog.md`
- `quickstart.md`
- `START_HERE_CONNECT_CODEX_SKILLS.md`
- `admin-onboarding-guide.md`
- `CONTRIBUTING.md`
- `.github/pull_request_template.md`
- заголовок, описание и комментарии Pull Request
- человекочитаемые описания в `plugin.json`
- человекочитаемые описания в `skill.yaml`
- body и `description` в `SKILL.md`
- `examples/*.md`
- сообщения скриптов, которые видит пользователь

## Pull Request

Описание PR, первый комментарий PR, review comments и review body пишутся на русском языке. Технические имена, пути, команды, branch names, commit hashes, статусы CI и названия файлов остаются как есть.

Запрещено оставлять человекочитаемое описание PR на английском вроде `What changed`, `Why`, `Validation`, `Notes`. Если нужен такой каркас, используйте русские заголовки: `Что изменилось`, `Зачем`, `Проверка`, `Примечания`.

## Что Не Переводить

Эти элементы являются техническим контрактом и должны оставаться стабильными:

- имена файлов: `SKILL.md`, `plugin.json`, `skill.yaml`, `catalog.md`;
- YAML/JSON keys: `owner`, `authors`, `source_asset`, `status`, `summary`, `use_cases`, `example_files`;
- статусы: `draft`, `experimental`, `team-ready`, `deprecated`, `internal-only`;
- команды: `python -m pytest`, `./scripts/install_plugin.sh`;
- пути, имена plugin/skill, branch names, repo names;
- термины Codex/GitHub, если их перевод делает инструкцию менее точной.

## Как Это Защищено

CI запускает `pytest` на каждом Pull Request. Тест `test_language_policy.py` проверяет, что пользовательский слой проекта остаётся русскоязычным, а технические ключи и команды не переводятся.

Отдельный workflow `.github/workflows/pr-language.yml` проверяет PR title/body и PR comments через `scripts/check_pr_language.py`. Он должен падать, если человекочитаемый текст PR выглядит англоязычным или не содержит русского текста.
