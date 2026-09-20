#!/usr/bin/env python3
"""Проверка маршрутизации на входах из examples/good-*.md.

Три шага:

    python scripts/routing_baseline.py --source examples build
    python scripts/routing_baseline.py --source examples run --model claude-opus-5
    python scripts/routing_baseline.py --source examples report --model claude-opus-5

`build` собирает набор и обезличенный список описаний всех навыков. Набор
`examples` — вход каждого хорошего примера с разметкой «есть ли во входе
дословный natural_trigger»; набор `triggers` — сами фразы `natural_triggers`,
та самая проверка, которая упирается в потолок.
`run` спрашивает независимого судью: каждый вызов — отдельный процесс `claude`
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
import random
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
SHUFFLE_SEED = 20260920

SYSTEM_PROMPT = (
    "Ты маршрутизатор запросов. Тебе дан список процедур с кодами и один запрос "
    "пользователя. Выбери ровно одну процедуру, которая должна обработать запрос, "
    "или ответь «ни один», если ни одна не подходит. Отвечай ТОЛЬКО кодом вида S07 "
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


def build(out: pathlib.Path, source: str) -> None:
    skills = load_skills()
    inputs = []
    for name, skill in skills.items():
        if skill["status"] not in EVAL_STATUSES or name in EXPLICIT_ONLY:
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

    order = sorted(skills)
    random.Random(SHUFFLE_SEED).shuffle(order)
    codes = {name: f"S{i + 1:02d}" for i, name in enumerate(order)}

    out.mkdir(parents=True, exist_ok=True)
    (out / "skills.json").write_text(
        json.dumps({"codes": codes, "skills": skills}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / f"inputs-{source}.json").write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "choice_list.txt").write_text(
        "\n".join(f'{codes[name]}: {skills[name]["description"]}' for name in order) + "\n",
        encoding="utf-8",
    )

    lengths = sorted(len(item["text"]) for item in inputs)
    middle = lengths[len(lengths) // 2] if lengths else 0
    print(f"набор: {source}")
    print(f"навыков всего: {len(skills)}")
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
    return digest.hexdigest()[:12]


def parse_answer(answer: str) -> str:
    match = re.search(r"\bS(\d{2})\b", answer)
    if match:
        return f"S{match.group(1)}"
    if "ни один" in answer.lower():
        return "NONE"
    return "UNPARSED"


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


def run(out: pathlib.Path, source: str, model: str, runs: int, limit: int, workers: int) -> None:
    cli = os.environ.get("ROUTING_BASELINE_CLI", "claude")
    raw_dir = out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    answers = raw_dir / "answers.jsonl"

    stamp = fingerprint(out, source)
    already = set()
    if answers.exists():
        for line in answers.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                already.add(
                    (record["input_id"], record["run"], record["model"], record.get("set_hash"))
                )

    choices = (out / "choice_list.txt").read_text(encoding="utf-8").strip()
    inputs = json.loads((out / f"inputs-{source}.json").read_text(encoding="utf-8"))
    if limit:
        inputs = inputs[:limit]

    jobs = [
        (item, attempt)
        for item in inputs
        for attempt in range(1, runs + 1)
        if (item["id"], attempt, model, stamp) not in already
    ]
    print(f"отпечаток набора: {stamp}")
    print(f"заданий: {len(jobs)} (готовых пропущено: {len(inputs) * runs - len(jobs)})")

    lock = threading.Lock()
    handle = answers.open("a", encoding="utf-8")
    counter = [0]

    def work(job):
        item, attempt = job
        started = time.time()
        code, stdout, stderr = ask_judge(cli, out, choices, item["text"], model)
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
            "parsed": parse_answer(stdout),
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


def report(out: pathlib.Path, source: str, model: str, runs: int, allow_partial: bool) -> None:
    meta = json.loads((out / "skills.json").read_text(encoding="utf-8"))
    codes = meta["codes"]
    names = {code: name for name, code in codes.items()}
    inputs = {
        item["id"]: item
        for item in json.loads((out / f"inputs-{source}.json").read_text(encoding="utf-8"))
    }

    stamp = fingerprint(out, source)
    votes = collections.defaultdict(list)
    failures = 0
    stale = 0
    for line in (out / "raw" / "answers.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["model"] != model or record.get("source", "examples") != source:
            continue
        if record.get("set_hash") != stamp:
            stale += 1
            continue
        failures += record["returncode"] != 0
        votes[record["input_id"]].append(record["parsed"])

    missing = [key for key in inputs if len(votes.get(key, [])) < runs]
    broken = [key for key, given in votes.items() if "UNPARSED" in given]
    if (missing or broken) and not allow_partial:
        raise SystemExit(
            f"замер неполный: входов без {runs} ответов — {len(missing)}, "
            f"с неразобранным ответом — {len(broken)}, "
            f"ответов от другого набора пропущено — {stale}. "
            "Допрогоните `run` или повторите с `--allow-partial`."
        )
    needed = runs // 2 + 1

    rows, pairs = [], collections.Counter()
    for input_id, given in sorted(votes.items()):
        item = inputs[input_id]
        expected = codes[item["owner"]]
        hit = sum(vote == expected for vote in given) >= needed
        top, top_count = collections.Counter(given).most_common(1)[0]
        went = "—" if hit else (names.get(top, top) if top_count >= 2 else "нет большинства")
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
        "partial": bool(missing or broken),
        "failed_calls": failures,
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
    print(f"вызовов с ошибкой: {failures}")
    if stale:
        print(f"пропущено ответов от другого набора: {stale}")
    if missing or broken:
        print(f"ЧАСТИЧНЫЙ ЗАМЕР: без полных {runs} ответов — {len(missing)}, с неразобранным — {len(broken)}")
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
    sub.add_parser("build", help="собрать набор входов и обезличенный список")
    runner = sub.add_parser("run", help="спросить независимого судью")
    runner.add_argument("--model", default="claude-opus-5", help="полный идентификатор модели, не алиас")
    runner.add_argument("--runs", type=int, default=3)
    runner.add_argument("--limit", type=int, default=0, help="только первые N входов")
    runner.add_argument("--workers", type=int, default=6)
    reporter = sub.add_parser("report", help="посчитать доли попаданий и промахи")
    reporter.add_argument("--model", default="claude-opus-5")
    reporter.add_argument("--runs", type=int, default=3, help="сколько прогонов ожидается на вход")
    reporter.add_argument(
        "--allow-partial",
        action="store_true",
        help="напечатать отчёт по незаконченному замеру, пометив его частичным",
    )
    args = parser.parse_args()

    if args.command == "build":
        build(args.out, args.source)
    elif args.command == "run":
        run(args.out, args.source, args.model, args.runs, args.limit, args.workers)
    else:
        report(args.out, args.source, args.model, args.runs, args.allow_partial)


if __name__ == "__main__":
    main()
