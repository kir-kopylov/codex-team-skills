from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"


def test_agents_guidance_routes_to_shared_contract() -> None:
    text = AGENTS.read_text(encoding="utf-8")

    assert "The complete shared repository contract lives in `CLAUDE.md`" in text
    assert "plugins/team-skills/.codex-plugin/plugin.json" in text
    assert ".claude-plugin/plugin.json" in text
    assert ".agents/plugins/marketplace.json" in text
    assert ".claude-plugin/marketplace.json" in text
    assert "~/.claude/skills/" in text


def test_agents_guidance_rejects_cross_runtime_search_replace_artifacts() -> None:
    text = AGENTS.read_text(encoding="utf-8")

    forbidden = (
        "(Codex, Codex",
        ".Codex-plugin",
        "~/.Codex/skills/",
        "Codex-sync-smoke",
    )

    for artifact in forbidden:
        assert artifact not in text
