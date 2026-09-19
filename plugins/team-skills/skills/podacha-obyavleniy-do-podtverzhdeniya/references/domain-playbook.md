# Domain Playbook

## Что Нельзя Потерять

- OLX Kazakhstan как first-class target для v1 marketplace listing workflow.
- Stable surface: `/adding/`, `/myaccount/`, edit URL pattern для возврата к опубликованным или ожидающим объявлениям.
- Автоподбор категорий OLX по заголовку: проверять итоговую категорию на preview, а не считать автоподбор достаточным.
- Ключевые поля формы: title, description, phone, person, location, category, condition, price, photos.
- Photo upload selector: `input[type=file][data-testid="attach-photos-input"]`.
- Для загрузки локальных фото через Chrome extension может требоваться `Allow access to file URLs`.
- OLX title limit: если tail с ключевыми словами не помещается, сокращать item phrase.
- После публикации OLX может открыть paid promotion screen; это не равно провалу публикации.
- Жёсткий no-promo path: `Не рекламировать` -> `Да, создать`, только если модалка говорит, что объявление уже создано и платная услуга не покупается.
- После правки title/description возможна повторная модерация.
- Проверять статусы: `Активные`, `Ожидающие`, `Отклоненные`, `Неактивные`, `Неоплаченные`.
- Проверять coverage by physical item, not listing count.
- Дубли не удалять и не деактивировать без явной команды пользователя.
- Казахские поисковые ключи для Алматы/KZ free pickup: `тегін`, `сыйға`, `алып кету`.

## Что Надо Обезличить

- Конкретный адрес, номер квартиры, подъезд, если пользователь не разрешил публиковать подъезд.
- Телефон, email, имя контактного лица и account/profile nickname.
- Реальные marketplace IDs, реальные URLs объявлений, payment/order/client IDs.
- Личные absolute paths, raw logs, chat transcripts, private screenshots и private media.
- Любые фото или media file references: в repo остаются только синтетические описания сценариев.

## Interface Mechanics

- Начинайте с background-only Chrome extension/browser API: inspect tabs, DOM selectors, form fill, file chooser API.
- Не используйте Computer Use, AppleScript, System Events, visible typing или coordinate clicks без короткого explicit foreground-control window.
- Перед заполнением формы держите локальный draft: title, description, category, price `Бесплатно`, condition, public address без квартиры, pickup terms, contact fields и photo paths.
- Public listing должен включать floor/no lift/pickup deadline, если это важно для решения покупателя, но apartment number не публикуется.
- Search wording для русских объявлений: `в дар`, `бесплатно`, `самовывоз`.
- Search wording для казахской discoverability: короткий title tail `| тегін, сыйға, алып кету`.
- Первый абзац описания может начинаться так: `Қазақша: тегін, сыйға беремін, тек өзіңіз алып кету керек. Келіп алып кету керек.`
- Не расширяйте item scope по фото. Если фото показывает матрас на кровати, объявление говорит только про матрас, пока пользователь не подтвердит кровать.
- Contact person, profile display name и old account nickname проверяются как разные сущности.

## Recovery And Edge Cases

- `another extension UI is open`: не fallback-ить в foreground control; использовать Chronicle только для observation, затем retry Chrome API. Если блокер остался, остановиться с одним background-safe шагом.
- `Browser is not available: extension`: retry once, затем официальный recovery Chrome plugin window/open-flow и reconnect без keyboard takeover.
- `Browser Use virtual clipboard is not installed`: reload edit page, retry locator-based fill, при необходимости reset browser runtime; не переходить к foreground typing.
- Paid promotion screen после free publish: выбрать только `Не рекламировать`; подтверждать `Да, создать` только при no-payment тексте о том, что объявление уже создано.
- Edited listing moderation: после изменения title/description проверить, не перешло ли объявление в `Ожидающие`, и записать это как marketplace state, а не как ошибку.
- Duplicate coverage: сверять physical inventory с account statuses. Дубли оставлять как есть, пока пользователь не попросил удалить или деактивировать.
