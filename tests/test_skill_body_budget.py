from __future__ import annotations

from conftest import load_frontmatter, skill_dirs


# Тело `SKILL.md` модель читает целиком на каждом запуске навыка, поэтому длина
# тела — это бюджет внимания: чем больше в нём справочного материала, тем выше
# шанс, что процедура и границы безопасности в нём утонут. Порог не идеал, а
# храповик: в него уже укладывается большинство навыков, и тест удерживает их
# там. Справочный материал нового навыка кладём сразу в `references/`, а в
# `SKILL.md` оставляем шаг, на котором его читают.
BODY_BUDGET = 12_000

# Навыки, тело которых стало длиннее порога ещё до появления этого теста.
# Перенос их крупных разделов в `references/` проверялся и отклонён: у самых
# длинных навыков такие разделы закреплены за `SKILL.md` отдельными тестами и
# составляют ядро процедуры или границы безопасности. Список намеренно без
# чисел: числа пришлось бы обновлять на каждой правке, а достигнутая длина
# превратилась бы в норму.
KNOWN_OVERSIZED = frozenset(
    {
        "dobavlenie-navyka-v-biblioteku",
        "dopusk-saytov-do-tsikla",
        "goal-contract-shaper-v3",
        "kontrakt-tseli-do-starta",
        "lechenie-terminala-pri-vpn",
        "narabotki-sessii-v-vetku",
        "navyk-iz-chastogo-zaprosa",
        "obnovlenie-biblioteki-navykov",
        "otsev-replik-do-vstrechi",
        "peredelka-dogovorov-arendy",
        "peresmotr-predposylok-posle-povtora",
        "podsadka-nezvanyh-v-snimok",
        "poisk-sekretov-bez-raskrytiya",
        "prosto-na-paltsah",
        "provedenie-vetki-do-uborki",
        "proverka-aktualnosti-v-momente",
        "proverka-lotov-perepiskoy",
        "proverka-prichin-sboya",
        "razbor-bardaka",
        "razbor-chata-na-artefakty",
        "sverka-aktivnoy-versii-navykov",
    }
)


def test_skill_body_fits_budget() -> None:
    skills = skill_dirs()
    assert skills, "Нужен хотя бы один skill"

    sizes = {}
    for skill_dir in skills:
        _, body = load_frontmatter(skill_dir / "SKILL.md")
        sizes[skill_dir.name] = len(body)

    oversized = {name for name, size in sizes.items() if size > BODY_BUDGET}

    grew = sorted(oversized - KNOWN_OVERSIZED)
    assert not grew, (
        f"Тело SKILL.md переросло лимит {BODY_BUDGET} знаков: "
        + ", ".join(f"{name} — {sizes[name]}" for name in grew)
        + ". Вынесите справочную часть в references/ этого навыка и оставьте в "
        "SKILL.md шаг, на котором её читают; пополнять KNOWN_OVERSIZED — "
        "последнее средство и решение владельца библиотеки."
    )

    shrank = sorted(KNOWN_OVERSIZED - oversized)
    assert not shrank, (
        "Список KNOWN_OVERSIZED устарел: " + ", ".join(shrank) + f" — уже не длиннее "
        f"{BODY_BUDGET} знаков либо переименован или удалён. Уберите имя из "
        "списка, иначе навык снова сможет вырасти незаметно."
    )
