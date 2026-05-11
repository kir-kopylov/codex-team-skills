---
name: photo-photobomb-director
description: Use this skill when the user wants to add playful, absurd, emotional, or grotesque photobomb elements to an existing photo while preserving the original people, animals, objects, background, composition, faces, poses, and lighting. Trigger this skill for natural requests like "сделай фотобомбинг", "добавь людей/животных", "усиль абсурд", "добавь гротеска", "сделай мемнее", "детский вайб", "пенсионный вайб", or "ещё уровень"; the user should not need to remember the skill name or technical parameters.
---

# Photo Photobomb Director

## Overview

Turn a user photo into a layered photobomb edit by adding only new accidental-looking elements. Preserve the existing image aggressively, then vary the added elements by audience, mood axes, and escalation level.

Use the built-in image editing flow for raster photos. If the edit target is a local file path, load it into the conversation first; if no image is available, ask for the image before generating.

## Natural Entry Points

The user should be able to invoke this skill without saying `$photo-photobomb-director`.

Trigger on ordinary phrasing when an image edit is implied:

- Russian: "сделай фотобомбинг", "добавь случайных людей", "добавь животных", "добавь абсурда", "усиль гротеск", "сделай упоротее", "ещё уровень", "мемнее", "для детей", "для друзей", "для пенсии", "без жести".
- English: "add a photobomb", "make it more absurd", "add random people/animals", "make it meme-ish", "one more level", "kid-safe", "family-safe".

When triggered naturally, do not ask the user to provide numeric axes. Translate their words into presets, levels, and safety bounds.

## Easy Request Router

Prefer this routing over asking for parameter lists:

- If the user says only "сделай фотобомбинг" -> use Friends Chat, Level 2, 1-2 additions.
- If the user says "усиль", "ещё", or "добавь следующий уровень" -> preserve the latest image exactly and add one new layer at the next escalation level.
- If the user says "детский" or "для детей" -> use Child-Safe, Level 1-2, high joy, high wholesomeness, no danger-shaped jokes.
- If the user says "пенсия", "для родителей", or "ретро" -> use Pension/Retro, Level 1-2, gentle absurdity, low chaos.
- If the user says "мем", "упорото", or "жёстче" -> use Surreal-Meme or Friends Chat, Level 3-4, high chaos, safe absurdity.
- If the user says "НЛО", "катастрофа", "аварийно", or "трагично" -> use Dark-Lite or Surreal-Meme, keep it theatrical and harmless: no impact, gore, injury, panic realism, or destruction.
- If the user says "не трогай людей/фон/животных" -> copy those invariants verbatim into the edit prompt.

## Friendly Controls

Let users control the skill with simple words:

- Vibe presets: `детский`, `семейный`, `друзья`, `пенсия`, `офисно`, `мем`, `НЛО`, `трагикомедия`, `без жести`.
- Strength levels: `чуть-чуть`, `нормально`, `сильнее`, `гротеск`, `максимум`, `ещё уровень`.
- Placement shortcuts: `на переднем плане`, `на фоне`, `в небе`, `с краю`, `мелкая пасхалка`, `перекрывает часть кадра`.
- Safety shortcuts: `без крипоты`, `без травм`, `детский`, `не страшно`, `мультяшно-безопасно`.

Map shortcuts to the detailed axes internally; do not expose the axis table unless the user asks for fine control.

## Mini Wizard

Ask at most two short questions only when the request is too vague to produce a satisfying result.

Use this decision rule:

- If there is no image -> ask for the photo.
- If there is an image but no vibe at all -> ask: "Какой вайб: детский, друзья, пенсия, мем, НЛО или без жести?"
- If there is an image and a vibe but no strength -> choose Level 2 by default; do not ask.
- If the user asks for "максимально" or "гротеск-гротеск" -> choose Level 4-5 and state the safety boundary.

Good wizard question:

```text
Какой режим взять: детский, друзья, пенсия, мем, НЛО или без жести? Если не выберете, возьму "друзья, уровень 2".
```

## Operating Contract

Every prompt must lock the invariants before describing additions:

- Preserve all existing people exactly: faces, expressions, poses, body positions, clothing, identity, scale, and placement.
- Preserve all existing animals, props, vehicles, signs, text, rocks, plants, buildings, sky, shadows, lighting, crop, perspective, and background layout.
- Add only the requested photobomb layers. Do not remove, repaint, beautify, sharpen, crop, resize, or relight the original image.
- Keep additions optically plausible for the photo unless the user explicitly asks for collage or meme style.
- If text is requested on a banner/sign, quote it exactly and warn that generated text may need a retry.

## Parameter Brief

Before editing, extract or infer this brief. If the user specifies enough, do not ask; state the chosen assumptions briefly.

- `target`: the photo to edit.
- `protected_subjects`: people/animals/objects that must remain unchanged.
- `photobomb_count`: number of new elements to add.
- `escalation_levels`: one pass with N layers, or iterative levels where each new edit preserves all previous edits.
- `axis_values`: 0-10 values for absurdity, grotesque, joy, tragicomic tone, wholesomeness, chaos/uporotost, realism, and subtlety.
- `audience`: child-safe, family, friends chat, pension/retro, office-safe, dark-lite, surreal-meme, or custom.
- `placement`: foreground, midground, background, flying, edge-of-frame, reflection/window, tiny-distant, or mixed.
- `safety_bounds`: no gore, no realistic injury, no disaster aftermath, no hate/sexual content, no targeted humiliation.
- `text`: exact wording if a banner, label, sign, or speech element is requested.

## Escalation Levels

Use levels as a ladder, not as separate styles:

- Level 1: Barely accidental. One small plausible intruder in the edge or background.
- Level 2: Clear photobomb. One funny foreground or midground element, still realistic.
- Level 3: Layered scene. Multiple elements create a joke chain while preserving the original photo.
- Level 4: Grotesque-safe absurdity. Improbable but harmless elements, e.g. giant butterfly, tiny UFO, runaway picnic umbrella.
- Level 5: Maximal meme logic. Several impossible coincidences, but still no harm, gore, or real catastrophe.

For iterative user requests like "add more", preserve all previous generated additions exactly and add only the next layer.

Natural-language mapping:

- `чуть-чуть` -> Level 1.
- `нормально` -> Level 2.
- `сильнее` or `ещё уровень` -> increase by one level.
- `гротеск` -> Level 4.
- `максимум` -> Level 5 with safety bounds.

## Mood Axes

Tune additions using independent axes:

- Absurdity: from plausible tourist accident to impossible coincidence.
- Grotesque: from quirky exaggeration to visually ridiculous; keep it non-horror unless asked.
- Joy: from dry joke to cheerful, bright, celebratory chaos.
- Tragicomic: danger-shaped joke without real harm, e.g. broken-engine smoke with no explosion.
- Wholesomeness: soft, friendly, cute, family-safe energy.
- Uporotost/chaos: internet-meme randomness, strange props, improbable timing.
- Realism: phone-photo naturalness, matched lens, fog, shadows, depth of field.
- Subtlety: hidden easter egg versus half-frame photobomb.

If "tragicness" is requested, make it theatrical and safe: no visible suffering, no bodies, no impact, no gore, no realistic emergency aftermath.

## Audience Presets

- Child-safe: animals, balloons, butterflies, silly birds, friendly props, no danger-shaped jokes.
- Family: warm comedy, cute animals, harmless tourists, readable banners, low grotesque.
- Friends chat: bolder absurdity, awkward humans, photobomb animals, weird travel coincidences.
- Pension/retro: gentle humor, old-school tourist props, accordion, tea thermos, nostalgic signs, low chaos.
- Office-safe: clean visual joke, no insults, no risky disaster imagery, no crude details.
- Dark-lite: near-disaster framing without harm; smoke, panic-shaped angles, but cartoon-safe.
- Surreal-meme: UFOs, giant insects, impossible objects, still integrated into the photo.

Russian shorthand mapping:

- `детский` -> Child-safe.
- `семейный` -> Family.
- `друзья` -> Friends chat.
- `пенсия`, `ретро`, `для родителей` -> Pension/Retro.
- `офисно` -> Office-safe.
- `без жести` -> Office-safe or Family with explicit no-harm bounds.
- `трагикомедия`, `аварийно, но безопасно` -> Dark-lite.
- `мем`, `упорото`, `НЛО` -> Surreal-meme.

## Photobomb Element Menu

Pick elements that match the photo context and requested axes:

- People: lost hiker, confused guide, tourist taking the same selfie, person peeking behind rock/tree/door.
- Animals: marmot, cat, dog, goat, bird, monkey, seal, llama; match geography unless absurdity is high.
- Flying foreground: butterfly, tiny bird, moth, balloon, paper plane, drone, hat, leaf cloud.
- Flying background: distant eagle, UFO, tiny plane, paraglider, umbrella, delivery drone.
- Props: banner, sign, picnic basket, runaway suitcase, bouquet, giant map, misplaced chair.
- Weather/light: sudden rainbow, theatrical fog curl, confetti gust, but avoid changing the whole background.
- Reflection/easter egg: extra figure or animal in water, glass, sunglasses, or mirror if present.

## Prompt Pattern

Use this structure for image edits:

```text
Edit the provided photo as the exact target. Preserve the entire existing image pixel-faithfully wherever possible: do not move, remove, repaint, retouch, crop, resize, sharpen, beautify, or change [protected subjects and background details].

Only add [photobomb_count] new photobomb element(s): [precise elements, placement, scale, and behavior].

Vibe: [audience preset], absurdity [0-10], grotesque [0-10], joy [0-10], tragicomic [0-10], wholesomeness [0-10], chaos/uporotost [0-10], realism [0-10], subtlety [0-10].

Match the original camera perspective, lens, lighting, shadows, color temperature, depth of field, weather, motion blur, and occlusion. Additions should look accidentally captured in the photo.

Safety and tone: [bounds]. No extra text except: "[exact text]".
```

## Defaults

When the user gives a loose request, use:

- `photobomb_count`: 1-3.
- `escalation_levels`: 1 current edit.
- `audience`: friends chat.
- `axis_values`: absurdity 6, grotesque 4, joy 6, tragicomic 1, wholesomeness 5, chaos/uporotost 5, realism 8, subtlety 4.
- `placement`: one foreground or edge-of-frame element plus one background element when count is 2+.
- `safety_bounds`: funny, non-cruel, non-horror, no realistic injury.

## Quick Examples

- "Сделай фотобомбинг, но не трогай людей и фон" -> Friends Chat, Level 2, 1-2 additions.
- "Добавь ещё уровень, мемнее" -> preserve all existing generated content, add one Surreal-Meme layer.
- "Для детей, без крипоты" -> Child-safe, Level 1-2, cheerful animals or butterflies.
- "Пенсионный вайб, чуть-чуть" -> Pension/Retro, Level 1, small nostalgic easter egg.
- "НЛО аварийно, но мультяшно-безопасно, с баннером" -> Dark-lite/Surreal-Meme, no explosion, exact banner text.
- "Apply $photo-photobomb-director: 3 layers, child-safe, joy 8, grotesque 1" -> explicit invocation still works.

