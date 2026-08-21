---
name: photo-photobomb-director
description: Используйте этот skill, когда пользователь хочет добавить на существующее фото playful, абсурдные, эмоциональные или гротескные элементы фотобомбинга, сохранив исходных людей, животных, объекты, фон, композицию, лица, позы и освещение. Skill должен срабатывать на обычные фразы вроде "сделай фотобомбинг", "добавь людей/животных", "усиль абсурд", "добавь гротеска", "сделай мемнее", "детский вайб", "пенсионный вайб" или "ещё уровень"; пользователь не должен помнить внутреннее имя skill или технические параметры.
---

# Photo Photobomb Director

## Согласие На Запуск

Явный вызов — команда, внутреннее имя навыка или первая фраза из каталога — выполняйте сразу, без вопроса.

При автосрабатывании на смысловое сходство сначала извлеките из текущего запроса:

- действие пользователя;
- конкретный объект: исходное фото и добавляемые персонажи или детали;
- короткое различие: управляемое редактирование с инвариантами вместо общей идеи.

Затем без вводного объяснения заполните и покажите следующую карточку:

Применить **«Режиссёр фотобомбинга»** (@kir-kopylov) для <кратко назовите действие и фото>?

**С навыком:** <назовите только фиксацию неизменяемых деталей, уровня и места вмешательства, точное редактирование и проверку сохранности сцены>.

**Без навыка:** <назовите только идею или общий запрос без управляемого вмешательства и защиты деталей>.

Перед отправкой проверьте карточку:

- ровно три содержательные строки: три непустые видимые строки;
- не более 45 слов во всей карточке;
- вопрос о применении стоит первым и один раз называет действие и объект;
- «С навыком» и «Без навыка» занимают по одной строке и одному предложению;
- сравнительные строки показывают только различие и не повторяют запрос;
- автор указан как `@kir-kopylov` в скобках в первой строке;
- нет отдельного ограничения, таблицы, кодовой рамки, служебного жаргона или заголовка `Annotation N`;
- неизвестное не придумывайте; если реальное ограничение меняет выбор, кратко включите его в подходящую сравнительную строку.

После карточки ждите ответа. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

Этот skill превращает фото пользователя в многослойный фотобомбинг: он добавляет только новые случайно выглядящие элементы и агрессивно сохраняет всё, что уже есть в кадре.

Используйте стандартный image editing flow для растровых фото. Если цель редактирования дана как локальный путь к файлу, сначала покажите изображение в контексте диалога; если изображения нет, попросите пользователя прикрепить фото.

## Естественные Входы

Пользователь не должен писать `$photo-photobomb-director`.

Запускайте skill по обычным формулировкам, если подразумевается редактирование изображения:

- русские фразы: "сделай фотобомбинг", "добавь случайных людей", "добавь животных", "добавь абсурда", "усиль гротеск", "сделай упоротее", "ещё уровень", "мемнее", "для детей", "для друзей", "для пенсии", "без жести";
- английские фразы: "add a photobomb", "make it more absurd", "add random people/animals", "make it meme-ish", "one more level", "kid-safe", "family-safe".

Когда skill сработал по естественной фразе, не просите пользователя заполнять числовые оси. Переведите его слова в пресет, уровень и safety bounds самостоятельно.

## Быстрый Роутер Запросов

Используйте этот роутинг вместо анкетирования пользователя:

- пользователь сказал только "сделай фотобомбинг" -> Friends Chat, уровень 2, 1-2 добавления;
- пользователь сказал "усиль", "ещё" или "добавь следующий уровень" -> сохранить последнюю картинку точно и добавить один новый слой;
- пользователь сказал "детский" или "для детей" -> Child-Safe, уровень 1-2, высокая радость, высокая доброта, без опасных шуток;
- пользователь сказал "пенсия", "для родителей" или "ретро" -> Pension/Retro, уровень 1-2, мягкий абсурд, низкий хаос;
- пользователь сказал "мем", "упорото" или "жёстче" -> Surreal-Meme или Friends Chat, уровень 3-4, высокий chaos, безопасный абсурд;
- пользователь сказал "НЛО", "катастрофа", "аварийно" или "трагично" -> Dark-Lite или Surreal-Meme, но театрально и без вреда: без удара, gore, травм, реалистичной паники и разрушений;
- пользователь сказал "не трогай людей/фон/животных" -> дословно перенесите эти invariants в prompt редактирования.

## Простые Управляющие Слова

Пользователь может управлять skill обычными словами:

- vibe presets: `детский`, `семейный`, `друзья`, `пенсия`, `офисно`, `мем`, `НЛО`, `трагикомедия`, `без жести`;
- уровни силы: `чуть-чуть`, `нормально`, `сильнее`, `гротеск`, `максимум`, `ещё уровень`;
- placement shortcuts: `на переднем плане`, `на фоне`, `в небе`, `с краю`, `мелкая пасхалка`, `перекрывает часть кадра`;
- safety shortcuts: `без крипоты`, `без травм`, `детский`, `не страшно`, `мультяшно-безопасно`.

Сопоставляйте эти слова с детальными осями внутри skill. Не показывайте таблицу осей пользователю, если он не просит тонкую настройку.

## Мини-Мастер

Проверку проводи внутренне; пользователю не показывай вероятные ответы и карту изменений.

Перед любым вопросом проведи контрфактическую проверку:
Представь наиболее вероятные ответы пользователя.
Назови, какое решение, действие или часть результата изменит каждый ответ.
Если следующий шаг при всех ответах одинаков — вопрос запрещён.
Если пользователь уже зафиксировал выбор — запиши его, не открывай заново.
Если неизвестное техническое и его можно проверить самостоятельно — проверь, не спрашивай.
Задавай только ближайший вопрос, ответ на который реально меняет результат.

Задавайте не больше одного короткого вопроса за ход и не больше двух за весь мини-мастер. После ответа заново решайте, нужен ли второй вопрос.

Правило:

- если изображения нет -> попросить фото;
- если фото есть, но нет vibe -> спросить: "Какой вайб: детский, друзья, пенсия, мем, НЛО или без жести?";
- если фото и vibe есть, но нет силы -> выбрать уровень 2 по умолчанию;
- если пользователь просит "максимально" или "гротеск-гротеск" -> выбрать уровень 4-5 и явно назвать safety boundary.

Хороший вопрос:

```text
Какой режим взять: детский, друзья, пенсия, мем, НЛО или без жести? Если не выберете, возьму "друзья, уровень 2".
```

## Контракт Сохранения

Каждый prompt редактирования сначала фиксирует invariants, потом описывает добавления:

- сохранить всех существующих людей точно: лица, выражения, позы, положение тела, одежду, identity, масштаб и placement;
- сохранить всех существующих животных, props, vehicles, signs, text, камни, растения, здания, небо, тени, свет, crop, perspective и layout фона;
- добавлять только запрошенные photobomb layers;
- не удалять, не перерисовывать, не ретушировать, не beautify, не sharpen, не crop, не resize и не relight исходное изображение;
- additions должны быть оптически правдоподобными для фото, если пользователь явно не просит collage или meme style;
- если пользователь просит текст на banner/sign, процитируйте его точно и предупредите, что generated text иногда требует повтора.

## Внутренний Parameter Brief

Перед редактированием извлеките или разумно выведите:

- `target`: фото для редактирования;
- `protected_subjects`: люди, животные и объекты, которые нельзя менять;
- `photobomb_count`: сколько новых элементов добавить;
- `escalation_levels`: один проход с N слоями или итеративное усиление, где новая правка сохраняет все предыдущие;
- `axis_values`: 0-10 для absurdity, grotesque, joy, tragicomic tone, wholesomeness, chaos/uporotost, realism и subtlety;
- `audience`: child-safe, family, friends chat, pension/retro, office-safe, dark-lite, surreal-meme или custom;
- `placement`: foreground, midground, background, flying, edge-of-frame, reflection/window, tiny-distant или mixed;
- `safety_bounds`: no gore, no realistic injury, no disaster aftermath, no hate/sexual content, no targeted humiliation;
- `text`: точная формулировка, если нужен banner, label, sign или speech element.

## Уровни Усиления

Используйте уровни как лестницу:

- Level 1: почти случайно. Один маленький правдоподобный intruder с краю или на фоне.
- Level 2: понятный фотобомбинг. Один смешной foreground или midground element, всё ещё реалистичный.
- Level 3: layered scene. Несколько элементов создают цепочку шутки и не ломают исходное фото.
- Level 4: grotesque-safe absurdity. Невероятные, но безвредные элементы: giant butterfly, tiny UFO, runaway picnic umbrella.
- Level 5: maximal meme logic. Несколько невозможных совпадений, но без вреда, gore и реалистичной катастрофы.

Для итераций вроде "добавь ещё" сохраняйте все прошлые additions точно и добавляйте только следующий слой.

Natural-language mapping:

- `чуть-чуть` -> Level 1;
- `нормально` -> Level 2;
- `сильнее` или `ещё уровень` -> увеличить на один уровень;
- `гротеск` -> Level 4;
- `максимум` -> Level 5 с safety bounds.

## Оси Настроения

Настраивайте additions по независимым осям:

- Absurdity: от правдоподобной случайности до невозможного совпадения.
- Grotesque: от quirky exaggeration до визуально нелепого; без хоррора, если пользователь не просит.
- Joy: от сухой шутки до cheerful chaos.
- Tragicomic: форма опасности без реального вреда, например broken-engine smoke без explosion.
- Wholesomeness: мягкая, дружелюбная, family-safe энергия.
- Uporotost/chaos: internet-meme randomness, странные props, невероятный timing.
- Realism: phone-photo naturalness, matched lens, fog, shadows, depth of field.
- Subtlety: hidden easter egg вместо half-frame photobomb.

Если пользователь просит "трагичность", делайте её театральной и безопасной: без видимых страданий, тел, удара, gore и реалистичных последствий ЧС.

## Пресеты Аудитории

- Child-safe: животные, шарики, бабочки, silly birds, friendly props, без danger-shaped jokes.
- Family: тёплая comedy, cute animals, harmless tourists, readable banners, низкий grotesque.
- Friends chat: более смелый absurdity, awkward humans, photobomb animals, weird travel coincidences.
- Pension/retro: gentle humor, old-school tourist props, accordion, tea thermos, nostalgic signs, низкий chaos.
- Office-safe: чистая визуальная шутка, без insults, risky disaster imagery и crude details.
- Dark-lite: near-disaster framing без вреда; smoke, panic-shaped angles, но cartoon-safe.
- Surreal-meme: UFOs, giant insects, impossible objects, но интегрированные в фото.

Russian shorthand mapping:

- `детский` -> Child-safe;
- `семейный` -> Family;
- `друзья` -> Friends chat;
- `пенсия`, `ретро`, `для родителей` -> Pension/Retro;
- `офисно` -> Office-safe;
- `без жести` -> Office-safe или Family с явным no-harm boundary;
- `трагикомедия`, `аварийно, но безопасно` -> Dark-lite;
- `мем`, `упорото`, `НЛО` -> Surreal-meme.

## Меню Photobomb Elements

Выбирайте элементы, которые подходят фото и выбранным осям:

- люди: lost hiker, confused guide, tourist taking the same selfie, person peeking behind rock/tree/door;
- животные: marmot, cat, dog, goat, bird, monkey, seal, llama; match geography unless absurdity is high;
- flying foreground: butterfly, tiny bird, moth, balloon, paper plane, drone, hat, leaf cloud;
- flying background: distant eagle, UFO, tiny plane, paraglider, umbrella, delivery drone;
- props: banner, sign, picnic basket, runaway suitcase, bouquet, giant map, misplaced chair;
- weather/light: sudden rainbow, theatrical fog curl, confetti gust, но не менять весь фон;
- reflection/easter egg: extra figure or animal in water, glass, sunglasses, or mirror if present.

## Prompt Pattern

Используйте эту структуру для image edits:

```text
Edit the provided photo as the exact target. Preserve the entire existing image pixel-faithfully wherever possible: do not move, remove, repaint, retouch, crop, resize, sharpen, beautify, or change [protected subjects and background details].

Only add [photobomb_count] new photobomb element(s): [precise elements, placement, scale, and behavior].

Vibe: [audience preset], absurdity [0-10], grotesque [0-10], joy [0-10], tragicomic [0-10], wholesomeness [0-10], chaos/uporotost [0-10], realism [0-10], subtlety [0-10].

Match the original camera perspective, lens, lighting, shadows, color temperature, depth of field, weather, motion blur, and occlusion. Additions should look accidentally captured in the photo.

Safety and tone: [bounds]. No extra text except: "[exact text]".
```

## Значения По Умолчанию

Если запрос свободный:

- `photobomb_count`: 1-3;
- `escalation_levels`: 1 текущая правка;
- `audience`: friends chat;
- `axis_values`: absurdity 6, grotesque 4, joy 6, tragicomic 1, wholesomeness 5, chaos/uporotost 5, realism 8, subtlety 4;
- `placement`: один foreground или edge-of-frame element плюс один background element, если count 2+;
- `safety_bounds`: funny, non-cruel, non-horror, no realistic injury.

## Опрос После Использования

Опрос задаётся один раз — после выдачи финального варианта фото, когда пользователь не просит следующий уровень, не посреди рабочего цикла. Если пользователь уже ответил «пропустить» в этой сессии, не переспрашивайте.

```text
Опрос по skill:
1. Что в этом использовании photo-photobomb-director было полезно?
2. Что стоит доработать в skill или его формате?
Можно ответить коротко или написать "пропустить".
```

Если пользователь ответил, сохраните санированную карточку в `~/.codex/skill-runs/photo-photobomb-director/usage-feedback.jsonl` — лучше через bundled script:

```bash
python3 scripts/log_usage_feedback.py --liked "..." --improve "..." --outcome "..."
```

Script перед записью редактирует приватные пути, контакты и token-like строки и сохраняет `redaction_applied` и `redaction_types`. Если запись невозможна из-за sandbox, прав или отсутствия tools, не делайте вид, что лог сохранён: скажите об этом и покажите короткую JSONL-карточку для ручного сохранения. Raw-ответы, контакты, пути и секреты не коммитить.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/<skill-name>/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.

## Быстрые Примеры

- "Сделай фотобомбинг, но не трогай людей и фон" -> Friends Chat, Level 2, 1-2 additions.
- "Добавь ещё уровень, мемнее" -> сохранить все existing generated content и добавить один Surreal-Meme layer.
- "Для детей, без крипоты" -> Child-safe, Level 1-2, cheerful animals или butterflies.
- "Пенсионный вайб, чуть-чуть" -> Pension/Retro, Level 1, small nostalgic easter egg.
- "НЛО аварийно, но мультяшно-безопасно, с баннером" -> Dark-lite/Surreal-Meme, no explosion, exact banner text.
- "Apply $photo-photobomb-director: 3 layers, child-safe, joy 8, grotesque 1" -> явный вызов тоже работает.
