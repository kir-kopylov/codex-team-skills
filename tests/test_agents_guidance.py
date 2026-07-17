from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"


def test_agents_guidance_routes_to_shared_sources_of_truth() -> None:
    text = AGENTS.read_text(encoding="utf-8")

    assert "The complete shared repository workflow lives in `CLAUDE.md`" in text
    assert "machine-readable two-runtime topology lives in `runtime-contract.yaml`" in text
    assert "<!-- BEGIN GENERATED RUNTIME CONTRACT -->" in text
    assert "<!-- END GENERATED RUNTIME CONTRACT -->" in text


def test_agents_guidance_stays_a_compact_entrypoint() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert len(text.splitlines()) <= 130
    assert "It must not become a copied fork of `CLAUDE.md`" in normalized
