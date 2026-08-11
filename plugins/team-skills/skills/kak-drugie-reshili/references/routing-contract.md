# Routing Contract

## До Локального Эксперимента

Фраза «не выдумывай, найди описанные людьми решения» без повторного local no-outcome маршрутизируется в `kak-drugie-reshili`.

Нельзя выдумывать `state_fingerprint`, `closed_branch` или `same_state_count`, которых пользователь не предоставил.

## После Повторного Провала

Если есть current state и не менее двух одинаковых `failed` или `partial` на одном слое, задачу принимает `stuck-troubleshooting-reframe`.

Если новые гипотезы по контракту обязаны иметь внешнее происхождение:

1. stuck skill фиксирует fingerprint и закрывает ветку;
2. формирует один ограниченный research question;
3. builder возвращает внешний candidate packet;
4. stuck skill, а не builder, проектирует локальный pivot, observable, rollback и stop condition.

## Другие Маршруты

- Одна точная ссылка для проверки — обычная проверка источника.
- Текущая цена, наличие или доступность — живая проверка через официальный канал.
- Очевидная failing assertion с одним следующим тестом — обычная диагностика.
- Уже выполняемый эксперимент — экспериментальный процесс, не builder.

## Regression Cases

1. Source-first без attempts → builder.
2. Два одинаковых timeout с новыми логами → stuck.
3. Два провала плюс обязательное внешнее происхождение → stuck → builder → stuck.
4. Один симптом и просьба «как другие решали» → builder, не stuck.
5. Точная failing assertion и очевидный тест → ни один из двух skills.
