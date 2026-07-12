#!/usr/bin/env python3
"""Deterministic adapters and projections for system knowledge domain events."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EVENT_TYPES = {
    "artifact_observed",
    "claim_proposed",
    "evidence_attached",
    "claim_supported",
    "claim_corroborated",
    "claim_contradicted",
    "claim_stale",
    "unknown_opened",
    "unknown_resolved",
    "graph_node_changed",
    "graph_edge_changed",
    "observation_recorded",
    "next_action_ranked",
    "document_promoted",
}
CLAIM_STATE_EVENTS = {
    "claim_supported": "supported",
    "claim_corroborated": "corroborated",
    "claim_contradicted": "contradicted",
    "claim_stale": "stale",
}
PROMOTABLE_CLAIM_STATES = {"supported", "corroborated"}
DEFAULT_EXCLUDES = {".git", ".goal-runtime", "node_modules", "__pycache__", ".pytest_cache"}


class KnowledgeError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sha256_file(path: Path, max_bytes: int | None = None) -> str | None:
    if max_bytes is not None and path.stat().st_size > max_bytes:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_id(kind: str, location: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{location}".encode("utf-8")).hexdigest()[:16]
    return f"artifact-{digest}"


def inspect_filesystem(
    source: Path,
    *,
    max_items: int = 5000,
    excludes: set[str] | None = None,
    hash_max_bytes: int = 1024 * 1024,
) -> dict[str, Any]:
    source = source.resolve()
    if not source.is_dir():
        raise KnowledgeError(f"Filesystem source is not a directory: {source}")
    excluded = excludes or DEFAULT_EXCLUDES
    artifacts: list[dict[str, Any]] = []
    truncated = False
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().lower()):
        relative = path.relative_to(source)
        if any(part in excluded for part in relative.parts):
            continue
        if len(artifacts) >= max_items:
            truncated = True
            break
        if path.is_symlink():
            kind = "symlink"
        elif path.is_dir():
            kind = "directory"
        elif path.is_file():
            kind = "file"
        else:
            kind = "other"
        item: dict[str, Any] = {
            "artifact_id": artifact_id(kind, relative.as_posix()),
            "kind": kind,
            "location": relative.as_posix(),
        }
        if kind == "file":
            item["size_bytes"] = path.stat().st_size
            digest = sha256_file(path, hash_max_bytes)
            item["sha256"] = digest
            item["hash_status"] = "computed" if digest else "skipped_size_limit"
        artifacts.append(item)
    return {
        "adapter": "filesystem",
        "source": str(source),
        "observed_at": utc_now(),
        "excluded_names": sorted(excluded),
        "max_items": max_items,
        "truncated": truncated,
        "artifacts": artifacts,
    }


def run_git(source: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *arguments],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise KnowledgeError(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout.strip()


def inspect_git(source: Path) -> dict[str, Any]:
    source = source.resolve()
    top = Path(run_git(source, "rev-parse", "--show-toplevel")).resolve()
    branch = run_git(source, "branch", "--show-current", check=False) or None
    head = run_git(source, "rev-parse", "HEAD", check=False) or None
    remotes = run_git(source, "remote", "-v", check=False).splitlines()
    status = run_git(source, "status", "--short", "--branch", "--untracked-files=all")
    artifact = {
        "artifact_id": artifact_id("git_repository", str(top)),
        "kind": "git_repository",
        "location": str(top),
        "branch": branch,
        "head": head,
        "remotes": remotes,
        "status_lines": status.splitlines(),
        "dirty": any(line and not line.startswith("##") for line in status.splitlines()),
    }
    return {
        "adapter": "git",
        "source": str(source),
        "observed_at": utc_now(),
        "artifacts": [artifact],
    }


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def inspect_document(source: Path) -> dict[str, Any]:
    source = source.resolve()
    text = source.read_text(encoding="utf-8")
    headings = []
    links = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = HEADING_RE.match(line)
        if match:
            headings.append({"level": len(match.group(1)), "title": match.group(2), "line": number})
        for label, target in LINK_RE.findall(line):
            links.append({"label": label, "target": target, "line": number})
    artifact = {
        "artifact_id": artifact_id("document", str(source)),
        "kind": "document",
        "location": str(source),
        "size_bytes": source.stat().st_size,
        "sha256": sha256_file(source),
        "headings": headings,
        "links": links,
    }
    return {
        "adapter": "document",
        "source": str(source),
        "observed_at": utc_now(),
        "artifacts": [artifact],
    }


def inspect_csv(source: Path, delimiter: str | None = None) -> dict[str, Any]:
    source = source.resolve()
    text = source.read_text(encoding="utf-8-sig")
    sample = text[:8192]
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    rows = list(reader)
    headers = rows[0] if rows else []
    data_rows = rows[1:] if rows else []
    width = len(headers)
    malformed = [index + 2 for index, row in enumerate(data_rows) if len(row) != width]
    normalized_rows = [tuple(row) for row in data_rows]
    duplicates = sum(count - 1 for count in Counter(normalized_rows).values() if count > 1)
    null_counts = {
        header or f"column_{index + 1}": sum(
            1 for row in data_rows if index >= len(row) or not row[index].strip()
        )
        for index, header in enumerate(headers)
    }
    artifact = {
        "artifact_id": artifact_id("csv", str(source)),
        "kind": "csv",
        "location": str(source),
        "sha256": sha256_file(source),
        "delimiter": delimiter,
        "headers": headers,
        "row_count": len(data_rows),
        "column_count": width,
        "null_counts": null_counts,
        "duplicate_row_count": duplicates,
        "malformed_row_numbers": malformed,
    }
    return {
        "adapter": "csv",
        "source": str(source),
        "observed_at": utc_now(),
        "artifacts": [artifact],
    }


def validate_event(event_type: str, payload: dict[str, Any]) -> None:
    if event_type not in EVENT_TYPES:
        raise KnowledgeError(f"Unsupported domain event type: {event_type}")
    required_by_type = {
        "claim_proposed": {"claim_id", "text"},
        "evidence_attached": {"claim_id", "evidence"},
        "claim_supported": {"claim_id"},
        "claim_corroborated": {"claim_id"},
        "claim_contradicted": {"claim_id"},
        "claim_stale": {"claim_id"},
        "unknown_opened": {"unknown_id", "question", "missing_evidence"},
        "unknown_resolved": {"unknown_id", "resolution"},
        "graph_node_changed": {"node_id", "node_type", "name"},
        "graph_edge_changed": {"edge_id", "from", "relation", "to", "evidence"},
        "observation_recorded": {"observation_id", "observation", "evidence"},
        "next_action_ranked": {"action_id", "action", "cost", "uncertainty_reduction"},
        "document_promoted": {"document_id", "path", "claim_ids"},
    }
    missing = required_by_type.get(event_type, set()) - set(payload)
    if missing:
        raise KnowledgeError(f"{event_type} missing fields: {', '.join(sorted(missing))}")
    forbidden_states = {"proven", "proof", "verified_true"}
    state = str(payload.get("state", "")).lower()
    if state in forbidden_states:
        raise KnowledgeError("Claim state 'proven' is forbidden; use supported/corroborated/contradicted/stale")


def goalrt_prefix(explicit: str | None) -> list[str]:
    candidate = explicit or os.environ.get("GOALRT") or shutil.which("goalrt")
    if not candidate:
        raise KnowledgeError("goalrt is unavailable")
    path = Path(candidate)
    if path.suffix.lower() == ".py":
        return [sys.executable, str(path.resolve())]
    return [candidate]


def invoke_goalrt(
    goalrt: str | None,
    arguments: list[str],
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*goalrt_prefix(goalrt), *arguments],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise KnowledgeError(result.stderr.strip() or result.stdout.strip() or "goalrt failed")
    return result


def emit_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    state_root: str | None,
    goalrt: str | None,
    soft_output: str | None,
) -> str:
    validate_event(event_type, payload)
    if soft_output:
        envelope = {
            "mode": "SUPERVISED_SOFT_MODE",
            "event_type": event_type,
            "observed_at": utc_now(),
            "payload": payload,
        }
        output = Path(soft_output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(envelope) + "\n")
        return f"SUPERVISED_SOFT_MODE:{output}"
    if not state_root:
        raise KnowledgeError("--state-root is required unless --soft-output is explicitly used")
    result = invoke_goalrt(
        goalrt,
        [
            "domain",
            "emit",
            event_type,
            "--payload",
            canonical_json(payload),
            "--state-root",
            str(Path(state_root).resolve()),
        ],
    )
    return result.stdout.strip() or "RECORDED"


def load_runtime_journal(state_root: Path, goalrt: str | None) -> list[dict[str, Any]]:
    state_root = state_root.resolve()
    invoke_goalrt(goalrt, ["journal", "verify", "--state-root", str(state_root)])
    contract_path = state_root / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    journal_relative = Path(contract["paths"]["journal"])
    if journal_relative.is_absolute() or ".." in journal_relative.parts:
        raise KnowledgeError("Runtime journal path escapes state root")
    journal_path = state_root / journal_relative
    events = []
    for number, line in enumerate(journal_path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise KnowledgeError(f"Invalid runtime journal line {number}: {exc}") from exc
        if event.get("event_type") != "domain_event":
            continue
        domain = event.get("payload", {})
        event_type = domain.get("domain_event_type")
        payload = domain.get("data")
        if not isinstance(payload, dict):
            raise KnowledgeError(f"Domain event {event.get('event_id')} has no object data")
        validate_event(str(event_type), payload)
        events.append(
            {
                "event_id": event.get("event_id"),
                "timestamp_utc": event.get("timestamp_utc"),
                "event_type": event_type,
                "payload": payload,
            }
        )
    return events


def project_domain_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": "1.0",
        "artifacts": {},
        "claims": {},
        "unknowns": {},
        "graph_nodes": {},
        "graph_edges": {},
        "observations": [],
        "next_actions": {},
        "documents": {},
        "errors": [],
        "derived_through_event_id": None,
    }
    for event in events:
        event_type = event["event_type"]
        payload = event["payload"]
        event_id = event.get("event_id")
        observed_at = event.get("timestamp_utc") or payload.get("observed_at")
        state["derived_through_event_id"] = event_id
        if event_type == "artifact_observed":
            artifacts = payload.get("artifacts", [payload])
            for artifact in artifacts:
                identifier = artifact.get("artifact_id")
                if not identifier:
                    state["errors"].append(f"artifact_observed {event_id} has no artifact_id")
                    continue
                item = dict(artifact)
                item["observed_at"] = payload.get("observed_at") or observed_at
                item["source_event_id"] = event_id
                state["artifacts"][identifier] = item
        elif event_type == "claim_proposed":
            identifier = payload["claim_id"]
            state["claims"][identifier] = {
                **payload,
                "state": "proposed",
                "evidence": [],
                "source_event_id": event_id,
                "updated_at": observed_at,
            }
        elif event_type == "evidence_attached":
            claim = state["claims"].get(payload["claim_id"])
            if not claim:
                state["errors"].append(f"Evidence references missing claim {payload['claim_id']}")
            else:
                evidence = payload["evidence"]
                claim["evidence"].extend(evidence if isinstance(evidence, list) else [evidence])
                claim["updated_at"] = observed_at
        elif event_type in CLAIM_STATE_EVENTS:
            claim = state["claims"].get(payload["claim_id"])
            if not claim:
                state["errors"].append(f"State change references missing claim {payload['claim_id']}")
            else:
                claim["state"] = CLAIM_STATE_EVENTS[event_type]
                claim["state_reason"] = payload.get("reason")
                claim["updated_at"] = observed_at
        elif event_type == "unknown_opened":
            state["unknowns"][payload["unknown_id"]] = {
                **payload,
                "status": "open",
                "source_event_id": event_id,
                "updated_at": observed_at,
            }
        elif event_type == "unknown_resolved":
            unknown = state["unknowns"].get(payload["unknown_id"])
            if not unknown:
                state["errors"].append(f"Resolution references missing unknown {payload['unknown_id']}")
            else:
                unknown.update(payload)
                unknown["status"] = "resolved"
                unknown["updated_at"] = observed_at
        elif event_type == "graph_node_changed":
            state["graph_nodes"][payload["node_id"]] = {
                **payload,
                "source_event_id": event_id,
                "updated_at": observed_at,
            }
        elif event_type == "graph_edge_changed":
            state["graph_edges"][payload["edge_id"]] = {
                **payload,
                "source_event_id": event_id,
                "updated_at": observed_at,
            }
        elif event_type == "observation_recorded":
            state["observations"].append({**payload, "source_event_id": event_id, "observed_at": observed_at})
        elif event_type == "next_action_ranked":
            state["next_actions"][payload["action_id"]] = {
                **payload,
                "source_event_id": event_id,
                "updated_at": observed_at,
            }
        elif event_type == "document_promoted":
            claim_ids = payload["claim_ids"]
            bad = {
                claim_id: state["claims"].get(claim_id, {}).get("state", "missing")
                for claim_id in claim_ids
                if state["claims"].get(claim_id, {}).get("state") not in PROMOTABLE_CLAIM_STATES
            }
            document = {
                **payload,
                "source_event_id": event_id,
                "updated_at": observed_at,
                "promotion_status": "blocked" if bad else "promoted",
                "blocking_claims": bad,
            }
            state["documents"][payload["document_id"]] = document
            if bad:
                state["errors"].append(
                    f"Document {payload['document_id']} promotion blocked by claims {bad}"
                )
    return state


def md(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(md(value) for value in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def render_projections(state: dict[str, Any]) -> dict[str, str]:
    inventory = "# Inventory\n\n" + table(
        ["ID", "Kind", "Location", "Observed at"],
        (
            (identifier, item.get("kind"), item.get("location"), item.get("observed_at"))
            for identifier, item in sorted(state["artifacts"].items())
        ),
    )
    claims = "# Claims\n\n" + table(
        ["ID", "State", "Claim", "Evidence count", "Updated at"],
        (
            (identifier, item.get("state"), item.get("text"), len(item.get("evidence", [])), item.get("updated_at"))
            for identifier, item in sorted(state["claims"].items())
        ),
    )
    unknowns = "# Unknowns\n\n" + table(
        ["ID", "Status", "Question", "Missing evidence", "Owner", "Next action"],
        (
            (
                identifier,
                item.get("status"),
                item.get("question"),
                item.get("missing_evidence"),
                item.get("owner"),
                item.get("next_action"),
            )
            for identifier, item in sorted(state["unknowns"].items())
        ),
    )
    graph = "# Knowledge Graph\n\n## Nodes\n\n" + table(
        ["ID", "Type", "Name", "Evidence"],
        (
            (identifier, item.get("node_type"), item.get("name"), item.get("evidence"))
            for identifier, item in sorted(state["graph_nodes"].items())
        ),
    )
    graph += "\n## Edges\n\n" + table(
        ["ID", "From", "Relation", "To", "Evidence", "Claim state"],
        (
            (
                identifier,
                item.get("from"),
                item.get("relation"),
                item.get("to"),
                item.get("evidence"),
                item.get("claim_state"),
            )
            for identifier, item in sorted(state["graph_edges"].items())
        ),
    )
    observations = "# Observation Ledger\n\n" + table(
        ["ID", "Observation", "Evidence", "Confidence", "Alternative", "Next experiment"],
        (
            (
                item.get("observation_id"),
                item.get("observation"),
                item.get("evidence"),
                item.get("confidence"),
                item.get("alternative_explanation"),
                item.get("next_experiment"),
            )
            for item in state["observations"]
        ),
    )
    roadmap = "# Ranked Next Actions\n\n" + table(
        ["ID", "Action", "Cost", "Uncertainty reduction", "Unlocks", "Risks", "Why now"],
        (
            (
                identifier,
                item.get("action"),
                item.get("cost"),
                item.get("uncertainty_reduction"),
                item.get("unlocks"),
                item.get("risks"),
                item.get("why_now"),
            )
            for identifier, item in sorted(state["next_actions"].items())
        ),
    )
    documents = "# Stable Documentation Candidates\n\n" + table(
        ["ID", "Path", "Status", "Claims", "Blocking claims"],
        (
            (
                identifier,
                item.get("path"),
                item.get("promotion_status"),
                ", ".join(item.get("claim_ids", [])),
                canonical_json(item.get("blocking_claims", {})),
            )
            for identifier, item in sorted(state["documents"].items())
        ),
    )
    return {
        "inventory.md": inventory,
        "claims.md": claims,
        "unknowns.md": unknowns,
        "graph.md": graph,
        "observations.md": observations,
        "roadmap.md": roadmap,
        "stable-doc-candidates.md": documents,
    }


def write_projections(state: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(
        output_dir / "knowledge-state.json",
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    for filename, content in render_projections(state).items():
        atomic_write(output_dir / filename, content)


def command_discover(args: argparse.Namespace) -> int:
    source = Path(args.source)
    if args.adapter == "filesystem":
        payload = inspect_filesystem(
            source,
            max_items=args.max_items,
            excludes=set(args.exclude) if args.exclude else None,
            hash_max_bytes=args.hash_max_bytes,
        )
    elif args.adapter == "git":
        payload = inspect_git(source)
    elif args.adapter == "document":
        payload = inspect_document(source)
    else:
        payload = inspect_csv(source, delimiter=args.delimiter)
    if args.profile:
        payload["profile"] = args.profile
    print(
        emit_event(
            "artifact_observed",
            payload,
            state_root=args.state_root,
            goalrt=args.goalrt,
            soft_output=args.soft_output,
        )
    )
    return 0


def command_event(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        raise KnowledgeError(f"Invalid --payload JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise KnowledgeError("--payload must be a JSON object")
    print(
        emit_event(
            args.event_type,
            payload,
            state_root=args.state_root,
            goalrt=args.goalrt,
            soft_output=args.soft_output,
        )
    )
    return 0


def command_project(args: argparse.Namespace) -> int:
    events = load_runtime_journal(Path(args.state_root), args.goalrt)
    state = project_domain_events(events)
    write_projections(state, Path(args.output_dir).resolve())
    print(
        canonical_json(
            {
                "events": len(events),
                "claims": len(state["claims"]),
                "unknowns": len(state["unknowns"]),
                "errors": len(state["errors"]),
                "output_dir": str(Path(args.output_dir).resolve()),
            }
        )
    )
    return 0


def command_batch(args: argparse.Namespace) -> int:
    source = Path(args.file).resolve()
    try:
        records = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise KnowledgeError(f"Invalid batch JSON: {exc}") from exc
    if not isinstance(records, list) or not records:
        raise KnowledgeError("Batch must be a non-empty JSON array")
    emitted = 0
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise KnowledgeError(f"Batch item {index} must be an object")
        event_type = record.get("event_type")
        payload = record.get("payload")
        if not isinstance(event_type, str) or not isinstance(payload, dict):
            raise KnowledgeError(f"Batch item {index} needs event_type and object payload")
        emit_event(
            event_type,
            payload,
            state_root=args.state_root,
            goalrt=args.goalrt,
            soft_output=args.soft_output,
        )
        emitted += 1
    result: dict[str, Any] = {"events_emitted": emitted, "source": str(source)}
    if args.project_output:
        if args.soft_output:
            raise KnowledgeError("--project-output is unavailable in SUPERVISED_SOFT_MODE")
        events = load_runtime_journal(Path(args.state_root), args.goalrt)
        state = project_domain_events(events)
        output_dir = Path(args.project_output).resolve()
        write_projections(state, output_dir)
        result.update(
            {
                "projection_output": str(output_dir),
                "projection_errors": len(state["errors"]),
            }
        )
    print(canonical_json(result))
    return 0


def command_promote(args: argparse.Namespace) -> int:
    events = load_runtime_journal(Path(args.state_root), args.goalrt)
    state = project_domain_events(events)
    bad = {
        claim_id: state["claims"].get(claim_id, {}).get("state", "missing")
        for claim_id in args.claim_id
        if state["claims"].get(claim_id, {}).get("state") not in PROMOTABLE_CLAIM_STATES
    }
    if bad:
        raise KnowledgeError(f"Stable document promotion blocked by claims: {bad}")
    payload = {
        "document_id": args.document_id,
        "path": args.path,
        "claim_ids": args.claim_id,
        "promoted_at": utc_now(),
    }
    print(
        emit_event(
            "document_promoted",
            payload,
            state_root=args.state_root,
            goalrt=args.goalrt,
            soft_output=None,
        )
    )
    return 0


def add_emit_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-root")
    parser.add_argument("--goalrt")
    parser.add_argument("--soft-output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skb")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover")
    discover.add_argument("adapter", choices=["filesystem", "git", "document", "csv"])
    discover.add_argument("source")
    discover.add_argument("--max-items", type=int, default=5000)
    discover.add_argument("--hash-max-bytes", type=int, default=1024 * 1024)
    discover.add_argument("--exclude", action="append")
    discover.add_argument("--delimiter")
    discover.add_argument("--profile")
    add_emit_options(discover)
    discover.set_defaults(func=command_discover)

    event = subparsers.add_parser("event")
    event.add_argument("event_type", choices=sorted(EVENT_TYPES))
    event.add_argument("--payload", required=True)
    add_emit_options(event)
    event.set_defaults(func=command_event)

    batch = subparsers.add_parser("batch")
    batch.add_argument("file")
    batch.add_argument("--project-output")
    add_emit_options(batch)
    batch.set_defaults(func=command_batch)

    project = subparsers.add_parser("project")
    project.add_argument("--state-root", required=True)
    project.add_argument("--goalrt")
    project.add_argument("--output-dir", required=True)
    project.set_defaults(func=command_project)

    promote = subparsers.add_parser("promote")
    promote.add_argument("--state-root", required=True)
    promote.add_argument("--goalrt")
    promote.add_argument("--document-id", required=True)
    promote.add_argument("--path", required=True)
    promote.add_argument("--claim-id", action="append", required=True)
    promote.set_defaults(func=command_promote)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (KnowledgeError, OSError) as exc:
        print(f"skb: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
