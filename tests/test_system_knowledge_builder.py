from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from conftest import ROOT


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "system-knowledge-builder"
SCRIPT = SKILL / "scripts" / "skb.py"
SPEC = importlib.util.spec_from_file_location("system_knowledge_builder_skb", SCRIPT)
assert SPEC and SPEC.loader
skb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(skb)


def event(event_id: str, event_type: str, payload: dict) -> dict:
    return {
        "event_id": event_id,
        "timestamp_utc": f"2026-07-12T00:00:0{event_id[-1]}Z",
        "event_type": event_type,
        "payload": payload,
    }


def test_skill_is_domain_only_and_uses_goalrt() -> None:
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    assert "goalrt domain emit" in content
    assert "SUPERVISED_SOFT_MODE" in content
    assert "Состояния claim `proven` не существует" in content
    assert "не владеет budgets" in content
    assert "## Goal Executor" not in content
    assert "eHous / GitLab-kopylov_ke Defaults" not in content
    assert "references/system-knowledge-events.schema.json" in content


def test_ehous_rules_live_only_in_profile() -> None:
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    profile = json.loads(
        (SKILL / "references" / "profiles" / "ehous.json").read_text(encoding="utf-8")
    )

    assert "ALLOW_SELECT_ONLY" not in content
    assert profile["profile_id"] == "ehous"
    assert profile["sql_gate"]["required_token"] == ["ALLOW_SELECT_ONLY", "NO_DB_ACCESS"]


def test_script_does_not_append_runtime_journal_directly() -> None:
    content = (SKILL / "scripts" / "skb.py").read_text(encoding="utf-8")

    assert '"domain",\n            "emit"' in content
    assert "journal.jsonl" not in content
    assert 'open("journal' not in content


def test_filesystem_adapter_is_path_first_and_excludes_runtime_noise(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret-ish metadata\n", encoding="utf-8")

    payload = skb.inspect_filesystem(tmp_path)

    locations = {item["location"] for item in payload["artifacts"]}
    assert "src/app.py" in locations
    assert not any(location.startswith(".git") for location in locations)
    app = next(item for item in payload["artifacts"] if item["location"] == "src/app.py")
    assert app["sha256"]
    assert payload["truncated"] is False


def test_csv_adapter_reports_quality_signals(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("id,name\n1,A\n2,\n2,\n3,B,extra\n", encoding="utf-8")

    payload = skb.inspect_csv(source, delimiter=",")
    artifact = payload["artifacts"][0]

    assert artifact["row_count"] == 4
    assert artifact["null_counts"]["name"] == 2
    assert artifact["duplicate_row_count"] == 1
    assert artifact["malformed_row_numbers"] == [5]


def test_document_adapter_extracts_headings_and_links(tmp_path: Path) -> None:
    source = tmp_path / "README.md"
    source.write_text("# System\n\nSee [runbook](docs/runbook.md).\n## Limits\n", encoding="utf-8")

    payload = skb.inspect_document(source)
    artifact = payload["artifacts"][0]

    assert [item["title"] for item in artifact["headings"]] == ["System", "Limits"]
    assert artifact["links"][0]["target"] == "docs/runbook.md"


def test_projection_keeps_claim_evidence_unknowns_and_graph_separate(tmp_path: Path) -> None:
    events = [
        event("e1", "claim_proposed", {"claim_id": "C1", "text": "Desktop calls WebAPI."}),
        event(
            "e2",
            "evidence_attached",
            {"claim_id": "C1", "evidence": {"source": "src/client.cs:10", "source_type": "static"}},
        ),
        event("e3", "claim_supported", {"claim_id": "C1", "reason": "Direct call site."}),
        event(
            "e4",
            "unknown_opened",
            {
                "unknown_id": "U1",
                "question": "Is this deployed?",
                "missing_evidence": "Dated runtime config",
                "owner": "system owner",
                "next_action": "Inspect deployed config",
            },
        ),
        event(
            "e5",
            "graph_node_changed",
            {"node_id": "N1", "node_type": "service", "name": "WebAPI", "evidence": "C1"},
        ),
    ]

    state = skb.project_domain_events(events)
    skb.write_projections(state, tmp_path / "out")

    assert state["claims"]["C1"]["state"] == "supported"
    assert len(state["claims"]["C1"]["evidence"]) == 1
    assert state["unknowns"]["U1"]["status"] == "open"
    assert state["graph_nodes"]["N1"]["name"] == "WebAPI"
    assert (tmp_path / "out" / "knowledge-state.json").exists()


def test_contradiction_blocks_stable_document_promotion() -> None:
    state = skb.project_domain_events(
        [
            event("e1", "claim_proposed", {"claim_id": "C1", "text": "Current route is X."}),
            event("e2", "claim_supported", {"claim_id": "C1"}),
            event("e3", "claim_contradicted", {"claim_id": "C1", "reason": "Runtime differs."}),
            event(
                "e4",
                "document_promoted",
                {"document_id": "D1", "path": "docs/stable.md", "claim_ids": ["C1"]},
            ),
        ]
    )

    assert state["claims"]["C1"]["state"] == "contradicted"
    assert state["documents"]["D1"]["promotion_status"] == "blocked"
    assert state["documents"]["D1"]["blocking_claims"] == {"C1": "contradicted"}
    assert state["errors"]


def test_proven_claim_state_is_rejected() -> None:
    try:
        skb.validate_event("claim_proposed", {"claim_id": "C1", "text": "x", "state": "proven"})
    except skb.KnowledgeError as exc:
        assert "forbidden" in str(exc)
    else:
        raise AssertionError("proven state must be rejected")


def test_soft_mode_is_explicit_and_not_a_runtime_journal(tmp_path: Path) -> None:
    output = tmp_path / "observation-batch.jsonl"
    result = skb.emit_event(
        "claim_proposed",
        {"claim_id": "C1", "text": "Needs review."},
        state_root=None,
        goalrt=None,
        soft_output=str(output),
    )

    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert result.startswith("SUPERVISED_SOFT_MODE:")
    assert envelope["mode"] == "SUPERVISED_SOFT_MODE"
    assert output.name != "journal.jsonl"


def test_batch_rejects_empty_input(tmp_path: Path) -> None:
    source = tmp_path / "batch.json"
    source.write_text("[]\n", encoding="utf-8")
    args = type(
        "Args",
        (),
        {
            "file": str(source),
            "state_root": None,
            "goalrt": None,
            "soft_output": str(tmp_path / "soft.jsonl"),
            "project_output": None,
        },
    )()

    try:
        skb.command_batch(args)
    except skb.KnowledgeError as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("empty batch must be rejected")
