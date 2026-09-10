## Вход

Пользователь дает JSON, где в старом English блоке есть `Welcome, the castle is open!`, а в Chinese блоке есть literal translation artifacts.

## Ожидаемое Поведение

Не чинить только одну строку. Пересобрать или полностью audit target-language blocks from `ru`. Заменить смысловые ошибки: `замок открыт` -> `the lock is open` / `门锁已打开`; `горничная` -> cleaner / `保洁人员`; `отчетные документы` -> accounting/reporting documents / `报销/凭证文件`. Отдельно сверить, что все маршруты, входы, лифты, лестницы, коды и условия в `en/kk/ch` совпадают с русским источником.

## Нельзя

Считать structural JSON validation достаточной. Оставлять `castle`, `maid`, mojibake fragments or untranslated device-function words outside `ru`. Сохранять перевод, где путь гостя отличается от `ru`, даже если плейсхолдеры и JSON-схема совпали.
