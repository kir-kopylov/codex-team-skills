# Known Failure Patterns

Эти паттерны не являются отдельными skills. Это короткий список классов ошибок, которые стоит проверять перед выводом "готово" или перед повтором repair-действия.

## False Completion

Косвенный признак принят за результат: процесс запущен, окно открыто, форма входа видна, spinner крутится, терминальная команда успешна. Лечение: completion gate с direct evidence и forbidden false positives.

## Tool-Layer Confusion

Наблюдение из одного слоя выдано за состояние другого слоя. Например, PowerShell видит сеть, а GUI-приложение может идти через собственный proxy или старый профиль. Лечение: layer matrix и provenance для каждого факта.

## Stale Evidence

Скрин, лог или статус относятся к прошлому состоянию. Лечение: freshness в completion gate и новый state fingerprint после каждого действия пользователя, сна, перезапуска или смены VPN.

## Same-State Repeat

Агент повторяет действие без изменения влияющего слоя. Лечение: ledger запрещает повтор при том же fingerprint и явно называет, какое изменение разрешает ретест.

## User Changed Goal Mid-Run

Цель изменилась, но агент продолжает старый критерий. Лечение: goal contract обновляется, старый completion gate становится недействительным.

## Sandbox Result Mistaken For App Reality

Результат из Codex sandbox, терминала или bundled runtime принят за состояние пользовательского приложения. Лечение: маркировать provenance и требовать прямое evidence из целевого слоя.

## GUI Screenshot/Accessibility Mismatch

Accessibility tree, координаты и реальный скрин спорят друг с другом. Лечение: GUI evidence ladder и fresh after-screenshot после каждого действия.
