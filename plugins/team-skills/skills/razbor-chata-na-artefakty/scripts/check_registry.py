#!/usr/bin/env python3
"""Проверка формата реестра утверждений и машинный шлюз между фазами.

Запуск:  python3 check_registry.py [путь-к-registry.md]

Коды возврата:
  0 — формат чист, незакрытых маркеров нет: фаза 2 разрешена
  1 — есть нарушения формата
  2 — файл не прочитан или детектор мёртв (сам себя не поймал)
  3 — формат чист, но остались незакрытые маркеры (!сомнение / !контекст-сжат):
      реестр не вычитан человеком, фаза 2 закрыта

Код 3 существует затем, чтобы шлюз держался кодом возврата, а не тем, что модель
внимательно прочитала строку вывода. Незакрытый маркер — это не косметика: он
означает, что статус подтвердила машина, а не человек.

Проверки по кириллице сделаны на python, а не на grep: в окружении без
подходящей локали диапазоны кириллицы в grep -E молча не срабатывают
и проверка возвращает ложный ноль.
"""

from __future__ import annotations

import hashlib
import re
import sys

STATUSES = "+x?0"

DOUBT = "!сомнение"
COMPACTED = "!контекст-сжат"

# Служебные строки шапки, которые не являются утверждениями.
# Дефис здесь СОЗНАТЕЛЬНО отсутствует: строка «- 905 | ... » — это típичная
# правка человека markdown-рефлексом, и она обязана попасть в нарушения,
# а не потеряться в фильтре шапки.
SKIP_PREFIX = ("#", "Чат:", "Статусы:", "Статус меняется", "Хеш реестра:")
STOP_HEADER = "## Без якоря"

BASE_RE = re.compile(r"^(?P<status>[+x?0]) (?P<num>\d{3}) \| (?P<text>[^|]+?) \| якорь: (?P<anchor>.+)$")
ALT_RE = re.compile(r"\s*альт:(?P<alt>\d{3})\s*$")
NUM_PREFIX_RE = re.compile(r"^[+x?0] \d{3} ")


def strip_markers(line: str) -> tuple[str, bool, bool, str | None]:
    """Снимает с хвоста строки служебные маркеры в любом порядке.

    Маркеры живут в конце строки, потому что поле «якорь» содержит произвольный
    текст из чата и должно оставаться последним смысловым полем. Возвращает
    очищенную строку и снятые флаги.
    """
    base = line.rstrip()
    doubt = compacted = False
    alt = None
    changed = True
    while changed:
        changed = False
        if base.endswith(DOUBT):
            base, doubt, changed = base[: -len(DOUBT)].rstrip(), True, True
        if base.endswith(COMPACTED):
            base, compacted, changed = base[: -len(COMPACTED)].rstrip(), True, True
        m = ALT_RE.search(base)
        if m:
            base, alt, changed = base[: m.start()].rstrip(), m.group("alt"), True
    return base, doubt, compacted, alt


def validate_line(line: str) -> str | None:
    """Возвращает None если строка валидна, иначе текст причины."""
    if not line or line[0] not in STATUSES:
        if line.startswith("-"):
            return "строка начинается с дефиса — заменить дефис на статус (+ x ? 0)"
        return "первый символ не является статусом (+ x ? 0)"
    if len(line) < 2 or line[1] != " ":
        return "после статуса нет пробела"

    base, _, _, _ = strip_markers(line)
    if not BASE_RE.match(base):
        if "якорь:" not in base:
            return "нет якоря"
        if not NUM_PREFIX_RE.match(base):
            return "нумерация не трёхзначная"
        if base.count("|") > 2:
            return "лишняя вертикальная черта в тексте утверждения — заменить на запятую"
        return "структура строки не совпадает с форматом"

    # Маркер ищется во ВСЕЙ строке, а не только в поле «утверждение»: внутри
    # якоря он так же не снимается с хвоста и так же теряется при чтении, а
    # строка при этом выглядит валидной и открывает шлюз.
    if DOUBT in base or COMPACTED in base or "альт:" in base:
        return "служебный маркер стоит не в конце строки — перенести в хвост"
    return None


# Наборы для самотеста живут на уровне модуля, чтобы строка «детектор жив»
# считала их длину, а не печатала захардкоженное число: добавили девятый случай —
# счётчик обязан это показать сам.
BROKEN_CASES = {
    "= 006 | текст | якорь: «слова»": "битый статус",
    "+ 7 | текст | якорь: «слова»": "битая нумерация",
    "+ 008 | текст без привязки": "нет якоря",
    "+009 | текст | якорь: «слова»": "нет пробела после статуса",
    "": "пустая строка",
    "- 905 | текст | якорь: «слова»": "дописано дефисом вместо статуса",
    "? 010 | !сомнение внутри текста | якорь: «слова»": "маркер спрятан в тексте",
    "+ 011 | текст с | чертой | якорь: «слова»": "лишняя вертикальная черта",
    "? 012 | текст | якорь: !сомнение «слова»": "маркер спрятан перед якорем",
    "0 013 | текст | якорь: «слова !контекст-сжат»": "маркер спрятан внутри якоря",
    "x 014 | текст альт:001 | якорь: «слова»": "альт: не в конце строки",
}

GOOD_CASES = [
    "+ 001 | текст утверждения | якорь: «слова из чата»",
    "? 002 | текст утверждения | якорь: «слова из чата» !сомнение",
    "x 003 | текст утверждения | якорь: «слова из чата» альт:001",
    "0 004 | текст утверждения | якорь: «слова» !контекст-сжат",
    "x 005 | текст | якорь: «слова» альт:001 !сомнение",
]


def selftest() -> list[str]:
    """Проверяет, что детектор ловит заведомо битые строки.

    Ничего не пишет на диск: битые примеры существуют только в памяти.
    Если хотя бы один из них признан валидным — детектор сломан.
    """
    broken = BROKEN_CASES
    good = GOOD_CASES
    dead = []
    for line, what in broken.items():
        if validate_line(line) is None:
            dead.append(f"пропустил: {what}")
    for line in good:
        why = validate_line(line)
        if why is not None:
            dead.append(f"забраковал корректную строку ({why}): {line}")
    return dead


def analyze(raw: list[str]) -> dict:
    """Разбирает строки реестра. Отделено от печати, чтобы было тестируемо."""
    problems: list[tuple[int, str, str]] = []
    counts = {s: 0 for s in STATUSES}
    doubts: list[str] = []
    compacted: list[str] = []
    numbers: dict[str, int] = {}
    manual: list[str] = []
    status_by_num: dict[str, str] = {}
    alts: list[tuple[int, str, str]] = []
    prev_machine: int | None = None

    for i, line in enumerate(raw, 1):
        if line.startswith(STOP_HEADER):
            break
        s = line.rstrip()
        if not s or s.startswith(SKIP_PREFIX):
            continue
        why = validate_line(s)
        base, is_doubt, is_compacted, alt = strip_markers(s)
        if why:
            problems.append((i, why, s[:70]))
            # маркер, спрятанный в тексте, всё равно должен быть посчитан:
            # иначе нарушение формата чинят, а незакрытый статус теряется
            if DOUBT in s:
                doubts.append(f"стр.{i}")
            if COMPACTED in s:
                compacted.append(f"стр.{i}")
            continue
        m = BASE_RE.match(base)
        st, num = m.group("status"), m.group("num")
        counts[st] += 1
        if is_doubt:
            doubts.append(num)
        if is_compacted:
            compacted.append(num)
        if alt is not None:
            alts.append((i, num, alt))
            if st != "x":
                problems.append((i, f"альт: допустим только на строке x, здесь статус {st}", s[:70]))
        if num in numbers:
            problems.append((i, f"номер {num} уже был в строке {numbers[num]}", s[:70]))
        else:
            numbers[num] = i
            status_by_num[num] = st
        if int(num) >= 900:
            manual.append(num)
        else:
            # Порядок номеров машинного диапазона обязан быть возрастающим:
            # убывание означает, что реестр отсортирован не по появлению в чате.
            # Пропуски НЕ проверяем: человек по инструкции переносит строку без
            # якоря в раздел «Без якоря», и дыра в нумерации — штатный результат
            # его вычитки, а не дефект.
            if prev_machine is not None and int(num) < prev_machine:
                problems.append(
                    (i, f"номер {num} меньше предыдущего {prev_machine:03d} — нумерация не по порядку появления в чате", s[:70])
                )
            prev_machine = int(num)

    warnings: list[str] = []
    for line_no, num, alt in alts:
        if alt not in status_by_num:
            problems.append((line_no, f"альт:{alt} ссылается на номер, которого нет в реестре", f"строка {num}"))
        elif status_by_num[alt] != "+":
            warnings.append(f"строка {num}: альт:{alt} ссылается на статус {status_by_num[alt]}, а не на +")

    return {
        "problems": problems,
        "counts": counts,
        "doubts": doubts,
        "compacted": compacted,
        "manual": manual,
        "warnings": warnings,
        "total": sum(counts.values()),
    }


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "registry.md"

    dead = selftest()
    if dead:
        print("ДЕТЕКТОР МЁРТВ — результатам проверки верить нельзя:")
        for d in dead:
            print("  -", d)
        return 2
    print(
        f"детектор жив: да (поймал {len(BROKEN_CASES)} синтетических нарушений "
        f"из {len(BROKEN_CASES)}, {len(GOOD_CASES)} корректных строк принял)"
    )

    try:
        with open(path, "rb") as f:
            blob = f.read()
        raw = blob.decode("utf-8").split("\n")
    except OSError as e:
        print(f"файл не прочитан: {e}")
        return 2
    except UnicodeDecodeError as e:
        print(f"файл не в UTF-8: {e}")
        return 2

    digest = hashlib.sha256(blob).hexdigest()[:16]
    r = analyze(raw)

    print(f"файл: {path} | строк-утверждений: {r['total']} | sha256:{digest}")
    print(
        "  + принято: {0} | x отвергнуто: {1} | ? открыто: {2} | 0 без реакции: {3}".format(
            r["counts"]["+"], r["counts"]["x"], r["counts"]["?"], r["counts"]["0"]
        )
    )
    if r["manual"]:
        print(f"  дописано руками (номера от 900): {len(r['manual'])} — {', '.join(r['manual'])}")
    print(f"  незакрыто {DOUBT}: {len(r['doubts'])}" + (f" — {', '.join(r['doubts'])}" if r["doubts"] else ""))
    print(f"  незакрыто {COMPACTED}: {len(r['compacted'])}" + (f" — {', '.join(r['compacted'])}" if r["compacted"] else ""))

    if r["counts"]["0"] == 0 and r["total"] > 0:
        print("  ВНИМАНИЕ: ни одной строки со статусом 0. Проверить, не записаны ли")
        print("  предложения агента как принятые.")
    for w in r["warnings"]:
        print(f"  ВНИМАНИЕ: {w}")

    if r["problems"]:
        print(f"\nнарушений формата: {len(r['problems'])}")
        for ln, why, txt in r["problems"]:
            print(f"  строка {ln}: {why}\n    {txt}")
        return 1

    print("\nнарушений формата: 0")

    # Пустой артефакт — валидный результат, пустой РЕЕСТР — нет. Ноль
    # строк-утверждений означает обрыв записи или разбор, который не состоялся;
    # открыть здесь шлюз — значит выдать пустые артефакты за результат
    # человеческой вычитки.
    if r["total"] == 0:
        print("ШЛЮЗ ЗАКРЫТ: в реестре нет ни одной строки-утверждения.")
        print("Записать реестр заново; пустой реестр вычитывать нечем, и фаза 2 по нему не запускается.")
        return 1

    if r["doubts"] or r["compacted"]:
        print("ШЛЮЗ ЗАКРЫТ: остались незакрытые маркеры, реестр не вычитан человеком.")
        print("Фаза 2 не запускается, пока маркеры не снял человек.")
        return 3

    print("ШЛЮЗ ОТКРЫТ: формат чист, незакрытых маркеров нет.")
    print(f"Привязка к содержимому: sha256:{digest} — это число обязано совпасть с прочитанным файлом.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
