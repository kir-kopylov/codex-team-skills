from __future__ import annotations

import argparse
import re
import sys


CYRILLIC_WORD_RE = re.compile(r"[А-Яа-яЁё]{3,}")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")


def prose_for_language_check(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return text


def russian_score(text: str) -> tuple[int, int]:
    prose = prose_for_language_check(text)
    return len(CYRILLIC_WORD_RE.findall(prose)), len(LATIN_WORD_RE.findall(prose))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Проверяет, что PR title/body/comment написаны на русском."
    )
    parser.add_argument("--kind", default="PR text", help="Что проверяется: PR body, comment, review.")
    parser.add_argument("--title", default="", help="Заголовок PR, если есть.")
    parser.add_argument("--body", default="", help="Текст PR или комментария.")
    args = parser.parse_args()

    text = "\n".join(part for part in (args.title, args.body) if part)
    cyrillic_words, latin_words = russian_score(text)

    if cyrillic_words < 5:
        print(
            f"{args.kind} должен быть на русском: найдено русских слов={cyrillic_words}, "
            f"латинских слов={latin_words}. Технические термины допустимы, но пользовательский "
            "текст PR/comment пишется по-русски.",
            file=sys.stderr,
        )
        return 1

    if latin_words > cyrillic_words:
        print(
            f"{args.kind} выглядит англоязычным: русских слов={cyrillic_words}, "
            f"латинских слов={latin_words}. Перепишите PR/comment на русском, оставив "
            "технические имена, пути и команды как есть.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
