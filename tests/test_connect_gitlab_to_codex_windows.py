from __future__ import annotations

import base64
import codecs
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "connect-gitlab-to-codex-windows"
CONNECT_SCRIPT = SKILL_DIR / "scripts" / "connect-gitlab-account.ps1"


def test_connect_script_keeps_token_out_of_arguments_and_output() -> None:
    assert CONNECT_SCRIPT.read_bytes().startswith(codecs.BOM_UTF8), (
        "Windows PowerShell 5.1 требует UTF-8 BOM для надёжного разбора русского текста"
    )
    script = CONNECT_SCRIPT.read_text(encoding="utf-8")

    for required in (
        "Read-Host 'Personal Access Token (ввод скрыт)' -AsSecureString",
        "SecureStringToBSTR",
        "ZeroFreeBSTR",
        "credential-manager store --no-ui",
        "credential-manager get --no-ui",
        "LOCAL_CREDENTIAL_READY",
        "Удалённый доступ к GitLab: не проверен",
    ):
        assert required in script

    for forbidden in (
        "Write-Output $plainToken",
        "Write-Host $plainToken",
        "https://$gitLabUser:$plainToken@",
    ):
        assert forbidden not in script


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="нужен Windows PowerShell")
def test_connect_script_runs_with_mocked_gcm_without_secret_in_output() -> None:
    script_path = str(CONNECT_SCRIPT).replace("'", "''")
    harness = rf"""
$global:MockStored = ''

function global:git {{
    $stdinLines = @($input)
    $command = $args -join ' '
    switch -Regex ($command) {{
            '^--version$' {{
                $global:LASTEXITCODE = 0
                'git version 2.53.0.windows.2'
                break
            }}
            '^credential-manager --version$' {{
                $global:LASTEXITCODE = 0
                '2.7.3-test'
                break
            }}
            '^config --get-all credential.helper$' {{
                $global:LASTEXITCODE = 0
                'manager'
                break
            }}
            '^config --get-urlmatch credential.useHttpPath ' {{
                $global:LASTEXITCODE = 1
                break
            }}
            '^credential-manager store --no-ui$' {{
                $global:MockStored = $stdinLines -join "`n"
                $global:LASTEXITCODE = 0
                break
            }}
            '^credential-manager get --no-ui$' {{
                $global:LASTEXITCODE = 0
                'protocol=https'
                'host=gitlab.test'
                'username=skill-test-user'
                'password=fake-secret-for-test'
                break
            }}
        default {{ throw "Неожиданная mock-команда git: $command" }}
    }}
}}

function global:Read-Host {{
    param(
        [Parameter(Position = 0)]
        [string]$Prompt,
        [switch]$AsSecureString
    )

    if ($AsSecureString) {{
        return ConvertTo-SecureString 'fake-secret-for-test' -AsPlainText -Force
    }}
    return 'skill-test-user'
}}

$output = & '{script_path}' -GitLabHost gitlab.test
$outputText = $output -join "`n"

if ($outputText -notmatch 'LOCAL_CREDENTIAL_READY') {{
    throw 'Script не выдал LOCAL_CREDENTIAL_READY.'
}}
if ($outputText -match 'fake-secret-for-test') {{
    throw 'Синтетический token попал в вывод.'
}}
if ($global:MockStored -notmatch 'password=fake-secret-for-test') {{
    throw 'GCM mock не получил credential payload.'
}}
"""
    encoded = base64.b64encode(harness.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-EncodedCommand", encoded],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, (result.stdout + result.stderr).decode(errors="replace")


def test_skill_preserves_authentication_evidence_ladder() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    playbook = (SKILL_DIR / "references" / "domain-playbook.md").read_text(encoding="utf-8")
    combined = skill + playbook
    normalized = combined.lower()

    for required in (
        "TOKEN_CREATED",
        "LOCAL_CREDENTIAL_READY",
        "REMOTE_READ_VERIFIED",
        "Публичный repo не подходит",
        "/api/v4/user",
        "не угадывайте namespace",
        "write_repository",
        "не поддерживает API-аутентификацию",
    ):
        assert required.lower() in normalized


def test_every_known_exception_points_to_a_shipped_example() -> None:
    import yaml

    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    for item in data["exceptions"]:
        assert (SKILL_DIR / item["source_example"]).exists()
