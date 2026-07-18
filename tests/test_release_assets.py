from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml

from conftest import ROOT


BUILD_SCRIPT = ROOT / "scripts" / "build_release_bundle.py"
UTF8_BOM = b"\xef\xbb\xbf"
WINDOWS_PS1_ASSETS = (
    "install-team-skills.ps1",
    "uninstall-team-skills.ps1",
    "remove-team-skills-autoupdate.ps1",
)
NON_POWERSHELL_ASSETS = (
    "install-team-skills.cmd",
    "install-team-skills.command",
    "uninstall-team-skills.command",
    "remove-team-skills-autoupdate.command",
    "manifest.json",
    "team-skills-bundle.zip",
)
EXPECTED_ASSETS = {
    *WINDOWS_PS1_ASSETS,
    *NON_POWERSHELL_ASSETS,
}
BUNDLE_FORBIDDEN_NAMES = {
    "latest.json",
    "latest.json.sig",
    "manifest.json.sig",
    "team-skills-auto-update-with-git-fallback.ps1",
    "team-skills-public-key.pem",
    "team-skills-registry.py",
}
BUNDLE_FORBIDDEN_PREFIXES = (
    "bootstrap-team-skills",
    "refresh-team-skills",
    "update-team-skills",
)


def build_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--root",
            str(ROOT),
            "--dist",
            str(dist),
            "--commit",
            "abcdef1234567890",
            "--run-number",
            "123",
            "--run-attempt",
            "2",
        ],
        cwd=ROOT,
        check=True,
    )
    return dist


def test_release_asset_allowlist_is_exact(tmp_path: Path) -> None:
    dist = build_dist(tmp_path)
    assert {path.name for path in dist.iterdir()} == EXPECTED_ASSETS


def test_windows_ps1_assets_have_one_utf8_bom(tmp_path: Path) -> None:
    dist = build_dist(tmp_path)

    for name in WINDOWS_PS1_ASSETS:
        data = (dist / name).read_bytes()
        assert data.startswith(UTF8_BOM), f"{name} must be UTF-8 with BOM for Windows PowerShell 5.1"
        assert not data.startswith(UTF8_BOM + UTF8_BOM), f"{name} must not contain a double BOM"
        assert not data.decode("utf-8-sig").startswith("\ufeff")


def test_non_powershell_assets_do_not_get_a_bom(tmp_path: Path) -> None:
    dist = build_dist(tmp_path)
    for name in NON_POWERSHELL_ASSETS:
        assert not (dist / name).read_bytes().startswith(UTF8_BOM), f"{name} must not get a PowerShell BOM"


def test_manifest_is_minimal_and_matches_bundle(tmp_path: Path) -> None:
    dist = build_dist(tmp_path)
    manifest = json.loads((dist / "manifest.json").read_text(encoding="utf-8"))

    assert set(manifest) == {"schema_version", "release_tag", "commit", "plugin_version", "bundle"}
    assert manifest["schema_version"] == 1
    assert manifest["release_tag"] == "team-skills-vr123.2-abcdef1"
    assert manifest["commit"] == "abcdef1234567890"
    assert set(manifest["bundle"]) == {"url", "sha256", "size"}

    bundle = dist / "team-skills-bundle.zip"
    assert manifest["bundle"]["url"].endswith(
        f"/{manifest['release_tag']}/team-skills-bundle.zip"
    )
    assert manifest["bundle"]["sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert manifest["bundle"]["size"] == bundle.stat().st_size

    with zipfile.ZipFile(bundle) as archive:
        plugin_manifest = json.loads(
            archive.read("team-skills/.codex-plugin/plugin.json").decode("utf-8")
        )
    assert plugin_manifest["name"] == "team-skills"
    assert plugin_manifest["version"] == manifest["plugin_version"]
    assert plugin_manifest["release_id"] == manifest["release_tag"].removeprefix("team-skills-v")
    assert plugin_manifest["commit"] == manifest["commit"]


def test_release_installers_are_bound_to_the_built_tag(tmp_path: Path) -> None:
    dist = build_dist(tmp_path)
    for name in ("install-team-skills.ps1", "install-team-skills.command"):
        content = (dist / name).read_text(encoding="utf-8-sig")
        assert "team-skills-vr123.2-abcdef1" in content
        assert "__TEAM_SKILLS_RELEASE_TAG__" not in content
        assert "releases/latest/download/manifest.json" not in content


def test_release_does_not_ship_updater_or_signing_runtime(tmp_path: Path) -> None:
    dist = build_dist(tmp_path)
    forbidden = {
        "bootstrap-team-skills.ps1",
        "bootstrap-team-skills.sh",
        "update-team-skills.ps1",
        "update-team-skills.sh",
        "team-skills-status.ps1",
        "team-skills-status.command",
        "refresh-team-skills.command",
        "team-skills-registry.py",
        "team-skills-public-key.pem",
        "latest.json",
        "latest.json.sig",
        "manifest.json.sig",
    }
    assert forbidden.isdisjoint({path.name for path in dist.iterdir()})

    with zipfile.ZipFile(dist / "team-skills-bundle.zip") as archive:
        archive_paths = [Path(name) for name in archive.namelist()]
    for path in archive_paths:
        name = path.name.lower()
        assert "__pycache__" not in path.parts
        assert path.suffix.lower() not in {".pyc", ".pyo"}
        assert name != ".ds_store"
        assert name not in BUNDLE_FORBIDDEN_NAMES
        assert not name.endswith(".sig")
        assert not name.startswith(BUNDLE_FORBIDDEN_PREFIXES)


def test_windows_docs_preserve_ps51_utf8_bom_download(tmp_path: Path) -> None:
    del tmp_path
    docs = [ROOT / "START_HERE_CONNECT_CODEX_SKILLS.md", ROOT / "quickstart.md"]
    markers = ["DownloadData($u)", "UTF8.GetString($b)", "[char]0xFEFF", "UTF8Encoding($true)", "WriteAllText($p,$s,$enc)"]
    for path in docs:
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker in content, f"{path} missing Windows encoding marker: {marker}"


def test_workflow_gates_publish_on_both_os_smokes() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert jobs["windows-powershell-smoke"]["runs-on"] == "windows-latest"
    assert jobs["macos-one-shot-smoke"]["runs-on"] == "macos-latest"
    assert jobs["publish"]["needs"] == ["windows-powershell-smoke", "macos-one-shot-smoke"]

    workflow_text = json.dumps(workflow, ensure_ascii=False)
    assert "remove-team-skills-autoupdate.ps1" in workflow_text
    assert "remove-team-skills-autoupdate.command" in workflow_text
    assert "System.Management.Automation.Language.Parser" in workflow_text
    assert "gh release create" in workflow_text
    for forbidden in (
        "TEAM_SKILLS_SIGNING_KEY_PEM",
        "latest.json.sig",
        "manifest.json.sig",
        "Verify production signature",
    ):
        assert forbidden not in workflow_text
