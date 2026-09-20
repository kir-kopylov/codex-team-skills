# Хороший Пример: Неоднозначная Публикация

## Вход

«При публикации Workspace Agent API вернул timeout. Проверь, применилось ли изменение, и безопасно продолжи».

## Ожидаемое Поведение

Skill не повторяет publish. Сначала читает deployments, version ids и live, сопоставляет их с pre-release snapshot и requested diff. Если версия существует и live совпадает, продолжает с `VERIFIED`; если publish acknowledged, но live недоступен, фиксирует `PUBLISHED_UNVERIFIED`; если новой версии нет, описывает безопасный retry. Все выводы разделены по provenance.

## Нельзя

Нельзя публиковать повторно до readback, объявлять timeout доказательством провала или обновлять документацию как про live при статусе `PUBLISHED_UNVERIFIED`.
