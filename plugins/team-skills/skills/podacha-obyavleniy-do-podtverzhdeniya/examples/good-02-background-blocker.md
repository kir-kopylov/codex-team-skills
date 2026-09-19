# Хороший Пример: Background Browser Blocker

## Вход

Chrome API при заполнении OLX формы возвращает `another extension UI is open`. Пользователь ранее сказал: "не перехватывай клавиатуру, я хочу параллельно работать".

## Ожидаемое Поведение

Codex остаётся в background-only режиме. Он читает `references/domain-playbook.md`, использует Chronicle только как observation, если нужно понять видимое состояние, затем возвращается к Chrome API. Если blocker не снят, Codex останавливается с одной фразой: "Background API is blocked. I will not take over your keyboard. The next background-safe step is: ...".

## Нельзя

Нельзя использовать Computer Use, AppleScript, System Events, foreground typing, file picker automation или coordinate clicks. Нельзя считать раздражение пользователя разрешением на управление экраном.
