---
name: translate-sutki-access-json
description: Используйте этот skill, когда пользователь просит перевести JSON с инструкциями доступа, заселения или выезда для посуточных апартаментов на English, Kazakh и Chinese, сохранив схему JSON, ключи ru/en/kk/ch, HTML-теги, плейсхолдеры, коды доступа, адреса, переносы строк и кодировку UTF-8 без BOM. Срабатывает на фразы "переведи entranceMessages.json", "переведи access JSON на 3 языка", "сделай готовый JSON для Sutki", "исправь перевод улиц в JSON".
---

# Translate Sutki Access JSON

## Согласие На Запуск

Явный вызов — slash-команда, имя skill или первая фраза из каталога — выполняйте сразу, без вопроса. При автосрабатывании на смысловое сходство сначала спросите одной строкой: «Задача похожа на team skill `translate-sutki-access-json` — переводит JSON инструкций доступа для апартаментов с сохранением схемы, кодов и плейсхолдеров. Применить или решить без него?» — и ждите ответ. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

Этот skill переводит guest-facing JSON с инструкциями доступа, заселения, выезда и возврата залога для посуточных апартаментов.

Цель — получить готовый JSON-файл, который можно загрузить обратно в систему без ручной правки. Перевод должен быть естественным для гостя, но технические детали должны остаться неизменными: структура, ключи, HTML, плейсхолдеры, коды, этажи, подъезды, квартиры, адреса и точная последовательность переносов строк.

## Быстрый Роутинг

- Пользователь дал `.json` с `ru`, `en`, `kk`, `ch`, `translations`, `entrance-info`, `entrance-welcome`, `entrance-farewell`, `entrance-exit` или похожими ключами -> используйте этот skill.
- Пользователь просит "переведи на 3 языка" для access/check-in/check-out JSON -> переведите из `ru` в `en`, `kk`, `ch`, даже если старые целевые блоки уже есть.
- Пользователь просит готовый файл -> сохраните `.json`, не вставляйте весь JSON в чат.
- Пользователь уточняет правило про улицы, города, Консьерж, замок, горничную или кодировку -> обновите перевод и проверку под это правило.
- Пользователь просит литературный перевод без JSON, юридически заверенный перевод или live-state подтверждение адреса/наличия/цены -> этот skill не подходит.

## Процесс

1. Прочитайте исходный JSON как UTF-8. Проверьте, есть ли BOM, но не меняйте исходный файл без просьбы.
2. Определите русский источник: обычно `translations.ru` или `ru`.
3. Не доверяйте существующим `en`, `kk`, `ch`: пересоберите их из `ru` или явно audited against current rules.
4. Сохраните исходный `ru` без изменений, если пользователь не просил исправить русский текст.
5. Сохраните форму данных: массив или объект, `external_id`, все языковые блоки, все ключи внутри блоков.
6. Переведите:
   - `en`: English;
   - `kk`: Kazakh;
   - `ch`: Simplified Chinese.
7. Сохраните результат в UTF-8 without BOM.
8. Проверьте готовый файл парсингом JSON и отдельными semantic checks.
9. Перед сохранением готового файла выполните line-break audit: для каждого переводимого строкового поля извлеките из `ru`, `en`, `kk`, `ch` последовательность токенов переносов `CRLF`, `LF`, `CR` и убедитесь, что количество, порядок и тип каждого переноса совпадают.
10. Перед сдачей выполните обязательный semantic equivalence audit: для каждой смысловой инструкции в `ru` проверьте, что `en`, `kk` и `ch` передают тот же маршрут, действие, условие, ограничение и последовательность, а не только похожие слова.

## Что Сохранять Без Изменений

- HTML tags: `<b>`, `</b>`, `<i>`, `</i>`, `<br>` and similar markup.
- Placeholders: `[[PathLink]]`, `[[DoorPhoto]]` and every other `[[...]]` token.
- Access details: door codes, intercom codes, lock codes, floor numbers, entrance numbers, apartment numbers, dates, times, phone-like strings and punctuation inside codes such as `A#123`.
- JSON keys exactly as provided. Do not rename `ch` to `zh`.
- Переносы строк точно как в исходнике. Для каждой переводимой строки сохраняйте то же количество, порядок и тип переносов, что в `ru`: `CRLF` (`\r\n`) остается `CRLF`, `LF` (`\n`) остается `LF`, одиночный `CR` (`\r`), если встретится, остается `CR`.

## Переносы Строк

Переносы строк являются частью контракта данных, а не декоративным форматированием. Не нормализуйте их.

Для каждого переводимого строкового поля целевые поля `en`, `kk` и `ch` должны сохранять ту же последовательность токенов переносов, что исходное поле `ru`:

- одинаковое количество переносов;
- одинаковый порядок;
- тот же тип каждого переноса: `CRLF`, `LF` или одиночный `CR`;
- те же смысловые границы: между теми же абзацами, пунктами списка и строками инструкции.

Запрещено:

- превращать `CRLF` в `LF`;
- превращать `LF` в `CRLF`;
- заменять переносы пробелами;
- заменять переносы на `<br>`, если `<br>` не был буквальным содержимым исходника, а реальные токены переносов после этого не совпадают.

Перед сохранением JSON-файла извлеките последовательность токенов переносов из `ru` и из каждого соответствующего поля `en`, `kk`, `ch`. Сохранять файл запрещено, пока последовательности не совпадают точно. Экранированный JSON-текст вроде `\\r\\n` после чтения должен давать ту же последовательность токенов переносов.

## Адреса, Города И Улицы

Transliterate city and street names in addresses instead of translating them by meaning. Translate the address object type into the target language.

Correct examples:

- English: `Almaty`, `8 Marta Street`, `Kosmonavtov Avenue`, `Tramvayny Lane`.
- Kazakh: `Almaty`, `8 Marta көшесі`, `Kosmonavtov даңғылы`, `Tramvayny тұйық көшесі`.
- Chinese: `Almaty`, `8 Marta 街`, `Kosmonavtov 大道`, `Tramvayny 巷`.

Incorrect examples when transliteration is required:

- Chinese `阿拉木图` for `Алматы`.
- Chinese `三月八日街` for `8 Марта`.
- Chinese `8 Marta Street` inside `ch`, because the street name is transliterated but the word `Street` was not translated.
- Russian-only street names inside `en` or `ch`, unless the user explicitly asks for exact pasted source address.

Keep residential complexes, stores and navigation landmarks recognizable when guests must match them to signs or maps. For example, keep `ЖК Мельница` or `Пятерочка` visible and add a target-language descriptor only when helpful, such as Chinese `Пятерочка 超市` or `ЖК Мельница 住宅区`.

## Translation Style

- Use clear, polite guest-facing instructions.
- Translate meaning, not word order.
- Use practical terms: check-in, checkout, lock, cleaner, deposit, accounting documents, keys.
- Do not add warnings, explanations, fields or comments inside JSON.
- Translate button functions semantically unless the Russian word is confirmed as a visible device label.

Avoid known literal errors:

- `замок открыт` -> English `the lock is open`, Chinese `门锁已打开`; never `castle is open`.
- `горничная` in this context -> cleaner/cleaning staff; Chinese `保洁人员`, not servant-like wording.
- `отчетные документы` -> accounting/reporting documents; Chinese can use `报销/凭证文件`.
- `кнопка Консьерж`, if not confirmed as a visible printed label -> `concierge call button`, Kazakh functional wording, Chinese `呼叫礼宾/管理员按钮`.

## Проверка

Before final response, run or emulate these checks:

- Смысловой аудит пройден: каждый нумерованный шаг, маршрут, выбор входа, инструкция про лифт или лестницу, условие по замку или действию, выезд и возврат залога в `en`, `kk` и `ch` совпадают с `ru`.
- Аудит переносов строк пройден: каждое переводимое строковое поле сохраняет точную последовательность токенов `CRLF`, `LF` и одиночного `CR` для `ru -> en/kk/ch` без нормализации.
- JSON parses successfully.
- Output encoding is UTF-8 without BOM when a file is required.
- Record count matches source.
- `ru` block is unchanged unless explicitly edited.
- Every target language has the same keys as `ru`.
- Counts of `[[PathLink]]`, `[[DoorPhoto]]` and other placeholders match the Russian source per record.
- Access codes, floors, entrances, apartment numbers and door/intercom codes match source.
- Search target blocks for risky markers: `castle`, `maid`, mojibake fragments such as `Рџ`, `Р¶`, `Рњ`, and `Консьерж` outside `ru`.
- Search `en` and `ch` address fields for Cyrillic street/city names.
- Search `ch` address fields for English address type words such as `Street`, `Avenue`, `Lane`.
- Search `ch` address fields for incorrect Chinese-translated proper names such as `阿拉木图` and `三月八日街` when transliteration is required.

Процедура аудита переносов строк:

1. Для каждого соответствующего строкового поля читайте уже разобранные строковые значения, а не сырой JSON-текст.
2. Извлекайте токены по порядку: идите слева направо; `\r\n` -> `CRLF`, одиночный `\n` -> `LF`, одиночный `\r` -> `CR`.
3. Сравните токены `ru` с токенами каждого целевого языка.
4. Если отличается количество, порядок или тип хотя бы одного токена, исправьте переводимую строку до записи финального файла.
5. Не используйте глобальную нормализацию переносов, pretty-printer или редактор, который молча переписывает переносы внутри строковых значений JSON.

Semantic equivalence audit is mandatory because structural validation can be green while the guest-facing route is wrong. Check these risk patterns explicitly:

- `ru` offers alternatives such as "or", "или", "либо", "если" -> every target language must preserve the same alternatives and conditions.
- `ru` distinguishes main entrance, separate entrance, left/right side, stairs, elevator, floor or section -> targets must keep the same object and direction, not merge them.
- `ru` says a key/code/photo/link is needed for one route only -> targets must not move that requirement to another route.
- `ru` has a sequence of actions -> targets must preserve the sequence, not reorder it for style.

## Ответ

If the user asked for a file, reply briefly with:

- saved file path;
- JSON parse status;
- UTF-8 without BOM status;
- record count;
- line-break audit status: `переносы строк ru→en/kk/ch сверены; CRLF/LF сохранены без нормализации`;
- semantic audit status for `ru -> en/kk/ch`;
- any unresolved ambiguity.

Do not paste the entire JSON unless the user asks.

## Опрос После Использования

Опрос задается один раз — после сдачи финального файла или явного стопа, не посреди рабочего цикла. Если пользователь уже ответил «пропустить» в этой сессии, не переспрашивайте.

```text
Опрос по skill:
1. Что в этом использовании translate-sutki-access-json было полезно?
2. Что стоит доработать в skill или его формате?
Можно ответить коротко или написать "пропустить".
```

Если пользователь ответил, сохраните санированную карточку в `~/.codex/skill-runs/translate-sutki-access-json/usage-feedback.jsonl` через bundled script:

```bash
python scripts/log_usage_feedback.py --liked "..." --improve "..." --outcome "..."
```

Скрипт перед записью редактирует приватные пути, контакты и token-like строки и сохраняет `redaction_applied` и `redaction_types`. Если запись невозможна из-за sandbox, прав или отсутствия tools, не делайте вид, что лог сохранён: скажите об этом и покажите короткую JSONL-карточку для ручного сохранения. Raw-ответы, контакты, пути и секреты не коммитить.

## Логирование Сбоев

Перед выполнением skill прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если skill ошибся, пользователь поправил правило, tool/API/browser упал, нарушен режим работы или пришлось искать workaround, запишите приватную карточку в `~/.codex/skill-runs/translate-sutki-access-json/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.
