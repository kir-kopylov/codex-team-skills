#!/usr/bin/env python3
"""Ограниченная проверка маршрутизации по описаниям навыков.

Три шага:

    python scripts/routing_baseline.py --source examples build --skill имя-навыка
    python scripts/routing_baseline.py --source examples run --model идентификатор --dry-run
    python scripts/routing_baseline.py --source examples report --model идентификатор

`build` требует --skill/--related либо явно выбранный --full. Все описания
библиотеки остаются вариантами выбора; коды стабильны по имени. Набор
`examples` — вход каждого хорошего примера с разметкой «есть ли во входе
дословный natural_trigger»; набор `triggers` — сами фразы `natural_triggers`,
та самая проверка, которая упирается в потолок.
`run` — необязательный адаптер Claude: каждый вызов — отдельный процесс `claude`
без памяти, навыков, `CLAUDE.md` и инструментов, судья видит только список
кодов и один вход. `report` считает доли попаданий, промахи и путаемые пары.

Каждый ответ помечен отпечатком набора — хешем списка вариантов и входов. После
правки `description` отпечаток меняется, старые ответы перестают считаться
готовыми, и `report` их не смешивает с новыми. Неполный замер `report` не
печатает: доля по куску набора завысила бы результат.

Рабочая папка по умолчанию — `~/.codex/goal-runs/routing-baseline`: сырые
ответы судьи в репозиторий не коммитятся.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins" / "team-skills" / "skills"
DEFAULT_OUT = pathlib.Path.home() / ".codex" / "goal-runs" / "routing-baseline"

EVAL_STATUSES = {"team-ready", "experimental"}
EXPLICIT_ONLY = {"goal-contract-shaper-v3"}

SYSTEM_PROMPT = (
    "Ты маршрутизатор запросов. Тебе дан список процедур с кодами и один запрос "
    "пользователя. Выбери ровно одну процедуру, которая должна обработать запрос, "
    "или ответь «ни один», если ни одна не подходит. Отвечай ТОЛЬКО данным кодом "
    "или словами «ни один». Без объяснений."
)


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def load_skills() -> dict:
    skills = {}
    for folder in sorted(SKILLS.iterdir()):
        if not folder.is_dir():
            continue
        raw = (folder / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
        frontmatter = yaml.safe_load(match.group(1)) if match else {}
        registry = yaml.safe_load((folder / "skill.yaml").read_text(encoding="utf-8"))
        skills[folder.name] = {
            "name": folder.name,
            "description": frontmatter.get("description", ""),
            "status": registry.get("status"),
            "natural_triggers": registry.get("natural_triggers") or [],
        }
    return skills


def build(
    out: pathlib.Path,
    source: str,
    skills: list[str] | None = None,
    related: list[str] | None = None,
    full: bool = False,
) -> None:
    catalog = load_skills()
    targets, neighbors = sorted(set(skills or [])), sorted(set(related or []))
    if full and (targets or neighbors):
        raise SystemExit("--full нельзя сочетать с --skill или --related")
    if not full and not targets:
        raise SystemExit("укажите --skill либо явно запросите --full")
    eligible = {
        name for name, item in catalog.items()
        if item["status"] in EVAL_STATUSES and name not in EXPLICIT_ONLY
    }
    selected = eligible if full else set(targets + neighbors)
    unknown = selected - set(catalog)
    if unknown:
        raise SystemExit(f"неизвестные навыки: {', '.join(sorted(unknown))}")
    if selected - eligible:
        raise SystemExit("в охвате есть навык без смыслового автозапуска")
    scope = {
        "mode": "full" if full else "targeted",
        "skills": targets,
        "related": neighbors,
        "selected_skills": sorted(selected),
        "source": source,
    }
    inputs = []
    for name, skill in catalog.items():
        if name not in selected:
            continue
        if source == "triggers":
            for trigger in skill["natural_triggers"]:
                inputs.append(
                    {
                        "id": f"T{len(inputs) + 1:03d}",
                        "owner": name,
                        "file": f"plugins/team-skills/skills/{name}/skill.yaml",
                        "text": trigger,
                        "literal_trigger": True,
                    }
                )
            continue
        for path in sorted((SKILLS / name / "examples").glob("good-*.md")):
            body = re.search(
                r"^##\s*Вход\s*$(.*?)(?=^##\s|\Z)",
                path.read_text(encoding="utf-8"),
                re.S | re.M,
            )
            if not body:
                raise SystemExit(f"нет секции «## Вход»: {path}")
            text = body.group(1).strip()
            normalized = normalize(text)
            inputs.append(
                {
                    "id": f"I{len(inputs) + 1:03d}",
                    "owner": name,
                    "file": str(path.relative_to(ROOT)),
                    "text": text,
                    "literal_trigger": any(
                        normalize(trigger) and normalize(trigger) in normalized
                        for trigger in skill["natural_triggers"]
                    ),
                }
            )

    codes = {
        name: "S" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
        for name in catalog
    }
    if len(set(codes.values())) != len(codes):
        raise SystemExit("коллизия кодов навыков: набор не создан")
    order = sorted(catalog, key=codes.get)

    out.mkdir(parents=True, exist_ok=True)
    (out / "skills.json").write_text(
        json.dumps({"codes": codes, "skills": catalog}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / f"inputs-{source}.json").write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "choice_list.txt").write_text(
        "\n".join(f'{codes[name]}: {catalog[name]["description"]}' for name in order) + "\n",
        encoding="utf-8",
    )

    (out / f"scope-{source}.json").write_text(
        json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lengths = sorted(len(item["text"]) for item in inputs)
    middle = lengths[len(lengths) // 2] if lengths else 0
    print(f"набор: {source}")
    print(f"охват: {scope['mode']}")
    print(f"навыков всего: {len(catalog)}")
    print(f"навыков в наборе: {len({item['owner'] for item in inputs})}")
    print(f"входов: {len(inputs)}")
    print(f"с дословным триггером: {sum(item['literal_trigger'] for item in inputs)}")
    print(f"медиана длины входа: {middle} знаков")
    print(f"набор записан: {out}")


def fingerprint(out: pathlib.Path, source: str) -> str:
    """Отпечаток набора: список вариантов плюс входы."""
    digest = hashlib.sha256()
    digest.update((out / "choice_list.txt").read_bytes())
    digest.update((out / f"inputs-{source}.json").read_bytes())
    scope = out / f"scope-{source}.json"
    if scope.exists():
        digest.update(scope.read_bytes())
    return digest.hexdigest()[:12]


def parse_answer(answer: str, known_codes) -> str:
    answer = answer.strip()
    if answer in known_codes:
        return answer
    if answer.casefold() == "ни один":
        return "NONE"
    return "UNPARSED"


def load_dataset(out: pathlib.Path, source: str):
    meta = json.loads((out / "skills.json").read_text(encoding="utf-8"))
    inputs = json.loads((out / f"inputs-{source}.json").read_text(encoding="utf-8"))
    codes = meta["codes"]
    if len(set(codes.values())) != len(codes):
        raise SystemExit("коды навыков неоднозначны")
    if not inputs or len({item["id"] for item in inputs}) != len(inputs):
        raise SystemExit("набор пуст либо содержит повторные идентификаторы")
    if any(item["owner"] not in codes for item in inputs):
        raise SystemExit("владелец входа отсутствует в списке вариантов")
    path = out / f"scope-{source}.json"
    scope = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "mode": "legacy", "source": source,
    }
    if scope.get("source") != source or scope.get("mode") not in {
        "targeted", "full", "legacy",
    }:
        raise SystemExit("неверные метаданные охвата")
    if scope["mode"] == "targeted":
        targets, related = scope.get("skills", []), scope.get("related", [])
        selected = sorted(set(targets + related))
        if not targets or selected != scope.get("selected_skills"):
            raise SystemExit("неполные метаданные выбранных навыков")
        if any(item["owner"] not in selected for item in inputs):
            raise SystemExit("вход находится вне сохранённого охвата")
    return meta, inputs, scope


def valid_attempts(out, source, model, runs, inputs, known_codes):
    """Первый успешный корректный ответ на пару input/run — один голос."""
    stamp = fingerprint(out, source)
    items = {item["id"]: item for item in inputs}
    valid = {}
    stats = {"failed_calls": 0, "invalid_calls": 0, "duplicate_calls": 0, "stale": 0}
    path = out / "raw" / "answers.jsonl"
    if not path.exists():
        return valid, stats
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            stats["invalid_calls"] += 1
            continue
        if not isinstance(record, dict):
            stats["invalid_calls"] += 1
            continue
        if record.get("model") != model or record.get("source", "examples") != source:
            continue
        if record.get("set_hash") != stamp:
            stats["stale"] += 1
            continue
        input_id, attempt = record.get("input_id"), record.get("run")
        if not isinstance(input_id, str) or input_id not in items or type(attempt) is not int or attempt < 1:
            stats["invalid_calls"] += 1
            continue
        if attempt > runs:
            continue
        if type(record.get("returncode")) is not int:
            stats["invalid_calls"] += 1
            continue
        if record["returncode"] != 0:
            stats["failed_calls"] += 1
            continue
        raw = record.get("raw")
        parsed = parse_answer(raw, known_codes) if isinstance(raw, str) else "UNPARSED"
        item = items[input_id]
        if parsed == "UNPARSED" or any(
            key in record and record[key] != item[key]
            for key in ("owner", "file", "literal_trigger")
        ):
            stats["invalid_calls"] += 1
            continue
        key = (input_id, attempt)
        if key in valid:
            stats["duplicate_calls"] += 1
            continue
        valid[key] = parsed
    return valid, stats


def ask_judge(cli: str, workdir: pathlib.Path, choices: str, text: str, model: str):
    prompt = f"Список процедур:\n{choices}\n\nЗапрос пользователя:\n«{text}»\n\nОтвет:"
    command = [
        cli, "-p",
        "--safe-mode",
        "--tools", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--model", model,
        "--system-prompt", SYSTEM_PROMPT,
        prompt,
    ]
    done = subprocess.run(
        command, capture_output=True, text=True, cwd=str(workdir), timeout=300
    )
    return done.returncode, (done.stdout or "").strip(), (done.stderr or "").strip()


def run(
    out: pathlib.Path, source: str, model: str, runs: int = 1,
    limit: int = 0, workers: int = 6, full: bool = False, dry_run: bool = False,
) -> None:
    if runs < 1 or workers < 1 or limit < 0:
        raise SystemExit("--runs и --workers должны быть положительными, --limit — неотрицательным")
    meta, inputs, scope = load_dataset(out, source)
    if scope["mode"] != "targeted" and not full:
        raise SystemExit("полный или старый набор требует явного run --full")
    stamp = fingerprint(out, source)
    already, _ = valid_attempts(out, source, model, runs, inputs, set(meta["codes"].values()))
    if limit:
        inputs = inputs[:limit]

    jobs = [
        (item, attempt)
        for item in inputs
        for attempt in range(1, runs + 1)
        if (item["id"], attempt) not in already
    ]
    print(f"отпечаток набора: {stamp}")
    print(f"заданий: {len(jobs)} (готовых пропущено: {len(inputs) * runs - len(jobs)})")
    if dry_run:
        print("проверка расхода: процессы судьи не запускались")
        return
    if not jobs:
        return

    cli = os.environ.get("ROUTING_BASELINE_CLI", "claude")
    choices = (out / "choice_list.txt").read_text(encoding="utf-8").strip()
    known_codes = set(meta["codes"].values())
    raw_dir = out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    answers = raw_dir / "answers.jsonl"

    lock = threading.Lock()
    handle = answers.open("a", encoding="utf-8")
    counter = [0]

    def work(job):
        item, attempt = job
        started = time.time()
        try:
            code, stdout, stderr = ask_judge(cli, out, choices, item["text"], model)
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, stdout, stderr = -1, "", str(exc)
        record = {
            "input_id": item["id"],
            "run": attempt,
            "model": model,
            "source": source,
            "set_hash": stamp,
            "owner": item["owner"],
            "file": item["file"],
            "literal_trigger": item["literal_trigger"],
            "returncode": code,
            "raw": stdout,
            "stderr": stderr[:500],
            "parsed": parse_answer(stdout, known_codes),
            "seconds": round(time.time() - started, 1),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with lock:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            counter[0] += 1
            if counter[0] % 25 == 0 or code != 0:
                note = f" ОШИБКА {stderr[:120]}" if code else ""
                print(f'{counter[0]}/{len(jobs)} {item["id"]}#{attempt} → {record["parsed"]}{note}')

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, jobs))
    handle.close()
    print(f"сырые ответы: {answers}")


def report(
    out: pathlib.Path, source: str, model: str, runs: int = 1, allow_partial: bool = False,
) -> None:
    if runs < 1:
        raise SystemExit("--runs должен быть положительным")
    meta, input_rows, scope = load_dataset(out, source)
    codes = meta["codes"]
    names = {code: name for name, code in codes.items()}
    inputs = {item["id"]: item for item in input_rows}

    stamp = fingerprint(out, source)
    votes = collections.defaultdict(list)
    attempts, stats = valid_attempts(out, source, model, runs, input_rows, set(names))
    for (input_id, attempt), parsed in sorted(attempts.items()):
        votes[input_id].append(parsed)

    missing = [key for key in inputs if len(votes.get(key, [])) < runs]
    if missing and not allow_partial:
        raise SystemExit(
            f"замер неполный: входов без {runs} ответов — {len(missing)}, "
            f"некорректных ответов — {stats['invalid_calls']}, "
            f"ответов от другого набора пропущено — {stats['stale']}. "
            "Допрогоните `run` или повторите с `--allow-partial`."
        )
    needed = runs // 2 + 1

    rows, pairs = [], collections.Counter()
    for input_id, given in sorted(votes.items()):
        item = inputs[input_id]
        expected = codes[item["owner"]]
        hit = sum(vote == expected for vote in given) >= needed
        top, top_count = collections.Counter(given).most_common(1)[0]
        went = "—" if hit else (names.get(top, top) if top_count >= needed else "нет большинства")
        rows.append(
            {
                "id": input_id,
                "owner": item["owner"],
                "file": item["file"],
                "literal": item["literal_trigger"],
                "hit": hit,
                "went": went,
                "votes": [names.get(vote, vote) for vote in given],
            }
        )
        if not hit and went in codes:
            pairs[(item["owner"], went)] += 1

    def share(predicate):
        chosen = [row for row in rows if predicate(row)]
        return sum(row["hit"] for row in chosen), len(chosen)

    summary = {
        "source": source,
        "model": model,
        "set_hash": stamp,
        "runs": runs,
        "scope": scope,
        "partial": bool(missing),
        "failed_calls": stats["failed_calls"],
        "invalid_calls": stats["invalid_calls"],
        "duplicate_calls": stats["duplicate_calls"],
        "total": share(lambda row: True),
        "no_literal": share(lambda row: not row["literal"]),
        "literal": share(lambda row: row["literal"]),
        "misses": [row for row in rows if not row["hit"]],
        "pairs": [{"owner": a, "went": b, "count": n} for (a, b), n in pairs.most_common()],
        "rows": rows,
    }
    path = out / f"summary-{source}-{model}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    titles = {"total": "все входы", "no_literal": "без дословного триггера", "literal": "с дословным триггером"}
    for key, title in titles.items():
        hits, total = summary[key]
        tail = f" = {hits / total:.1%}" if total else ""
        print(f"{title}: {hits}/{total}{tail}")
    print(f"отпечаток набора: {stamp}")
    print(f"охват: {scope['mode']}")
    print(f"вызовов с ошибкой: {stats['failed_calls']}")
    print(f"некорректных ответов: {stats['invalid_calls']}")
    print(f"повторных ответов: {stats['duplicate_calls']}")
    if stats["stale"]:
        print(f"пропущено ответов от другого набора: {stats['stale']}")
    if missing:
        print(f"ЧАСТИЧНЫЙ ЗАМЕР: без полных {runs} ответов — {len(missing)}")
    print(f"промахов: {len(summary['misses'])}")
    for pair in summary["pairs"]:
        print(f'  {pair["count"]}  {pair["owner"]} → {pair["went"]}')
    print(f"сводка: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Базовая проверка маршрутизации по входам примеров")
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT, help="рабочая папка вне репозитория")
    parser.add_argument(
        "--source",
        choices=("examples", "triggers"),
        default="examples",
        help="набор входов: тексты хороших примеров или фразы natural_triggers",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    builder = sub.add_parser("build", help="собрать явно выбранный охват")
    selection = builder.add_mutually_exclusive_group(required=True)
    selection.add_argument("--skill", action="append", help="проверяемый навык; можно повторять")
    selection.add_argument("--full", action="store_true", help="полная библиотека по отдельному запросу")
    builder.add_argument("--related", action="append", help="соседний навык; можно повторять")
    runner = sub.add_parser("run", help="необязательный запуск через Claude CLI")
    runner.add_argument("--model", required=True, help="явный идентификатор модели судьи")
    runner.add_argument("--runs", type=int, default=1)
    runner.add_argument("--limit", type=int, default=0, help="только первые N входов")
    runner.add_argument("--workers", type=int, default=6)
    runner.add_argument("--full", action="store_true", help="явно разрешить полный или старый набор")
    runner.add_argument("--dry-run", action="store_true", help="показать число вызовов без запуска судьи")
    reporter = sub.add_parser("report", help="посчитать доли попаданий и промахи")
    reporter.add_argument("--model", required=True, help="идентификатор судьи в сохранённых ответах")
    reporter.add_argument("--runs", type=int, default=1, help="сколько прогонов ожидается на вход")
    reporter.add_argument(
        "--allow-partial",
        action="store_true",
        help="напечатать отчёт по незаконченному замеру, пометив его частичным",
    )
    args = parser.parse_args()

    if args.command == "build":
        build(args.out, args.source, skills=args.skill, related=args.related, full=args.full)
    elif args.command == "run":
        run(args.out, args.source, args.model, args.runs, args.limit, args.workers, args.full, args.dry_run)
    else:
        report(args.out, args.source, args.model, args.runs, args.allow_partial)


if __name__ == "__main__":
    main()
