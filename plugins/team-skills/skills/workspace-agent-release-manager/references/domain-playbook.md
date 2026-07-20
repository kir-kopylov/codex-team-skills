# Domain Playbook

## Что Нельзя Потерять

- Workspace Agent имеет как минимум раздельные состояния draft, published deployment и фактический live.
- Раздел `Автоматизации` или аналогичный schedule API показывает живые расписания отдельно от текста инструкций.
- У schedule важны stable id, timezone, cadence, enabled state и target agent/version, если интерфейс их раскрывает.
- `Приложения` или connector settings подтверждают конфигурацию интеграции, но не гарантируют успешный runtime action.
- Кнопка или API `Publish` может подтвердить приём операции до доступности live readback.
- Recovery documentation описывает прошлое подтверждённое состояние и не заменяет свежий config read.
- Workspace Agent и обычная Codex scheduled task — разные типы автоматизации; не конвертируйте один в другой по догадке.
- После каждого mutation нужен независимый readback той поверхности, которая менялась.

## Что Надо Обезличить

- реальные agent, deployment, version, schedule и connector ids;
- account labels, адреса email, телефоны, имена и списки получателей;
- ссылки на рабочие Drive/Docs/Sheets и внутренние папки;
- полный prompt, если он содержит частные правила или персональные данные;
- screenshots, raw chat, browser profile paths, cookies и OAuth metadata;
- названия внутренних процессов, клиентов и организаций, не нужные механике релиза.

В examples используйте роли вроде «основной получатель», `AGENT_ID`, `VERSION_ID` и synthetic schedule. Механику сохраняйте, частные значения заменяйте.

## Interface Mechanics

1. Начинайте с purpose-built Workspace Agent API или connector.
2. Получайте current config перед каждой mutation, особенно перед full prompt replacement.
3. Читайте draft и latest published deployment как отдельные объекты.
4. Читайте `Автоматизации` или schedule endpoint отдельно; текст времени в instructions не является schedule evidence.
5. После draft mutation используйте config readback, а не только success toast.
6. После `Publish` сохраните version id и откройте live representation заново.
7. При изменении apps проверяйте только configuration state; runtime-пробу выполняйте лишь с отдельным разрешением на side effect.
8. Browser fallback начинается с точной страницы target agent и pre-action screenshot/readback, затем заканчивается refresh и повторной проверкой.
9. Документацию синхронизируйте после live verification и помечайте provenance.

Не фиксируйте selectors, URL или название кнопки как вечный контракт, если они не подтверждены текущим интерфейсом. При изменении UI обновляйте playbook по свежему evidence.

## Recovery And Edge Cases

### Current Config Недоступен

Сделайте до трёх bounded read attempts. Не стройте полный replacement по docs. Итог — `BLOCKED_PRECHECK` и одно условие возобновления.

### Publish Вернул Timeout

Не нажимайте publish повторно. Сначала re-list deployments и прочитайте live version. Если новая версия найдена, продолжайте verification; если результат не читается, используйте `PUBLISHED_UNVERIFIED`.

### Draft И Live Расходятся

Не переписывайте draft автоматически. Сравните version ids и выясните, какой deployment сейчас live. Исправление требует нового approved diff.

### Schedule Задублировался

Не удаляйте «лишний» объект по времени или имени. Сначала сопоставьте stable ids, creation/update metadata и target version; удаление требует отдельного разрешения.

### Connector Потерял Авторизацию

Остановите repeated writes, запросите штатное reconnect и после него начните со fresh read. Browser не является автоматическим обходом connector failure.

### Browser Не Даёт Проверить Сохранение

Не объявляйте success по одному toast или визуальному изменению поля. Используйте `PUBLISHED_UNVERIFIED` либо ближайший incomplete status и назовите необходимый machine/readback check.

### Документ И Live Противоречат Друг Другу

Свежий live имеет более высокий evidence rank. Исправьте документ только при разрешении, сохраните verified timestamp и не скрывайте ранее обнаруженное расхождение в release report.
