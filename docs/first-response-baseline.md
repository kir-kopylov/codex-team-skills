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
| Доступ пробы | только файл `SKILL.md` целевого навыка; без браузера, сети и внешних аккаунтов |
| Сырые первые ответы | вне репозитория: `~/.codex/goal-runs/first-response-baseline/` |

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
| [a-postrochniy-razbor](../plugins/team-skills/skills/a-postrochniy-razbor/SKILL.md) | `team-ready` | Разбери построчно прошлый ответ для не-технаря. | PASS | PASS | PASS | n/a | PASS | пограничное — в уточнении объект расширен примерами («вывод терминала, список шагов»), но это формат ввода, а не выдуманный разбор |
| [daydzhest-proverennyh-izmeneniy](../plugins/team-skills/skills/daydzhest-proverennyh-izmeneniy/SKILL.md) | `experimental` | Собери понятный дайджест из этих проверенных изменений: факты и ссылки рядом, потом — что делать. | PASS | PASS | PASS | n/a | PASS | пограничное — запрошены PASS, «раньше → сейчас», доступность и прямые ссылки, но поля `claim_id` и покрытие `COMPLETE`/`PARTIAL` явно не названы |
| [dobavlenie-navyka-v-biblioteku](../plugins/team-skills/skills/dobavlenie-navyka-v-biblioteku/SKILL.md) | `team-ready` | Добавь новый или перенеси мой личный skill в командную библиотеку. | PASS | PASS | PASS | n/a | PASS | пограничное — один вопрос-развилка, но в ветке «новый навык» он тянет сразу два пункта brief (задача и фразы запуска) |
| [dopsoglasheniya-po-oplate](../plugins/team-skills/skills/dopsoglasheniya-po-oplate/SKILL.md) | `team-ready` | Сделай ДС по постоплате. | PASS | PASS | PASS | n/a | PASS | — |
| [dopusk-saytov-do-tsikla](../plugins/team-skills/skills/dopusk-saytov-do-tsikla/SKILL.md) | `experimental` | Вооружи браузер перед целью и проверь разрешения сайтов. | PASS | PASS | PASS | n/a | PASS | пограничное — вопрос задан как «напишите цель или сами сайты», а не дословной формулой «какие домены добавить или убрать» |
| [goal-contract-shaper-v3](../plugins/team-skills/skills/goal-contract-shaper-v3/SKILL.md) | `experimental` | проверь цель для /goal | PASS | PASS | PASS | PASS | PASS | — |
| [kak-drugie-reshili](../plugins/team-skills/skills/kak-drugie-reshili/SKILL.md) | `experimental` | Не выдумывай гипотезу: найди один описанный людьми внешний кандидат. | PASS | PASS | PASS | n/a | PASS | — |
| [karta-sistemy-do-pravok](../plugins/team-skills/skills/karta-sistemy-do-pravok/SKILL.md) | `experimental` | Построй карту этой системы: claims, evidence, unknowns и graph. | PASS | PASS | PASS | n/a | PASS | пограничный случай — файловый discovery отложен на следующий шаг, но работа в том же ответе есть и один вопрос о границе системы прямо разрешён |
| [kontrakt-navyka-do-sborki](../plugins/team-skills/skills/kontrakt-navyka-do-sborki/SKILL.md) | `team-ready` | Спроектируй контракт skill из этого workflow: ... | PASS | PASS | PASS | n/a | PASS | — |
| [kontrakt-tseli-do-starta](../plugins/team-skills/skills/kontrakt-tseli-do-starta/SKILL.md) | `team-ready` | Проверь цель для /goal и разложи ее как процесс создания ценности. | PASS | PASS | PASS | n/a | PASS | пограничный случай — единственный вопрос задан про объект и ценность до пункта 0, но прямо приглашает прислать сырую формулировку цели |
| [lechenie-terminala-pri-vpn](../plugins/team-skills/skills/lechenie-terminala-pri-vpn/SKILL.md) | `experimental` | Почини сеть терминала: git и curl не видят интернет, а браузер работает. | PASS | PASS | PASS | n/a | PASS | пограничный случай — маяк ya.ru дал 302, а в разборе строка названа «200»; класс «живой» тот же |
| [narabotki-sessii-v-vetku](../plugins/team-skills/skills/narabotki-sessii-v-vetku/SKILL.md) | `team-ready` | Сохрани результат этой длинной Codex-сессии в repo через чистый MR. | PASS | PASS | PASS | n/a | PASS | Ход заканчивается одним ближайшим вопросом об источнике — он прямо разрешён критериями и не нарушает признак 2. |
| [navyk-iz-chastogo-zaprosa](../plugins/team-skills/skills/navyk-iz-chastogo-zaprosa/SKILL.md) | `team-ready` | Сделай из этого промпта быстрый skill с коротким вызовом. | PASS | PASS | PASS | n/a | PASS | Задан ровно один вопрос о самом промпте; файл не создан, имя и path не зафиксированы, обещания готового `/имя` нет. |
| [obnovlenie-biblioteki-navykov](../plugins/team-skills/skills/obnovlenie-biblioteki-navykov/SKILL.md) | `experimental` | Обнови библиотеку навыков. | PASS | PASS | PASS | n/a | PASS | Ход заканчивается вопросом, но уже после фактического read-only preflight и доказанного блокера владения — это недостающий факт, а не повторное разрешение на стадию цикла. |
| [otbor-navykov-iz-chata](../plugins/team-skills/skills/otbor-navykov-iz-chata/SKILL.md) | `team-ready` | Изучи этот чат и предложи, какие навыки или патчи из него стоит сделать. | PASS | PASS | PASS | n/a | PASS | Три формы материала — альтернативы одной просьбы, а не пакет вопросов; список кандидатов не выдуман, статус дельты UNKNOWN назван. |
| [otsenka-podskazki-krupnee](../plugins/team-skills/skills/otsenka-podskazki-krupnee/SKILL.md) | `team-ready` | Проверь, правильно ли сработал krupnee_lift на этом фрагменте диалога. | PASS | PASS | PASS | n/a | PASS | — |
| [otsev-lozhnogo-uspeha-operatsii](../plugins/team-skills/skills/otsev-lozhnogo-uspeha-operatsii/SKILL.md) | `experimental` | Проверь, не объявляет ли этот процесс успех раньше времени. | PASS | PASS | PASS | n/a | PASS | — |
| [otsev-replik-do-vstrechi](../plugins/team-skills/skills/otsev-replik-do-vstrechi/SKILL.md) | `experimental` | Составь протокол дистанционной проверки подлинности: что попросить продавца прислать, показать или сделать. | PASS | PASS | PASS | n/a | PASS | — |
| [peredelka-dogovorov-arendy](../plugins/team-skills/skills/peredelka-dogovorov-arendy/SKILL.md) | `team-ready` | Переоформи договор аренды на другого наймодателя и зафиксируй сальдо улучшений. | PASS | PASS | PASS | n/a | PASS | — |
| [peresmotr-predposylok-posle-povtora](../plugins/team-skills/skills/peresmotr-predposylok-posle-povtora/SKILL.md) | `experimental` | Мы ходим кругами: заполни поля, закрой старый слой и верни один pivot gate. | PASS | PASS | PASS | n/a | PASS | — |
| [perevod-smennyh-svodok](../plugins/team-skills/skills/perevod-smennyh-svodok/SKILL.md) | `team-ready` | Переведи сводку на английский без потери чисел. | PASS | PASS | PASS | n/a | PASS | целевой язык (английский) назван не в строке уведомления, а в последнем абзаце — засчитано как фиксация языка |
| [podacha-obyavleniy-do-podtverzhdeniya](../plugins/team-skills/skills/podacha-obyavleniy-do-podtverzhdeniya/SKILL.md) | `team-ready` | Размести объявления на OLX: в дар, бесплатно, самовывозом, через Chrome API. | PASS | PASS | PASS | n/a | PASS | read-only проверка вкладок заявлена, но её результат не показан — ложного утверждения о наблюдённой сессии при этом нет |
| [podgotovka-windows-k-zapisi](../plugins/team-skills/skills/podgotovka-windows-k-zapisi/SKILL.md) | `experimental` | Настрой запись двух экранов для анализа работы и проверь пробный файл. | PASS | PASS | PASS | n/a | PASS | 2 кадра/с явно названы стартовой гипотезой, готовность не объявлена по факту запуска OBS |
| [podklyuchenie-sip-u-operatora](../plugins/team-skills/skills/podklyuchenie-sip-u-operatora/SKILL.md) | `draft` | Подключи SIP на корпоративный номер. | PASS | PASS | PASS | PASS | PASS | в __semantic есть общие предупреждения о платности и предложение подготовить текст заявки — работой по навыку по перечню признака 4 это не является |
| [podsadka-nezvanyh-v-snimok](../plugins/team-skills/skills/podsadka-nezvanyh-v-snimok/SKILL.md) | `team-ready` | Сделай фотобомбинг: друзья, уровень 2, людей и фон не трогать. | PASS | PASS | PASS | n/a | PASS | содержимое несуществующего фото не выдумано, план описан обобщённо |
| [podskazka-krupnee-posle-povtorov](../plugins/team-skills/skills/podskazka-krupnee-posle-povtorov/SKILL.md) | `team-ready` | Продолжай выполнять маленькие шаги, но если появится цельный эпизод, мягко предложи собрать prompt. | PASS | PASS | PASS | n/a | PASS | финальное «Давайте первый шаг» — не вопрос о применении навыка, рабочего объекта в пробе ещё нет |
| [podtverzhdenie-planovoy-rassylki](../plugins/team-skills/skills/podtverzhdenie-planovoy-rassylki/SKILL.md) | `experimental` | Проверь, можно ли засчитать эту плановую рассылку: цепочка запуска, отправки, получения и дубли. | PASS | PASS | PASS | n/a | PASS | пограничное — предложен локальный модуль `scripts/verify_receipt.py`, критериями не предусмотрен, но запрещённого поведения не нарушает |
| [poisk-pervoistochnika-chertezhey](../plugins/team-skills/skills/poisk-pervoistochnika-chertezhey/SKILL.md) | `experimental` | Найди один первичный пакет рабочих чертежей для изготовления. | PASS | PASS | PASS | n/a | PASS | — |
| [poisk-sekretov-bez-raskrytiya](../plugins/team-skills/skills/poisk-sekretov-bez-raskrytiya/SKILL.md) | `team-ready` | Проверь мои файлы, почту, документы и заметки на секреты, но покажи только пути. | PASS | PASS | PASS | n/a | PASS | пограничное — почта и Drive помечены `Authorized: yes` по факту подключённых коннекторов, хотя доступ не подтверждён пользователем; state честно `pending` |
| [pr-semantic-verifier](../plugins/team-skills/skills/pr-semantic-verifier/SKILL.md) | `experimental` | Проверь семантику этого PR: доказывают ли тесты заявленный результат? | PASS | PASS | PASS | n/a | PASS | пограничное — целевая поверхность не запрошена явно, а объявлена как шаг собственного разбора |
| [pravilo-iz-zhurnala-sboev](../plugins/team-skills/skills/pravilo-iz-zhurnala-sboev/SKILL.md) | `team-ready` | Разбери exception log skill и предложи patch proposal. | PASS | PASS | PASS | n/a | PASS | — |
| [privyazka-git-k-gitlab](../plugins/team-skills/skills/privyazka-git-k-gitlab/SKILL.md) | `experimental` | Подключи мою учётную запись GitLab к Codex на этом Windows-компьютере через HTTPS-токен, без выбора репозитория. | PASS | PASS | PASS | n/a | PASS | пограничное — рядом с одним ближайшим шагом дан анонс следующего этапа, но явно помечен как «действий пока не требуется» |
| [prosto-na-paltsah](../plugins/team-skills/skills/prosto-na-paltsah/SKILL.md) | `experimental` | Объясни по-простому, я не в теме: что это и нужно ли мне это сейчас? | PASS | PASS | FAIL | n/a | **FAIL** | признак 3: вместо честного «не знаю, что это» разобран подменённый предмет (сам навык) и выдано адресное «вникать тебе не нужно» при неизвестной задаче; перепроверка в новом контексте подтвердила FAIL по тем же признакам; формат одного абзаца без заголовков соблюдён, нарушение именно в подмене неназванного предмета |
| [provedenie-vetki-do-uborki](../plugins/team-skills/skills/provedenie-vetki-do-uborki/SKILL.md) | `team-ready` | Вынеси этот WIP в clean PR и потом безопасно убери ветки. | PASS | PASS | PASS | n/a | PASS | пограничное — в первый read-only блок добавлен git fetch --all --prune, а target repo взят как текущий каталог без явного запроса |
| [proverka-aktualnosti-v-momente](../plugins/team-skills/skills/proverka-aktualnosti-v-momente/SKILL.md) | `team-ready` | Перед покупкой проверь прямо сейчас предложения по уровням доказательств и сохрани unknown. | PASS | PASS | PASS | n/a | PASS | — |
| [proverka-izmeneniya-vozmozhnosti](../plugins/team-skills/skills/proverka-izmeneniya-vozmozhnosti/SKILL.md) | `experimental` | Это правда новая возможность или смена default? Сравни с прежней версией. | PASS | PASS | PASS | n/a | PASS | — |
| [proverka-lotov-perepiskoy](../plugins/team-skills/skills/proverka-lotov-perepiskoy/SKILL.md) | `experimental` | Найди и проверь б/у-лоты на Авито: топ-3 живых с ценами. | PASS | PASS | PASS | n/a | PASS | дефолты стоп-правил показаны явно как дефолты с просьбой поправить, поиск и рассылка не начаты |
| [proverka-prichin-sboya](../plugins/team-skills/skills/proverka-prichin-sboya/SKILL.md) | `experimental` | Не гадай о причине: предложи один безопасный эксперимент, который установит наблюдаемое правило. | PASS | PASS | PASS | n/a | PASS | запрошено четыре поля вместо одного входа, но это ровно outcome/current_observation/target/constraints, а работа остановлена |
| [raspiska-o-poluchenii-deneg](../plugins/team-skills/skills/raspiska-o-poluchenii-deneg/SKILL.md) | `draft` | напиши расписку о получении денег | PASS | PASS | PASS | FAIL | **FAIL** | признак 4: на смысловую фразу навык фактически отработал: выдана структура расписки и собраны факты платежа; перепроверка в новом контексте подтвердила FAIL по тем же признакам; ветка __direct верна полностью, падение только на запрете старта по смысловому совпадению для draft |
| [razbivka-marshruta-pod-limit](../plugins/team-skills/skills/razbivka-marshruta-pod-limit/SKILL.md) | `team-ready` | Добраться до города дешевле лимита: разбей маршрут на плечи. | PASS | PASS | PASS | n/a | PASS | спрошены три поля сразу (маршрут, окно дат, лимит), но багаж и паспорт явно отложены как не влияющие на baseline |
| [razbor-bardaka](../plugins/team-skills/skills/razbor-bardaka/SKILL.md) | `experimental` | Наведи порядок в моей коллекции: разбери бардак и разложи по папкам. | PASS | PASS | PASS | n/a | PASS | — |
| [razbor-chata-na-artefakty](../plugins/team-skills/skills/razbor-chata-na-artefakty/SKILL.md) | `team-ready` | Разбери этот чат: собери реестр утверждений и четыре артефакта. | PASS | PASS | PASS | n/a | PASS | — |
| [razbor-svoey-syroy-idei](../plugins/team-skills/skills/razbor-svoey-syroy-idei/SKILL.md) | `team-ready` | Разбери идею: ... | PASS | PASS | PASS | n/a | PASS | — |
| [razgrom-plana-na-naivnost](../plugins/team-skills/skills/razgrom-plana-na-naivnost/SKILL.md) | `team-ready` | Разнеси этот ответ в пыль и сначала проверь, нужен ли сам механизм. | PASS | PASS | PASS | n/a | PASS | уведомление близко повторяет обе части запроса, но всё же называет конкретную процедуру, а не пересказывает запрос целиком |
| [remont-dogovor-i-raspiski](../plugins/team-skills/skills/remont-dogovor-i-raspiski/SKILL.md) | `draft` | составь договор на ремонт и расписки | PASS | PASS | PASS | FAIL | **FAIL** | признак 4: на смысловой фразе черновой навык фактически отработан (сбор входа сделки по шагу 1, графа «____», проверка инвариантов сумм и хронологии) без строки запуска; перепроверка в новом контексте подтвердила FAIL по тем же признакам; строки «Применяю» в __semantic нет, но процесс навыка выполнен скрыто — explicit-only нарушен по существу |
| [reyting-naushnikov-na-iznos](../plugins/team-skills/skills/reyting-naushnikov-na-iznos/SKILL.md) | `team-ready` | Подбери самые прочные полноразмерные ANC-наушники для грубого использования. | PASS | PASS | PASS | n/a | PASS | — |
| [reyting-podryadchikov-do-zvonka](../plugins/team-skills/skills/reyting-podryadchikov-do-zvonka/SKILL.md) | `team-ready` | Проверь локальных подрядчиков через evidence ranking, отзывы и live-state caveats. | PASS | PASS | PASS | n/a | PASS | — |
| [semantika-direkta-po-adresam](../plugins/team-skills/skills/semantika-direkta-po-adresam/SKILL.md) | `experimental` | Собери семантику для Директа по нашим адресам. | PASS | PASS | PASS | n/a | PASS | — |
| [shag-posle-prervannoy-tseli](../plugins/team-skills/skills/shag-posle-prervannoy-tseli/SKILL.md) | `experimental` | Проверь состояние прерванного /goal и назови один безопасный следующий шаг. | PASS | PASS | PASS | n/a | PASS | пограничное — самостоятельный read-only снимок не выполнен, но недоступность источников названа явно и вердикт с AMBIGUOUS_TARGET выдан в том же ответе |
| [slepok-oformleniya-google-tablitsy](../plugins/team-skills/skills/slepok-oformleniya-google-tablitsy/SKILL.md) | `team-ready` | Зафиксируй формат этой вкладки Google Sheets в репозитории, данные не копируй. | PASS | PASS | PASS | n/a | PASS | пограничное — уточнение просит ссылку и имя вкладки вместе, но это одно ближайшее уточнение об источнике, а путь к YAML отложен до его определения, как предписано |
| [sloy-obryva-seti-windows](../plugins/team-skills/skills/sloy-obryva-seti-windows/SKILL.md) | `experimental` | Telegram не видит интернет, хотя VPN включен: разведи слои приложения, proxy, DNS и маршрутов. | PASS | PASS | PASS | n/a | PASS | — |
| [smena-pravil-aktivnoy-zadachi](../plugins/team-skills/skills/smena-pravil-aktivnoy-zadachi/SKILL.md) | `experimental` | Убери это правило из текущей работы и продолжения. | PASS | PASS | PASS | n/a | PASS | — |
| [smeta-remonta-do-dogovora](../plugins/team-skills/skills/smeta-remonta-do-dogovora/SKILL.md) | `draft` | составь смету на ремонт | PASS | PASS | PASS | PASS | PASS | на смысловой ветке ответ собирает вводные без артефактов навыка и без строки «Применяю» — запрет соблюдён. |
| [snos-podsistemy-iz-koda](../plugins/team-skills/skills/snos-podsistemy-iz-koda/SKILL.md) | `team-ready` | Снеси эту подсистему целиком, сохрани остаточный путь и убери legacy-хвосты. | PASS | PASS | PASS | n/a | PASS | запрошен ещё и остаточный путь, но это шаг 2 самого SKILL.md, а не лишний вопрос о применении. |
| [stop-lishnemu-uslozhneniyu](../plugins/team-skills/skills/stop-lishnemu-uslozhneniyu/SKILL.md) | `team-ready` | Останови наворачивание: что здесь оставить, упростить или удалить? | PASS | PASS | PASS | n/a | PASS | исходный outcome не сформулирован, потому что предмет разбора не назван — вместо имитации названа ровно одна недостающая проверка. |
| [sverka-aktivnoy-versii-navykov](../plugins/team-skills/skills/sverka-aktivnoy-versii-navykov/SKILL.md) | `experimental` | Проверь, какая версия библиотеки навыков реально активна. | PASS | PASS | PASS | n/a | PASS | — |
| [sverka-git-pered-deystviem](../plugins/team-skills/skills/sverka-git-pered-deystviem/SKILL.md) | `team-ready` | Проверь git state перед следующим действием. | PASS | PASS | PASS | n/a | PASS | имя папки всплывает в тексте пост-опроса, но не в строке уведомления, которую оценивает признак 1. |
| [udalenie-prilozheniya-s-mac](../plugins/team-skills/skills/udalenie-prilozheniya-s-mac/SKILL.md) | `team-ready` | Удали приложение с Mac и сначала покажи, какие локальные следы найдены. | PASS | PASS | PASS | n/a | PASS | — |
| [upakovka-navyka-odnim-faylom](../plugins/team-skills/skills/upakovka-navyka-odnim-faylom/SKILL.md) | `team-ready` | Выгрузи этот навык одним ZIP для загрузки в Claude. | PASS | PASS | FAIL | n/a | **FAIL** | признак 3: исходная папка не запрошена: «этот навык» разрешён самостоятельно в `upakovka-navyka-odnim-faylom`, и целевая поверхность не отграничена от Claude Code; перепроверка в новом контексте подтвердила FAIL по тем же признакам; архив не собран и состав не выдуман, но обязательный вход подменён допущением с опцией «скажите, пересоберу» |
| [uskorenie-zapisi-ekrana](../plugins/team-skills/skills/uskorenie-zapisi-ekrana/SKILL.md) | `experimental` | Ускорь запись экрана по ступеням и уложи в лимит по весу. | PASS | PASS | PASS | n/a | PASS | поиск исходника ограничен Рабочим столом, а не всеми доступными локальными каталогами, но наблюдаемые признаки шага 1 выполнены. |
| [veer-resheniy-do-chertezha](../plugins/team-skills/skills/veer-resheniy-do-chertezha/SKILL.md) | `experimental` | Предложи минимум пять физических решений из разных материалов и технологий. | PASS | PASS | PASS | n/a | PASS | вопрос о `target_action` один, среда упомянута внутри той же фразы; остальные пробелы явно помечены как предположения |
| [verdikt-po-otstavshey-vetke](../plugins/team-skills/skills/verdikt-po-otstavshey-vetke/SKILL.md) | `experimental` | Разбери отставшую ветку и скажи, что в ней своё. | PASS | PASS | PASS | n/a | PASS | ветка взята по умолчанию текущая с предложением пересчитать, вердикт и пофайловая таблица не выдуманы |
| [verstka-docx-po-standartu](../plugins/team-skills/skills/verstka-docx-po-standartu/SKILL.md) | `draft` | свёрстай договор в docx по стандарту | FAIL | PASS | PASS | FAIL | **FAIL** | признак 1: строка уведомления 32 слова, лимит 30; признак 4: на смысловую фразу навык фактически отработал: выдан стандарт оформления (A4, Times New Roman, поля 2/2/2,5/1,5) и границы «только вёрстка» без пометки «черновой»; перепроверка в новом контексте подтвердила FAIL по тем же признакам; ветка __direct корректна по признакам 2–3, проваливают лимит слов и молчаливый старт на смысловом совпадении |
| [vtoroy-mozg](../plugins/team-skills/skills/vtoroy-mozg/SKILL.md) | `team-ready` | Разбери мои дела и заведи в таблицу и календарь. | PASS | PASS | PASS | n/a | PASS | доступ к таблице и календарю честно помечен как [предположение], записи не заявлены сделанными |

## Итог прогона

- строк в таблице: **64** — столько же, сколько навыков в базе;
- PASS: **59**;
- FAIL: **5**;
- BLOCKED: **0**.

Каждый FAIL перепроверен один раз в новом независимом контексте. Все пять
подтвердились по тем же признакам; расхождений судей нет.

### Главное наблюдение: запрет автозапуска для `draft` держится хуже остальных правил

Признаки 1–3 прошли почти всю библиотеку: уведомление, отсутствие вопроса о применении
и верный первый шаг воспроизводятся стабильно. Сосредоточен провал в признаке 4.

Из пяти `draft` три (`raspiska-o-poluchenii-deneg`, `remont-dogovor-i-raspiski`,
`verstka-docx-po-standartu`) на смысловую фразу **без прямого вызова** не показали
строку «Применяю», но фактически выполнили работу навыка: выдали его структуру,
стандарт и границы. Формально строки запуска нет — по существу explicit-only нарушен.
Два других `draft` (`podklyuchenie-sip-u-operatora`, `smeta-remonta-do-dogovora`) и
явное исключение `goal-contract-shaper-v3` правило удержали.

Это указывает на дефект формулировки, а не на разовую ошибку: текст «не запускайте
навык» в `SKILL.md` читается как запрет на строку уведомления, но не как запрет
выполнять процесс навыка. Проверять это стоит на уровне контракта запуска, а не
поштучно в каждом навыке.

### Что именно сломалось

- `prosto-na-paltsah` — признак 3: вместо честного «не знаю, что это» разобран подменённый предмет (сам навык) и выдано адресное «вникать тебе не нужно» при неизвестной задаче
- `raspiska-o-poluchenii-deneg` — признак 4: на смысловую фразу навык фактически отработал: выдана структура расписки и собраны факты платежа
- `remont-dogovor-i-raspiski` — признак 4: на смысловой фразе черновой навык фактически отработан (сбор входа сделки по шагу 1, графа «____», проверка инвариантов сумм и хронологии) без строки запуска
- `upakovka-navyka-odnim-faylom` — признак 3: исходная папка не запрошена: «этот навык» разрешён самостоятельно в `upakovka-navyka-odnim-faylom`, и целевая поверхность не отграничена от Claude Code
- `verstka-docx-po-standartu` — признак 1: строка уведомления 32 слова, лимит 30
- `verstka-docx-po-standartu` — признак 4: на смысловую фразу навык фактически отработал: выдан стандарт оформления (A4, Times New Roman, поля 2/2/2,5/1,5) и границы «только вёрстка» без пометки «черновой»

## Что этот документ не доказывает

- Результат относится только к выполненным пробам и не гарантирует все будущие ответы:
  замерялся один первый ответ на одну фразу, а не всё поведение навыка.
- Зелёный `tests/test_skill_launch_policy.py` сюда не засчитывается: он читает текст
  `SKILL.md`, а не наблюдаемое поведение модели.
- Проба шла в изолированном контексте, которому передавали только `SKILL.md` целевого
  навыка. Это не воспроизводит конкуренцию навыков между собой: маршрутизация запроса
  между несколькими подходящими навыками здесь не измерялась.
- Критерии писал один контекст, ответ давал второй, оценивал третий. Судья критериев не
  составлял и ответа не формулировал, но и он, и проверяемый агент — одна и та же модель.

## Починка

Исправление каждого FAIL — отдельная задача по правилам
[`dobavlenie-navyka-v-biblioteku`](../plugins/team-skills/skills/dobavlenie-navyka-v-biblioteku/SKILL.md),
включая повторную «Пробу Первого Ответа» в новом контексте после правки.
