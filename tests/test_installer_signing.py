"""Тесты доставки для shell-установщиков и пути проверки подписи.

Закрывают пункт #5 анализа покрытия:

1. bash `-n` syntax-smoke для всех `.sh`/`.command` — паритет с windows-
   powershell-smoke, которая парсит `.ps1`. Ловит синтаксический регресс до
   того, как он дойдёт до пользователя.
2. Целостность якоря доверия: sha256 закреплённого `team-skills-public-key.pem`
   совпадает с pin'ом в ОБОИХ апдейтерах (.sh и .ps1). Расхождение ключа и
   pin'а молча запрещает любое обновление.
3. End-to-end проверка подписи тем же примитивом openssl, что использует
   апдейтер (`openssl dgst -sha256 -verify`): корректная подпись принимается,
   подделанный payload отвергается.
"""

from __future__ import annotations

import base64
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT


PUBLIC_KEY = ROOT / "installer" / "team-skills-public-key.pem"
UPDATE_SH = ROOT / "installer" / "update-team-skills.sh"
UPDATE_PS1 = ROOT / "installer" / "update-team-skills.ps1"
ADMIN_GUIDE = ROOT / "admin-onboarding-guide.md"
WINDOWS_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "windows-signature"
WINDOWS_FIXTURE_PAYLOAD = WINDOWS_FIXTURE_DIR / "latest.json"
WINDOWS_FIXTURE_SIGNATURE = WINDOWS_FIXTURE_DIR / "latest.json.sig"

# Shell-скрипты, которые обязаны парситься bash'ем (.cmd — batch, .ps1 — PowerShell).
SHELL_SCRIPTS = sorted(
    [*(ROOT / "installer").glob("*.sh"),
     *(ROOT / "installer").glob("*.command"),
     *(ROOT / "scripts").glob("*.sh")]
)


@pytest.mark.skipif(shutil.which("bash") is None, reason="нужен bash для -n syntax-smoke")
@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_shell_scripts_pass_bash_syntax_check(script: Path) -> None:
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"{script.name} не прошёл bash -n:\n{result.stderr}"


def test_shell_script_set_is_non_empty() -> None:
    # защита от тихого «0 скриптов» из-за опечатки в glob
    assert SHELL_SCRIPTS, "не найдено ни одного shell-скрипта для проверки"
    names = {p.name for p in SHELL_SCRIPTS}
    assert "update-team-skills.sh" in names
    assert "pull-skills.sh" in names


# --- целостность якоря доверия ---------------------------------------------

def _extract_pin(text: str) -> str:
    # bash: EXPECTED_PUBLIC_KEY_SHA256="..."  /  ps1: $ExpectedPublicKeySha256 = "..."
    match = re.search(r'(?:EXPECTED_PUBLIC_KEY_SHA256|ExpectedPublicKeySha256)\s*=\s*"([0-9a-f]{64})"', text)
    assert match, "не найден pinned sha256 public key в апдейтере"
    return match.group(1)


def test_public_key_pin_matches_shipped_key_in_both_updaters() -> None:
    actual = hashlib.sha256(PUBLIC_KEY.read_bytes()).hexdigest()
    sh_pin = _extract_pin(UPDATE_SH.read_text(encoding="utf-8"))
    ps1_pin = _extract_pin(UPDATE_PS1.read_text(encoding="utf-8"))

    assert sh_pin == actual, "pin в update-team-skills.sh разошёлся с реальным public key"
    assert ps1_pin == actual, "pin в update-team-skills.ps1 разошёлся с реальным public key"
    assert sh_pin == ps1_pin, "pin'ы в .sh и .ps1 апдейтерах должны совпадать"


@pytest.mark.skipif(shutil.which("openssl") is None, reason="нужен openssl для чтения RSA public key")
def test_windows_pinned_rsa_parameters_match_shipped_public_key() -> None:
    content = UPDATE_PS1.read_text(encoding="utf-8")
    modulus_match = re.search(r'PinnedPublicKeyModulusBase64\s*=\s*"([A-Za-z0-9+/=]+)"', content)
    exponent_match = re.search(r'PinnedPublicKeyExponentBase64\s*=\s*"([A-Za-z0-9+/=]+)"', content)
    assert modulus_match and exponent_match, "в Windows updater не найдены закреплённые RSA parameters"

    result = subprocess.run(
        ["openssl", "rsa", "-pubin", "-in", str(PUBLIC_KEY), "-modulus", "-noout"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    openssl_modulus = result.stdout.strip().removeprefix("Modulus=").lower()

    embedded_modulus = base64.b64decode(modulus_match.group(1))
    embedded_exponent = base64.b64decode(exponent_match.group(1))
    assert embedded_modulus.hex() == openssl_modulus
    assert int.from_bytes(embedded_exponent, "big") == 65537
    assert ".ImportFromPem(" not in content
    for marker in (
        "RSACryptoServiceProvider",
        "ProviderType = 24",
        "ImportParameters",
        'MapNameToOID("SHA256")',
        "VerifySignatureOnly",
    ):
        assert marker in content


def test_key_rotation_runbook_updates_all_windows_trust_material() -> None:
    content = ADMIN_GUIDE.read_text(encoding="utf-8")
    for marker in (
        "installer/team-skills-public-key.pem",
        "EXPECTED_PUBLIC_KEY_SHA256",
        "$PinnedPublicKeyModulusBase64",
        "$PinnedPublicKeyExponentBase64",
        "tests/fixtures/windows-signature/latest.json",
        "PEM, оба pin, встроенные RSA-параметры и fixture должны меняться одним PR",
    ):
        assert marker in content


# --- e2e проверки подписи ---------------------------------------------------


@pytest.mark.skipif(shutil.which("openssl") is None, reason="нужен openssl для e2e проверки подписи")
def test_production_windows_fixture_accepts_valid_and_rejects_tampered(tmp_path: Path) -> None:
    assert WINDOWS_FIXTURE_PAYLOAD.exists()
    assert WINDOWS_FIXTURE_SIGNATURE.exists()
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "tests/fixtures/windows-signature/latest.json text eol=lf" in attributes
    assert "tests/fixtures/windows-signature/latest.json.sig binary" in attributes

    valid = subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(PUBLIC_KEY),
            "-signature",
            str(WINDOWS_FIXTURE_SIGNATURE),
            str(WINDOWS_FIXTURE_PAYLOAD),
        ],
        capture_output=True,
        text=True,
    )
    assert valid.returncode == 0, valid.stderr

    tampered = tmp_path / "latest.json"
    payload = bytearray(WINDOWS_FIXTURE_PAYLOAD.read_bytes())
    payload[0] ^= 1
    tampered.write_bytes(payload)
    invalid = subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(PUBLIC_KEY),
            "-signature",
            str(WINDOWS_FIXTURE_SIGNATURE),
            str(tampered),
        ],
        capture_output=True,
        text=True,
    )
    assert invalid.returncode != 0, "изменённый production payload не должен проходить подпись"

@pytest.mark.skipif(shutil.which("openssl") is None, reason="нужен openssl для e2e проверки подписи")
def test_openssl_signature_primitive_accepts_valid_and_rejects_tampered(tmp_path: Path) -> None:
    private_key = tmp_path / "priv.pem"
    public_key = tmp_path / "pub.pem"
    payload = tmp_path / "manifest.json"
    signature = tmp_path / "manifest.json.sig"

    # свежая RSA-пара (тестируем механизм проверки, а не закреплённый ключ)
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private_key)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True, capture_output=True,
    )

    payload.write_text('{"runtime_version": "1.2.3", "release_id": "team-skills-v1.2.3"}', encoding="utf-8")

    # подпись тем же алгоритмом, что и в CI/апдейтере: RSA + SHA256
    subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(private_key), "-out", str(signature), str(payload)],
        check=True, capture_output=True,
    )

    # та же команда проверки, что в verify_signature() апдейтера
    def verify() -> int:
        return subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(public_key), "-signature", str(signature), str(payload)],
            capture_output=True,
        ).returncode

    assert verify() == 0, "валидная подпись должна проходить проверку"

    # подделанный payload обязан отвергаться
    payload.write_text('{"runtime_version": "9.9.9", "release_id": "evil"}', encoding="utf-8")
    assert verify() != 0, "подделанный payload не должен проходить проверку подписи"


@pytest.mark.skipif(shutil.which("openssl") is None, reason="нужен openssl для e2e проверки подписи")
def test_shipped_public_key_loads_as_rsa(tmp_path: Path) -> None:
    # апдейтеры используют RSA + PKCS1 — ключ обязан читаться как RSA public key
    result = subprocess.run(
        ["openssl", "rsa", "-pubin", "-in", str(PUBLIC_KEY), "-noout", "-text"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"public key не читается как RSA: {result.stderr}"
    assert "Public-Key" in result.stdout
