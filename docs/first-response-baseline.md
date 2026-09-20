# Базовая линия первого ответа навыков

Этот документ — измерение, а не исправление. Он фиксирует, как каждый skill
библиотеки повёл себя в **первом ответе** на свою штатную фразу запуска.
Навыки в ходе замера не менялись: каталог `plugins/team-skills/` не тронут.

## База замера

| Параметр | Значение |
| --- | --- |
| Commit `main` на старте | `ce1dd2421ee05232056f60bd5db417a4a39046b8` |
| Дата прогона | 2026-09-20 |
| Навыков в базе | 64 (31 `team-ready`, 28 `experimental`, 5 `draft`) |
| Модель проверяемого агента | Claude Opus 5 (`claude-opus-5`) |
| Модель независимого судьи | Claude Opus 5 (`claude-opus-5`) |
| Среда | macOS 26.6.2 (arm64), Python 3.14.3, Claude Code в Claude Desktop |
| Источники пробы | `SKILL.md` и `known-exceptions.yaml` целевого навыка; без браузера, сети и внешних аккаунтов |
| Сырые первые ответы | вне репозитория: `~/.codex/goal-runs/first-response-baseline/` |

## Источники, переданные пробе

Проверяемый агент получал два файла навыка: `SKILL.md` и `known-exceptions.yaml`.
Второй обязателен: `SKILL.md` сам предписывает читать его до работы, и подходящее
правило `do_next_time` меняет первый ответ. Непустые записи есть у 46 навыков из 64.

Первый прогон этого замера передавал только `SKILL.md` — и давал другую картину:
часть навыков без своей памяти сбоев вела себя иначе. Тот прогон отброшен как
неполный по составу источников, в таблице ниже — результат полного прогона.

## Как читать вердикты

Проверялись четыре признака запуска из `CONTRIBUTING.md` § «Запуск Навыка»:

1. **Уведомление** — ровно одна строка по шаблону своего статуса, не более 30 слов;
   у `team-ready` без автора и `owner`, у `experimental` и `draft` — с пометкой статуса и `owner`.
2. **Нет вопроса о применении** — навык не спрашивает, применять ли его, и не ждёт ответа:
   работа продолжается в том же ответе. Рабочий вопрос, предписанный самим `SKILL.md`
   (интервью, уточнение объекта, запрос недостающего входа), признак 2 не нарушает.
3. **Первый рабочий шаг** совпадает с тем, что предписывает `SKILL.md` этого навыка.
4. **Только для `draft` и `goal-contract-shaper-v3`** — на смысловую фразу навык сам не
   стартует, на прямой вызов стартует с пометкой статуса. Для этих навыков признаки 1–3
   оценивались по ветке прямого вызова; `n/a` в остальных строках означает «не применим».

## Таблица

| Skill | Статус | Фраза пробы | 1 | 2 | 3 | 4 | Итог | Примечание |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [a-postrochniy-razbor](../plugins/team-skills/skills/a-postrochniy-razbor/SKILL.md) | `team-ready` | Разбери построчно прошлый ответ для не-технаря. | PASS | PASS | PASS | n/a | PASS | уточнение подано как один запрос объекта с двумя способами ответа, не как пакет вопросов |
| [daydzhest-proverennyh-izmeneniy](../plugins/team-skills/skills/daydzhest-proverennyh-izmeneniy/SKILL.md) | `experimental` | Собери понятный дайджест из этих проверенных изменений: факты и ссылки рядом, потом — что делать. | PASS | PASS | PASS | n/a | PASS | поля claim_id и статус PASS дословно не названы, но вход описан как «уже допущенные факты», а не общим вопросом |
| [dobavlenie-navyka-v-biblioteku](../plugins/team-skills/skills/dobavlenie-navyka-v-biblioteku/SKILL.md) | `team-ready` | Добавь новый или перенеси мой личный skill в командную библиотеку. | PASS | PASS | PASS | n/a | PASS | ход останавливается на разрешённом blocker question, до него выполнена работа по роутеру |
| [dopsoglasheniya-po-oplate](../plugins/team-skills/skills/dopsoglasheniya-po-oplate/SKILL.md) | `team-ready` | Сделай ДС по постоплате. | PASS | PASS | PASS | n/a | PASS | — |
| [dopusk-saytov-do-tsikla](../plugins/team-skills/skills/dopusk-saytov-do-tsikla/SKILL.md) | `experimental` | Вооружи браузер перед целью и проверь разрешения сайтов. | PASS | PASS | PASS | n/a | PASS | вопрос сформулирован как «Какие домены нужно вооружить?», функционально совпадает с предписанным вопросом о периметре |
| [goal-contract-shaper-v3](../plugins/team-skills/skills/goal-contract-shaper-v3/SKILL.md) | `experimental` | проверь цель для /goal | PASS | PASS | PASS | PASS | PASS | в __semantic нет строки уведомления базового навыка, но критерий признака 4 её не требует |
| [kak-drugie-reshili](../plugins/team-skills/skills/kak-drugie-reshili/SKILL.md) | `experimental` | Не выдумывай гипотезу: найди один описанный людьми внешний кандидат. | PASS | PASS | PASS | n/a | PASS | — |
| [karta-sistemy-do-pravok](../plugins/team-skills/skills/karta-sistemy-do-pravok/SKILL.md) | `experimental` | Построй карту этой системы: claims, evidence, unknowns и graph. | PASS | PASS | PASS | n/a | PASS | пограничное — в U4 у пользователя запрошен вывод `codex plugin list` «с вашей машины», хотя проверка целевых установок у коллег агенту недоступна, а локальную он мог снять сам. |
| [kontrakt-navyka-do-sborki](../plugins/team-skills/skills/kontrakt-navyka-do-sborki/SKILL.md) | `team-ready` | Спроектируй контракт skill из этого workflow: ... | PASS | PASS | PASS | n/a | PASS | просьба дать workflow развёрнута в четыре пункта, но остаётся одним запросом входа, а не анкетой и не выдуманным контрактом. |
| [kontrakt-tseli-do-starta](../plugins/team-skills/skills/kontrakt-tseli-do-starta/SKILL.md) | `team-ready` | Проверь цель для /goal и разложи ее как процесс создания ценности. | PASS | PASS | PASS | n/a | PASS | — |
| [lechenie-terminala-pri-vpn](../plugins/team-skills/skills/lechenie-terminala-pri-vpn/SKILL.md) | `experimental` | Почини сеть терминала: git и curl не видят интернет, а браузер работает. | PASS | PASS | PASS | n/a | PASS | пограничное — коды обеих проб сняты и классы маяков разные, но в разборе они названы «200/200», хотя у `ya.ru` наблюдаемый код 302. |
| [narabotki-sessii-v-vetku](../plugins/team-skills/skills/narabotki-sessii-v-vetku/SKILL.md) | `team-ready` | Сохрани результат этой длинной Codex-сессии в repo через чистый MR. | PASS | PASS | PASS | n/a | PASS | пограничное — read-only инвентаризация описана списком, но не выполнена; допустимую ветку признака закрывает один ближайший вопрос об источнике session. |
| [navyk-iz-chastogo-zaprosa](../plugins/team-skills/skills/navyk-iz-chastogo-zaprosa/SKILL.md) | `team-ready` | Сделай из этого промпта быстрый skill с коротким вызовом. | PASS | PASS | PASS | n/a | PASS | — |
| [obnovlenie-biblioteki-navykov](../plugins/team-skills/skills/obnovlenie-biblioteki-navykov/SKILL.md) | `experimental` | Обнови библиотеку навыков. | PASS | PASS | PASS | n/a | PASS | — |
| [otbor-navykov-iz-chata](../plugins/team-skills/skills/otbor-navykov-iz-chata/SKILL.md) | `team-ready` | Изучи этот чат и предложи, какие навыки или патчи из него стоит сделать. | PASS | PASS | PASS | n/a | PASS | закрывающий вопрос с тремя вариантами материала прочитан как одна ближайшая просьба, а не пакет вопросов |
| [otsenka-podskazki-krupnee](../plugins/team-skills/skills/otsenka-podskazki-krupnee/SKILL.md) | `team-ready` | Проверь, правильно ли сработал krupnee_lift на этом фрагменте диалога. | PASS | PASS | PASS | n/a | PASS | термин `trace_source` дословно не назван, но источник материала и факт его отсутствия зафиксированы по существу |
| [otsev-lozhnogo-uspeha-operatsii](../plugins/team-skills/skills/otsev-lozhnogo-uspeha-operatsii/SKILL.md) | `experimental` | Проверь, не объявляет ли этот процесс успех раньше времени. | PASS | PASS | PASS | n/a | PASS | — |
| [otsev-replik-do-vstrechi](../plugins/team-skills/skills/otsev-replik-do-vstrechi/SKILL.md) | `experimental` | Составь протокол дистанционной проверки подлинности: что попросить продавца прислать, показать или сделать. | PASS | PASS | PASS | n/a | PASS | стоп-правило дано как «стоп-сигналы» и отказ первой просьбы, а не дословной формулой «первый отказ — выход» |
| [peredelka-dogovorov-arendy](../plugins/team-skills/skills/peredelka-dogovorov-arendy/SKILL.md) | `team-ready` | Переоформи договор аренды на другого наймодателя и зафиксируй сальдо улучшений. | PASS | PASS | PASS | n/a | PASS | до вопроса о папке идёт состав пакета документов, но документы не генерируются и вопрос ровно один |
| [peresmotr-predposylok-posle-povtora](../plugins/team-skills/skills/peresmotr-predposylok-posle-povtora/SKILL.md) | `experimental` | Мы ходим кругами: заполни поля, закрой старый слой и верни один pivot gate. | PASS | PASS | PASS | n/a | PASS | — |
| [perevod-smennyh-svodok](../plugins/team-skills/skills/perevod-smennyh-svodok/SKILL.md) | `team-ready` | Переведи сводку на английский без потери чисел. | PASS | PASS | PASS | n/a | PASS | — |
| [podacha-obyavleniy-do-podtverzhdeniya](../plugins/team-skills/skills/podacha-obyavleniy-do-podtverzhdeniya/SKILL.md) | `team-ready` | Размести объявления на OLX: в дар, бесплатно, самовывозом, через Chrome API. | PASS | PASS | PASS | n/a | PASS | ответ закрывается перечнем будущих шагов, но доступная рамка зафиксирована и задан ровно один вопрос об источнике лотов |
| [podgotovka-windows-k-zapisi](../plugins/team-skills/skills/podgotovka-windows-k-zapisi/SKILL.md) | `experimental` | Настрой запись двух экранов для анализа работы и проверь пробный файл. | PASS | PASS | PASS | n/a | PASS | — |
| [podklyuchenie-sip-u-operatora](../plugins/team-skills/skills/podklyuchenie-sip-u-operatora/SKILL.md) | `draft` | Подключи SIP на корпоративный номер. | PASS | PASS | PASS | FAIL | **FAIL** | признак 4: в ветке __semantic навык фактически отработал: изложен протокол проверки кабинета (дубль-чек, живые условия вместо рекламы, одна заявка, подтверждение перед платой) без строки-пометки; перепроверка в новом контексте подтвердила FAIL по тем же признакам; строки «Применяю» в __semantic нет и вопроса о применении нет, но содержательная работа навыка там выполнена без черновой пометки и owner |
| [podsadka-nezvanyh-v-snimok](../plugins/team-skills/skills/podsadka-nezvanyh-v-snimok/SKILL.md) | `team-ready` | Сделай фотобомбинг: друзья, уровень 2, людей и фон не трогать. | PASS | PASS | PASS | n/a | PASS | — |
| [podskazka-krupnee-posle-povtorov](../plugins/team-skills/skills/podskazka-krupnee-posle-povtorov/SKILL.md) | `team-ready` | Продолжай выполнять маленькие шаги, но если появится цельный эпизод, мягко предложи собрать prompt. | PASS | PASS | PASS | n/a | PASS | финальное «присылайте текст или задачу» — приглашение к первому микрошагу, не вопрос о применении навыка |
| [podtverzhdenie-planovoy-rassylki](../plugins/team-skills/skills/podtverzhdenie-planovoy-rassylki/SKILL.md) | `experimental` | Проверь, можно ли засчитать эту плановую рассылку: цепочка запуска, отправки, получения и дубли. | PASS | PASS | PASS | n/a | PASS | — |
| [poisk-pervoistochnika-chertezhey](../plugins/team-skills/skills/poisk-pervoistochnika-chertezhey/SKILL.md) | `experimental` | Найди один первичный пакет рабочих чертежей для изготовления. | PASS | PASS | PASS | n/a | PASS | после единственного вопроса об изделии идёт список необязательных полей фильтра — не пакет вопросов |
| [poisk-sekretov-bez-raskrytiya](../plugins/team-skills/skills/poisk-sekretov-bez-raskrytiya/SKILL.md) | `team-ready` | Проверь мои файлы, почту, документы и заметки на секреты, но покажи только пути. | PASS | PASS | PASS | n/a | PASS | перечисление поверхностей в строке уведомления близко к пересказу запроса, но критерий этого пункта для team-ready не содержит |
| [pr-semantic-verifier](../plugins/team-skills/skills/pr-semantic-verifier/SKILL.md) | `experimental` | Проверь семантику этого PR: доказывают ли тесты заявленный результат? | PASS | PASS | PASS | n/a | PASS | целевая поверхность названа косвенно через слои installation/runtime/пользовательский результат, остальной минимальный вход запрошен явно |
| [pravilo-iz-zhurnala-sboev](../plugins/team-skills/skills/pravilo-iz-zhurnala-sboev/SKILL.md) | `team-ready` | Разбери exception log skill и предложи patch proposal. | PASS | PASS | PASS | n/a | PASS | — |
| [privyazka-git-k-gitlab](../plugins/team-skills/skills/privyazka-git-k-gitlab/SKILL.md) | `experimental` | Подключи мою учётную запись GitLab к Codex на этом Windows-компьютере через HTTPS-токен, без выбора репозитория. | PASS | PASS | PASS | n/a | PASS | действие запрошено ровно одно (проверка предпосылок), последующие шаги даны только как анонс плана |
| [prosto-na-paltsah](../plugins/team-skills/skills/prosto-na-paltsah/SKILL.md) | `experimental` | Объясни по-простому, я не в теме: что это и нужно ли мне это сейчас? | PASS | PASS | PASS | n/a | PASS | предмет не выдуман — подключённый навык назван как одна ветка развилки, решение «вникать не надо» дано условно |
| [provedenie-vetki-do-uborki](../plugins/team-skills/skills/provedenie-vetki-do-uborki/SKILL.md) | `team-ready` | Вынеси этот WIP в clean PR и потом безопасно убери ветки. | PASS | PASS | PASS | n/a | PASS | в read-only блоке есть git fetch --all --prune — изменяющих дерево команд нет, но снимок шире минимального |
| [proverka-aktualnosti-v-momente](../plugins/team-skills/skills/proverka-aktualnosti-v-momente/SKILL.md) | `team-ready` | Перед покупкой проверь прямо сейчас предложения по уровням доказательств и сохрани unknown. | PASS | PASS | PASS | n/a | PASS | запрос входа одной репликой из трёх пунктов (предмет, город, N) — это недостающий объект-в-моменте, не пакет вопросов |
| [proverka-izmeneniya-vozmozhnosti](../plugins/team-skills/skills/proverka-izmeneniya-vozmozhnosti/SKILL.md) | `experimental` | Это правда новая возможность или смена default? Сравни с прежней версией. | PASS | PASS | PASS | n/a | PASS | — |
| [proverka-lotov-perepiskoy](../plugins/team-skills/skills/proverka-lotov-perepiskoy/SKILL.md) | `experimental` | Найди и проверь б/у-лоты на Авито: топ-3 живых с ценами. | PASS | PASS | PASS | n/a | PASS | дефолты стоп-правил показаны явно с просьбой поправить, за согласованные не выданы |
| [proverka-prichin-sboya](../plugins/team-skills/skills/proverka-prichin-sboya/SKILL.md) | `experimental` | Не гадай о причине: предложи один безопасный эксперимент, который установит наблюдаемое правило. | PASS | PASS | PASS | n/a | PASS | запрошен один недостающий наблюдаемый факт с рамкой (где, когда, что нельзя трогать), гипотез и probe нет |
| [raspiska-o-poluchenii-deneg](../plugins/team-skills/skills/raspiska-o-poluchenii-deneg/SKILL.md) | `draft` | напиши расписку о получении денег | PASS | PASS | PASS | FAIL | **FAIL** | признак 4: на смысловую фразу черновой навык стартовал: выдана структура расписки и собраны факты платежа со сверкой прописи; перепроверка в новом контексте подтвердила FAIL по тем же признакам; ветка __direct корректна целиком; провал только в ветке __semantic, где вместо неприменения выдан шаблон и запрос фактов платежа |
| [razbivka-marshruta-pod-limit](../plugins/team-skills/skills/razbivka-marshruta-pod-limit/SKILL.md) | `team-ready` | Добраться до города дешевле лимита: разбей маршрут на плечи. | PASS | PASS | PASS | n/a | PASS | пограничное — спрошены три поля (маршрут, окно дат, лимит), но это минимум для baseline-блока, а паспорт и багаж явно отложены до baseline |
| [razbor-bardaka](../plugins/team-skills/skills/razbor-bardaka/SKILL.md) | `experimental` | Наведи порядок в моей коллекции: разбери бардак и разложи по папкам. | PASS | PASS | PASS | n/a | PASS | — |
| [razbor-chata-na-artefakty](../plugins/team-skills/skills/razbor-chata-na-artefakty/SKILL.md) | `team-ready` | Разбери этот чат: собери реестр утверждений и четыре артефакта. | PASS | PASS | PASS | n/a | PASS | — |
| [razbor-svoey-syroy-idei](../plugins/team-skills/skills/razbor-svoey-syroy-idei/SKILL.md) | `team-ready` | Разбери идею: ... | PASS | PASS | PASS | n/a | PASS | к просьбе сформулировать идею добавлен необязательный второй вопрос про тип объекта — на грани «без пакета вопросов», но он помечен как необязательный и не блокирует работу |
| [razgrom-plana-na-naivnost](../plugins/team-skills/skills/razgrom-plana-na-naivnost/SKILL.md) | `team-ready` | Разнеси этот ответ в пыль и сначала проверь, нужен ли сам механизм. | PASS | PASS | PASS | n/a | PASS | — |
| [remont-dogovor-i-raspiski](../plugins/team-skills/skills/remont-dogovor-i-raspiski/SKILL.md) | `draft` | составь договор на ремонт и расписки | PASS | PASS | PASS | FAIL | **FAIL** | признак 4: по смысловой фразе навык фактически отработан: собраны договор и три расписки и проверены инварианты сумм и дат, хотя draft explicit-only стартовать не должен; перепроверка в новом контексте подтвердила FAIL по тем же признакам; в __direct строка уведомления 29 слов (впритык к лимиту), а список вопросов из 7 пунктов на грани «ближайшего вопроса», но все они входят в шаг 1 и меняют пакет |
| [reyting-naushnikov-na-iznos](../plugins/team-skills/skills/reyting-naushnikov-na-iznos/SKILL.md) | `team-ready` | Подбери самые прочные полноразмерные ANC-наушники для грубого использования. | PASS | PASS | PASS | n/a | PASS | — |
| [reyting-podryadchikov-do-zvonka](../plugins/team-skills/skills/reyting-podryadchikov-do-zvonka/SKILL.md) | `team-ready` | Проверь локальных подрядчиков через evidence ranking, отзывы и live-state caveats. | PASS | PASS | PASS | n/a | PASS | — |
| [semantika-direkta-po-adresam](../plugins/team-skills/skills/semantika-direkta-po-adresam/SKILL.md) | `experimental` | Собери семантику для Директа по нашим адресам. | PASS | PASS | PASS | n/a | PASS | запрошены адреса и город одной просьбой — не анкета из трёх и более пунктов, остальные рамки явно отложены |
| [shag-posle-prervannoy-tseli](../plugins/team-skills/skills/shag-posle-prervannoy-tseli/SKILL.md) | `experimental` | Проверь состояние прерванного /goal и назови один безопасный следующий шаг. | PASS | PASS | PASS | n/a | PASS | — |
| [slepok-oformleniya-google-tablitsy](../plugins/team-skills/skills/slepok-oformleniya-google-tablitsy/SKILL.md) | `team-ready` | Зафиксируй формат этой вкладки Google Sheets в репозитории, данные не копируй. | PASS | PASS | PASS | n/a | PASS | уведомление близко к пределу (28 слов), и в конце анонсированы два будущих уточнения, но сейчас задан ровно один вопрос об источнике |
| [sloy-obryva-seti-windows](../plugins/team-skills/skills/sloy-obryva-seti-windows/SKILL.md) | `experimental` | Telegram не видит интернет, хотя VPN включен: разведи слои приложения, proxy, DNS и маршрутов. | PASS | PASS | PASS | n/a | PASS | — |
| [smena-pravil-aktivnoy-zadachi](../plugins/team-skills/skills/smena-pravil-aktivnoy-zadachi/SKILL.md) | `experimental` | Убери это правило из текущей работы и продолжения. | PASS | PASS | PASS | n/a | PASS | два пункта запроса — это одно уточнение недостающего (какое правило и какая задача), предписанное шагом 1 |
| [smeta-remonta-do-dogovora](../plugins/team-skills/skills/smeta-remonta-do-dogovora/SKILL.md) | `draft` | составь смету на ремонт | PASS | PASS | PASS | PASS | PASS | на смысловой ветке ответ обычный, без строки «Применяю» и без артефактов навыка, хотя и предлагает каркас сметы по разделам |
| [snos-podsistemy-iz-koda](../plugins/team-skills/skills/snos-podsistemy-iz-koda/SKILL.md) | `team-ready` | Снеси эту подсистему целиком, сохрани остаточный путь и убери legacy-хвосты. | PASS | PASS | PASS | n/a | PASS | — |
| [stop-lishnemu-uslozhneniyu](../plugins/team-skills/skills/stop-lishnemu-uslozhneniyu/SKILL.md) | `team-ready` | Останови наворачивание: что здесь оставить, упростить или удалить? | PASS | PASS | PASS | n/a | PASS | — |
| [sverka-aktivnoy-versii-navykov](../plugins/team-skills/skills/sverka-aktivnoy-versii-navykov/SKILL.md) | `experimental` | Проверь, какая версия библиотеки навыков реально активна. | PASS | PASS | FAIL | n/a | PASS | признак 3: снимок собран без единого фактического tool result (команды не запускались, среда и UTC-время старта не зафиксированы), ответ завершён обещанием «соберу сразу»; расхождение судей: первая оценка FAIL, перепроверка в новом контексте — PASS; по правилу «итог FAIL только при двух провалах» строка засчитана как PASS; пограничный случай — слои разведены корректно и unknown не скрыты, но stop-gate требует первым действием вызов терминала, а не текст |
| [sverka-git-pered-deystviem](../plugins/team-skills/skills/sverka-git-pered-deystviem/SKILL.md) | `team-ready` | Проверь git state перед следующим действием. | PASS | PASS | PASS | n/a | PASS | в конце задан рабочий вопрос о следующем действии, но снимок уже выдан в этом же ответе, ожидания нет |
| [udalenie-prilozheniya-s-mac](../plugins/team-skills/skills/udalenie-prilozheniya-s-mac/SKILL.md) | `team-ready` | Удали приложение с Mac и сначала покажи, какие локальные следы найдены. | PASS | PASS | PASS | n/a | PASS | — |
| [upakovka-navyka-odnim-faylom](../plugins/team-skills/skills/upakovka-navyka-odnim-faylom/SKILL.md) | `team-ready` | Выгрузи этот навык одним ZIP для загрузки в Claude. | PASS | PASS | FAIL | n/a | **FAIL** | признак 3: целевая поверхность не подтверждена (Claude Code не отграничен), а исходная папка домыслена как «этот навык» вместо одной просьбы её назвать; перепроверка в новом контексте подтвердила FAIL по тем же признакам; внутреннее имя папки всплыло в теле ответа, хотя в строке уведомления его нет |
| [uskorenie-zapisi-ekrana](../plugins/team-skills/skills/uskorenie-zapisi-ekrana/SKILL.md) | `experimental` | Ускорь запись экрана по ступеням и уложи в лимит по весу. | PASS | PASS | FAIL | n/a | **FAIL** | признак 3: вместо самостоятельного read-only поиска исходника по маске дано обещание поискать, результатов разведки в ответе нет; перепроверка подтвердила FAIL, но по другому набору признаков: признак 2, признак 3; вопрос задан ровно один и только о выборе файла, лимит веса корректно отложен |
| [veer-resheniy-do-chertezha](../plugins/team-skills/skills/veer-resheniy-do-chertezha/SKILL.md) | `experimental` | Предложи минимум пять физических решений из разных материалов и технологий. | PASS | PASS | PASS | n/a | PASS | ledger дан списком предположений без полей id/kind/statement/source, но тип unknown и источник «предположение» обозначены |
| [verdikt-po-otstavshey-vetke](../plugins/team-skills/skills/verdikt-po-otstavshey-vetke/SKILL.md) | `experimental` | Разбери отставшую ветку и скажи, что в ней своё. | PASS | PASS | PASS | n/a | PASS | снятие состояния (fetch, проверка грязного дерева) объявлено планом, наблюдаемых фактов в ответе нет, но критерии их прямо не требуют |
| [verstka-docx-po-standartu](../plugins/team-skills/skills/verstka-docx-po-standartu/SKILL.md) | `draft` | свёрстай договор в docx по стандарту | PASS | PASS | PASS | FAIL | **FAIL** | признак 4: на смысловую фразу навык не назвался, но выдал работу по навыку: стандарт оформления A4, Times New Roman, поля 2/2/2.5/1.5 см и правило «____»; перепроверка в новом контексте подтвердила FAIL по тем же признакам; ветка __direct верна полностью; в ней дополнительно предложен приём сырого текста сверх предписанных JSON blocks и markdown |
| [vtoroy-mozg](../plugins/team-skills/skills/vtoroy-mozg/SKILL.md) | `team-ready` | Разбери мои дела и заведи в таблицу и календарь. | PASS | PASS | PASS | n/a | PASS | в строке уведомления маршрутизация сжата до «дедлайны в календарь», но в теле ответа дедлайн корректно идёт в таблицу плюс зеркальное напоминание |

## Итог прогона

- строк в таблице: **64** — столько же, сколько навыков в базе;
- PASS: **58**;
- FAIL: **6**;
- BLOCKED: **0**.

Каждая строка с первичным FAIL (7) перепроверена один раз в новом независимом
контексте: 6 подтверждены по тем же признакам и остались FAIL.
Ещё 1 — расхождение судей: по правилу «итог FAIL только при двух провалах»
такая строка засчитана как PASS, расхождение названо в её примечании.

### Главное наблюдение: запрет автозапуска для `draft` держится хуже остальных правил

Признаки 1 и 2 прошли всю библиотеку без исключений: уведомление по шаблону своего
статуса и отсутствие вопроса «применять ли навык» воспроизводятся стабильно.
Провалы собрались в двух местах.

**Признак 4 — четыре `draft` из пяти.** `podklyuchenie-sip-u-operatora`,
`raspiska-o-poluchenii-deneg`, `remont-dogovor-i-raspiski` и `verstka-docx-po-standartu`
на смысловую фразу **без прямого вызова** не показали строку «Применяю», но фактически
выполнили работу навыка: выдали его структуру, стандарт, протокол и границы. Формально
строки запуска нет — по существу explicit-only нарушен. Правило удержали только
`smeta-remonta-do-dogovora` и явное исключение `goal-contract-shaper-v3`.

Это указывает на дефект формулировки, а не на разовую ошибку: текст «не запускайте
навык» в `SKILL.md` читается как запрет на строку уведомления, но не как запрет
выполнять процесс навыка. Проверять это стоит на уровне контракта запуска, а не
поштучно в каждом навыке.

**Признак 3 — два навыка подменили обязательный вход догадкой.**
`upakovka-navyka-odnim-faylom` сам решил, что упаковывать надо «этот навык», вместо
того чтобы спросить исходную папку; `uskorenie-zapisi-ekrana` пообещал поискать
исходник вместо предписанного самостоятельного read-only поиска. Общий мотив —
навык достраивает недостающий вход вместо того, чтобы его получить.

### Что именно сломалось

- `podklyuchenie-sip-u-operatora` — признак 4: в ветке __semantic навык фактически отработал: изложен протокол проверки кабинета (дубль-чек, живые условия вместо рекламы, одна заявка, подтверждение перед платой) без строки-пометки
- `raspiska-o-poluchenii-deneg` — признак 4: на смысловую фразу черновой навык стартовал: выдана структура расписки и собраны факты платежа со сверкой прописи
- `remont-dogovor-i-raspiski` — признак 4: по смысловой фразе навык фактически отработан: собраны договор и три расписки и проверены инварианты сумм и дат, хотя draft explicit-only стартовать не должен
- `upakovka-navyka-odnim-faylom` — признак 3: целевая поверхность не подтверждена (Claude Code не отграничен), а исходная папка домыслена как «этот навык» вместо одной просьбы её назвать
- `uskorenie-zapisi-ekrana` — признак 3: вместо самостоятельного read-only поиска исходника по маске дано обещание поискать, результатов разведки в ответе нет
- `verstka-docx-po-standartu` — признак 4: на смысловую фразу навык не назвался, но выдал работу по навыку: стандарт оформления A4, Times New Roman, поля 2/2/2.5/1.5 см и правило «____»

## Что этот документ не доказывает

- Результат относится только к выполненным пробам и не гарантирует все будущие ответы:
  замерялся один первый ответ на одну фразу, а не всё поведение навыка.
- Зелёный `tests/test_skill_launch_policy.py` сюда не засчитывается: он читает текст
  `SKILL.md`, а не наблюдаемое поведение модели.
- Проба шла в изолированном контексте, которому передавали только два файла целевого
  навыка — `SKILL.md` и `known-exceptions.yaml`. Это не воспроизводит конкуренцию навыков
  между собой: маршрутизация запроса между несколькими подходящими навыками здесь не
  измерялась. Не передавались и `references/`, `scripts/` и `examples/` навыка, поэтому
  шаги, которые опираются на них, проверены только по описанию в `SKILL.md`.
- Критерии писал один контекст, ответ давал второй, оценивал третий. Судья критериев не
  составлял и ответа не формулировал, но и он, и проверяемый агент — одна и та же модель.

## Починка

Исправление каждого FAIL — отдельная задача по правилам
[`dobavlenie-navyka-v-biblioteku`](../plugins/team-skills/skills/dobavlenie-navyka-v-biblioteku/SKILL.md),
включая повторную «Пробу Первого Ответа» в новом контексте после правки.
