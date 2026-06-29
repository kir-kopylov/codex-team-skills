from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from conftest import ROOT


REGISTRY_HELPER = ROOT / "installer" / "team-skills-registry.py"
UPDATE_SH = ROOT / "installer" / "update-team-skills.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


def _load_registry_module():
    # Имя файла с дефисами не импортируется обычным import — грузим по пути.
    spec = importlib.util.spec_from_file_location("team_skills_registry", REGISTRY_HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_helper(*args: str):
    result = subprocess.run(
        [sys.executable, str(REGISTRY_HELPER), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def test_registry_helper_is_idempotent_and_preserves_unrelated_config(tmp_path: Path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '[projects."/tmp/example"]\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )

    for _ in range(2):
        subprocess.run(
            [
                sys.executable,
                str(REGISTRY_HELPER),
                "ensure",
                "--config",
                str(config),
                "--marketplace-root",
                str(tmp_path),
            ],
            check=True,
            text=True,
            capture_output=True,
        )

    text = config.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    assert parsed["projects"]["/tmp/example"]["trust_level"] == "trusted"
    assert parsed["marketplaces"]["codex-team-skills"]["source"] == str(tmp_path)
    assert parsed["plugins"]["team-skills@codex-team-skills"]["enabled"] is True
    assert text.count("[marketplaces.codex-team-skills]") == 1
    assert text.count('[plugins."team-skills@codex-team-skills"]') == 1


def test_registry_helper_remove_only_managed_entries(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    subprocess.run(
        [
            sys.executable,
            str(REGISTRY_HELPER),
            "ensure",
            "--config",
            str(config),
            "--marketplace-root",
            str(tmp_path),
        ],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(REGISTRY_HELPER), "remove", "--config", str(config)],
        check=True,
    )
    text = config.read_text(encoding="utf-8")
    tomllib.loads(text)
    assert "codex-team-skills" not in text


# --- регресс rescue-ветки strip_managed_content ----------------------------
# Историческая bug-fix: чужие stanzas, по ошибке попавшие ВНУТРЬ managed-блока
# (например browser@/chrome@openai-bundled), при ensure должны спасаться наружу,
# а не молча удаляться вместе с нашим блоком.

MANAGED_BEGIN = "# BEGIN codex-team-skills managed block"
MANAGED_END = "# END codex-team-skills managed block"


def _config_with_trapped_foreign_plugin(marketplace_source: str = "/old/source") -> str:
    return (
        '[plugins."keep-me@local"]\n'
        "enabled = true\n"
        "\n"
        f"{MANAGED_BEGIN}\n"
        "[marketplaces.codex-team-skills]\n"
        f'source = "{marketplace_source}"\n'
        "\n"
        '[plugins."team-skills@codex-team-skills"]\n'
        "enabled = true\n"
        "\n"
        '[plugins."browser@chrome-bundled"]\n'
        "enabled = true\n"
        'extra = "x"\n'
        f"{MANAGED_END}\n"
    )


def test_strip_managed_content_rescues_foreign_stanza_unit() -> None:
    mod = _load_registry_module()
    stripped = mod.strip_managed_content(_config_with_trapped_foreign_plugin())
    parsed = tomllib.loads(stripped)

    # наши собственные записи удалены
    assert "codex-team-skills" not in parsed.get("marketplaces", {})
    assert "team-skills@codex-team-skills" not in parsed.get("plugins", {})

    # чужой плагин и не наша запись сохранены вне блока
    assert parsed["plugins"]["keep-me@local"]["enabled"] is True
    rescued = parsed["plugins"]["browser@chrome-bundled"]
    assert rescued["enabled"] is True and rescued["extra"] == "x"

    # ни одного маркера managed-блока в результате
    assert MANAGED_BEGIN not in stripped and MANAGED_END not in stripped


def test_ensure_rescues_foreign_plugin_trapped_in_managed_block(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(_config_with_trapped_foreign_plugin(), encoding="utf-8")

    _run_helper("ensure", "--config", str(config), "--marketplace-root", str(tmp_path))

    text = config.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)

    # чужой плагин пережил ensure и остался включённым
    assert parsed["plugins"]["browser@chrome-bundled"]["enabled"] is True
    assert parsed["plugins"]["keep-me@local"]["enabled"] is True
    # наш блок переустановлен ровно один раз
    assert parsed["plugins"]["team-skills@codex-team-skills"]["enabled"] is True
    assert text.count(MANAGED_BEGIN) == 1 and text.count(MANAGED_END) == 1
    assert parsed["marketplaces"]["codex-team-skills"]["source"] == str(tmp_path)


def test_ensure_collapses_duplicate_managed_blocks(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    one_block = (
        f"{MANAGED_BEGIN}\n"
        "[marketplaces.codex-team-skills]\n"
        'source = "/stale"\n'
        '[plugins."team-skills@codex-team-skills"]\n'
        "enabled = true\n"
        f"{MANAGED_END}\n"
    )
    config.write_text(one_block + "\n" + one_block, encoding="utf-8")

    _run_helper("ensure", "--config", str(config), "--marketplace-root", str(tmp_path))

    text = config.read_text(encoding="utf-8")
    tomllib.loads(text)  # не должно быть дублей таблиц — иначе TOML невалиден
    assert text.count(MANAGED_BEGIN) == 1
    assert text.count("[marketplaces.codex-team-skills]") == 1


def test_ensure_and_remove_create_backups(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[projects."/x"]\ntrust_level = "trusted"\n', encoding="utf-8")

    ensure_payload = _run_helper("ensure", "--config", str(config), "--marketplace-root", str(tmp_path))
    assert ensure_payload["ok"] is True
    assert ensure_payload["backup_path"] and Path(ensure_payload["backup_path"]).exists()

    remove_payload = _run_helper("remove", "--config", str(config))
    assert remove_payload["ok"] is True
    assert remove_payload["backup_path"] and Path(remove_payload["backup_path"]).exists()

    # бэкап-имена имеют секундную гранулярность, поэтому достаточно убедиться,
    # что обе операции отчитались о созданном бэкапе и хотя бы один файл на месте
    assert list(tmp_path.glob("config.toml.codex-team-skills.bak.*"))


def test_status_reports_managed_state_before_and_after(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"

    _run_helper("ensure", "--config", str(config), "--marketplace-root", str(tmp_path))
    after_ensure = _run_helper("status", "--config", str(config))
    assert after_ensure["managed_block"] is True
    assert after_ensure["marketplace_registered"] is True
    assert after_ensure["plugin_enabled"] is True
    assert after_ensure["toml_valid"] is True

    _run_helper("remove", "--config", str(config))
    after_remove = _run_helper("status", "--config", str(config))
    assert after_remove["managed_block"] is False
    assert after_remove["marketplace_registered"] is False
    assert after_remove["plugin_enabled"] is False
    assert after_remove["toml_valid"] is True


def test_updater_declares_codex_cache_invalidation_contract() -> None:
    content = UPDATE_SH.read_text(encoding="utf-8")
    assert ".codex/plugins/cache/$MARKETPLACE_NAME" in content
    assert "invalidate_codex_plugin_cache" in content
    assert "codex_plugin_cache_invalidated_path" in content
    assert "CODEX_TEAM_SKILLS_ALLOW_UNSIGNED" in content
    assert "--repair-install" in content
    assert "runtime_visibility" in content


def test_macos_repair_install_invalidates_codex_plugin_cache(tmp_path: Path) -> None:
    if not shutil.which("zsh"):
        return

    plugin_dest = tmp_path / "plugins" / "team-skills"
    manifest_path = plugin_dest / ".codex-plugin" / "plugin.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "name": "team-skills",
                "version": "0.1.0-r.test",
                "product_version": "0.1.0",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    stale_cache = tmp_path / ".codex" / "plugins" / "cache" / "codex-team-skills"
    stale_skill = stale_cache / "team-skills" / "0.1.0" / "skills" / "old" / "SKILL.md"
    stale_skill.parent.mkdir(parents=True)
    stale_skill.write_text("# stale\n", encoding="utf-8")

    install_root = tmp_path / "Application Support" / "CodexTeamSkills"
    codex_config = tmp_path / ".codex" / "config.toml"
    marketplace = tmp_path / ".agents" / "plugins" / "marketplace.json"

    result = subprocess.run(
        ["zsh", str(UPDATE_SH), "--repair-install"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        env={
            "HOME": str(tmp_path),
            "PATH": f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
            "CODEX_TEAM_SKILLS_HOME": str(install_root),
            "CODEX_TEAM_SKILLS_PLUGIN_DIR": str(plugin_dest),
            "CODEX_TEAM_SKILLS_MARKETPLACE_ROOT": str(tmp_path),
            "CODEX_TEAM_SKILLS_MARKETPLACE": str(marketplace),
            "CODEX_TEAM_SKILLS_CODEX_CONFIG": str(codex_config),
            "CODEX_TEAM_SKILLS_REGISTRY_HELPER": str(REGISTRY_HELPER),
            "CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR": str(stale_cache),
        },
    )

    assert "Codex plugin cache invalidated" in result.stdout
    assert not stale_cache.exists()
    stale_dirs = list(stale_cache.parent.glob("codex-team-skills.stale.*"))
    assert len(stale_dirs) == 1
    assert (stale_dirs[0] / "team-skills" / "0.1.0" / "skills" / "old" / "SKILL.md").exists()

    state = json.loads((install_root / "state" / "state.json").read_text(encoding="utf-8"))
    assert state["codex_plugin_cache_path"] == str(stale_cache)
    assert state["codex_plugin_cache_invalidated_path"] == str(stale_dirs[0])
    assert "cache invalidation" in state["runtime_visibility"]


def test_release_workflow_contains_signed_immutable_schema() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "build_release_bundle.py").read_text(encoding="utf-8")
    for marker in ("latest.json", "manifest.json.sig", "latest.json.sig", "TEAM_SKILLS_SIGNING_KEY_PEM"):
        assert marker in content
    for marker in ("runtime_version", "release_id", "minimum_bootstrap_version", "team-skills-v"):
        assert marker in build_script
    assert "windows-powershell-smoke" in content
    assert "claude-sync-smoke" in content
    assert "pull-skills.sh" in content
    assert "CLAUDE_SKILLS_DIR" in content


def test_public_key_is_valid_pem() -> None:
    public_key = (ROOT / "installer" / "team-skills-public-key.pem").read_text(encoding="utf-8")
    assert public_key.startswith("-----BEGIN PUBLIC KEY-----")
    assert public_key.rstrip().endswith("-----END PUBLIC KEY-----")
