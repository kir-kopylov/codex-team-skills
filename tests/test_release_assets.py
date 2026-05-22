from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

from conftest import ROOT


BUILD_SCRIPT = ROOT / "scripts" / "build_release_bundle.py"
UTF8_BOM = b"\xef\xbb\xbf"
WINDOWS_PS1_ASSETS = (
    "install-team-skills.ps1",
    "bootstrap-team-skills.ps1",
    "update-team-skills.ps1",
    "uninstall-team-skills.ps1",
    "team-skills-status.ps1",
)
NON_POWERSHELL_ASSETS = (
    "install-team-skills.cmd",
    "install-team-skills.command",
    "bootstrap-team-skills.sh",
    "update-team-skills.sh",
    "uninstall-team-skills.command",
    "team-skills-status.command",
    "team-skills-registry.py",
    "team-skills-public-key.pem",
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


def test_release_builder_writes_windows_ps1_assets_with_single_utf8_bom(tmp_path: Path) -> None:
    dist = build_dist(tmp_path)

    for name in WINDOWS_PS1_ASSETS:
        data = (dist / name).read_bytes()
        assert data.startswith(UTF8_BOM), f"{name} must be UTF-8 with BOM for Windows PowerShell 5.1"
        assert not data.startswith(UTF8_BOM + UTF8_BOM), f"{name} must not contain a double BOM"
        decoded = data.decode("utf-8-sig")
        assert decoded
        assert not decoded.startswith("\ufeff"), f"{name} must decode without a leading BOM character"
        assert "ValidateOnly" in decoded


def test_release_builder_does_not_add_bom_to_non_powershell_assets(tmp_path: Path) -> None:
    dist = build_dist(tmp_path)

    for name in NON_POWERSHELL_ASSETS:
        assert not (dist / name).read_bytes().startswith(UTF8_BOM), f"{name} must not get a PowerShell BOM"


def test_release_manifest_hashes_final_bom_assets(tmp_path: Path) -> None:
    dist = build_dist(tmp_path)
    manifest = json.loads((dist / "manifest.json").read_text(encoding="utf-8"))
    support_files = {entry["name"]: entry for entry in manifest["support_files"]}

    for name in WINDOWS_PS1_ASSETS:
        data = (dist / name).read_bytes()
        assert support_files[name]["sha256"] == hashlib.sha256(data).hexdigest()
        assert support_files[name]["size"] == len(data)


def test_windows_docs_rewrite_downloaded_installer_as_utf8_with_bom() -> None:
    docs = [
        ROOT / "START_HERE_CONNECT_CODEX_SKILLS.md",
        ROOT / "quickstart.md",
    ]
    markers = [
        "DownloadData($u)",
        "UTF8.GetString($b)",
        "[char]0xFEFF",
        "UTF8Encoding($true)",
        "WriteAllText($p,$s,$enc)",
    ]

    for path in docs:
        content = path.read_text(encoding="utf-8")
        assert "Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $p" not in content
        for marker in markers:
            assert marker in content, f"{path} missing Windows encoding marker: {marker}"


def test_workflow_gates_publish_on_windows_powershell_51_smoke() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert "windows-powershell-smoke" in jobs
    assert jobs["windows-powershell-smoke"]["runs-on"] == "windows-latest"
    assert jobs["windows-powershell-smoke"]["needs"] == "pytest"

    workflow_text = json.dumps(workflow, ensure_ascii=False)
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $path -ValidateOnly" in workflow_text
    assert "System.Management.Automation.Language.Parser" in workflow_text
    assert "0xEF" in workflow_text
    assert "0xBB" in workflow_text
    assert "0xBF" in workflow_text

    publish = jobs["publish"]
    assert publish["needs"] == ["pytest", "windows-powershell-smoke"]
    assert "gh release create" in workflow_text
