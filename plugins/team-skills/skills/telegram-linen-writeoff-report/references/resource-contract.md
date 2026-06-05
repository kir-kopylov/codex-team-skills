# Resource Contract

Этот файл фиксирует границу draft-пакета `telegram-linen-writeoff-report`.

Ожидаемые рабочие ресурсы исходного skill:

- `scripts/build_linen_report.py`;
- `scripts/parse_telegram_export.py`;
- `references/linen_rules.md`;
- `references/object_aliases.md`;
- `references/examples.md`;
- `references/verification.md`.

Если эти файлы недоступны в текущем запуске, skill должен запросить их у
пользователя или попросить путь к полному пакету. Отсутствие этих файлов рядом с
текущим `SKILL.md` не является доказательством, что они не существуют.

До добавления рабочих scripts и доменных references в repo или до явной привязки
к внутреннему пакету skill остается `draft` и не добавляется в `catalog.md` как
`team-ready`.
