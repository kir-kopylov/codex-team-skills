from __future__ import annotations

import py_compile

from conftest import ROOT, load_registry


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "dopsoglasheniya-po-oplate"


def test_dopsoglasheniya_asset_has_owner_and_team_ready_status() -> None:
    registry = load_registry(SKILL_DIR)
    assert registry["owner"] == "@elizaveta"
    assert "Елизавета" in registry.get("authors", [])
    assert registry["status"] == "team-ready"


def test_dopsoglasheniya_generator_has_no_nul_bytes_and_compiles(tmp_path) -> None:
    script = SKILL_DIR / "scripts" / "build_ds.py"
    source = script.read_bytes()
    assert b"\x00" not in source
    py_compile.compile(str(script), cfile=str(tmp_path / "build_ds.pyc"), doraise=True)
