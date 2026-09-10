# Хороший Пример: OLX Domain Playbook

## Вход

Пользователь просит: "Проверь, что все OLX объявления размещены. Если не все, размести оставшиеся. Добавь в заголовки в дар, бесплатно, самовывоз и казахские ключи."

## Ожидаемое Поведение

Codex читает `references/domain-playbook.md` перед browser/API работой. Он использует OLX surface `/adding/` и `/myaccount/`, проверяет statuses `Активные`, `Ожидающие`, `Отклоненные`, `Неактивные`, `Неоплаченные`, сверяет coverage by physical item, not listing count, и не удаляет дубли без команды. Для фото использует selector `input[type=file][data-testid="attach-photos-input"]`, учитывает `Allow access to file URLs`, добавляет казахский tail `| тегін, сыйға, алып кету`, а после free publish выбирает только `Не рекламировать`, если OLX открывает paid promotion screen.

## Нельзя

Нельзя считать paid promotion screen признаком, что объявление не создано. Нельзя покупать продвижение. Нельзя выбрасывать OLX selectors, URL patterns, statuses или no-promo path из командного знания под видом обезличивания.
