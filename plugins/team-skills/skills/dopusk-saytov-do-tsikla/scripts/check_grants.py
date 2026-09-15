#!/usr/bin/env python3
"""Подсказка (не судья!) по грантам Claude-in-Chrome для Windows + Chrome.

СУДЬЯ — страница расширения: Permissions -> "Your approved sites" (обновить перед
чтением). Этот скрипт лишь быстро подсматривает в базу расширения на диске и может
ошибаться: при работающем Chrome диск отстаёт от живого состояния, а после
уплотнения базы (compaction) запись уезжает в сжатый файл, где простой поиск её не
видит. Поэтому "ключ не найден" здесь НЕ значит "грантов нет" — это значит "проверь
на странице". При любом расхождении со страницей верить странице.

Область: только Chrome на Windows (одна конфигурация). Другие браузеры и системы
намеренно не поддерживаются — их закрывает страница расширения, она кросс-платформенная.

Использование:
  python check_grants.py --domains avito.ru www.avito.ru
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

DEFAULT_EXTENSION_ID = "fcoeoabgfenejglbffodgkkbkcdhcgfn"  # Claude in Chrome
KEY = b"permissionStorage"


def find_storage_dirs(extension_id: str) -> list[str]:
    home = os.path.expanduser("~")
    base = os.path.join(home, "AppData", "Local", "Google", "Chrome", "User Data")
    patterns = [
        os.path.join(base, "*", "Local Extension Settings", extension_id),
        os.path.join(base, "Local Extension Settings", extension_id),
    ]
    dirs = []
    for pattern in patterns:
        dirs.extend(d for d in glob.glob(pattern) if os.path.isdir(d))
    return dirs


def extract_json_object(data: bytes, start: int) -> dict | None:
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, min(len(data), start + 500_000)):
        ch = data[i : i + 1]
        if in_string:
            if escaped:
                escaped = False
            elif ch == b"\\":
                escaped = True
            elif ch == b'"':
                in_string = False
            continue
        if ch == b'"':
            in_string = True
        elif ch == b"{":
            depth += 1
        elif ch == b"}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(data[start : i + 1].decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    return None
    return None


def latest_permission_state(storage_dir: str) -> dict | None:
    files = [
        (os.path.getmtime(p), p)
        for p in glob.glob(os.path.join(storage_dir, "*"))
        if p.endswith((".log", ".ldb"))
    ]
    best: dict | None = None
    for _, path in sorted(files):
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        for match in re.finditer(re.escape(KEY), data):
            brace = data.find(b"{", match.end(), match.end() + 40)
            if brace == -1:
                continue
            obj = extract_json_object(data, brace)
            if isinstance(obj, dict) and "permissions" in obj:
                best = obj
    return best


def normalize(host: str) -> str:
    # Точное совпадение хостов: www.avito.ru и avito.ru считаются РАЗНЫМИ грантами
    # (снипет вооружает оба явно). Подсказка ошибается только в безопасную сторону —
    # скажет «похоже нет» и отправит сверить/вооружить, но никогда оптимистично «да».
    return host.strip().lower().rstrip(".")


def granted_always(state: dict) -> set[str]:
    hosts = set()
    for record in state.get("permissions", []):
        if not isinstance(record, dict):
            continue
        if record.get("action") == "allow" and record.get("duration") == "always":
            netloc = (record.get("scope") or {}).get("netloc", "")
            if netloc:
                hosts.add(normalize(str(netloc)))
    return hosts


def covered(domain: str, grants: set[str]) -> bool:
    return normalize(domain) in grants


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", nargs="+", required=True)
    parser.add_argument("--extension-id", default=DEFAULT_EXTENSION_ID)
    args = parser.parse_args()

    print("ПОДСКАЗКА, НЕ СУДЬЯ. Судит страница расширения: Permissions -> Your approved sites.")

    dirs = find_storage_dirs(args.extension_id)
    if not dirs:
        print("база расширения не найдена (возможно, не Chrome/Windows) — сверься на странице расширения")
        return 2

    state = None
    for d in sorted(dirs, key=os.path.getmtime):
        candidate = latest_permission_state(d)
        if candidate is not None:
            state = candidate
    if state is None:
        print("ключ не найден в базе — это НЕ значит «грантов нет» (возможно уплотнение базы); сверься на странице")
        return 2

    grants = granted_always(state)
    print(f"похоже вооружены (сверь на странице): {', '.join(sorted(grants)) if grants else '—'}")

    missing = [d for d in args.domains if not covered(d, grants)]
    for domain in args.domains:
        print(f"  {'[похоже да] ' if covered(domain, grants) else '[похоже нет]'} {domain}")

    if missing:
        print(f"\nпо подсказке не вооружены: {', '.join(missing)} — подтверди на странице, затем обход (см. SKILL.md)")
        return 1
    print("\nпо подсказке всё вооружено — подтверди на странице, затем проба тишины")
    return 0


if __name__ == "__main__":
    sys.exit(main())
