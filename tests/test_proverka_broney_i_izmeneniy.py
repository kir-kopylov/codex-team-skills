"""Проверки профиля без подключения к рабочей базе (PowerShell 7)."""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/team-skills/skills/proverka-broney-i-izmeneniy/scripts/check-booking.ps1'
PWSH = shutil.which('pwsh')
pytestmark = pytest.mark.skipif(PWSH is None, reason='Нужен PowerShell 7; сценарии проверяются локально на Windows.')

def run(*args: str):
    return subprocess.run([PWSH, '-NoProfile', '-File', str(SCRIPT), *args], capture_output=True, text=True, encoding='utf-8', timeout=30)

@pytest.fixture
def profile(tmp_path):
    # Класса соединения нет: попытка открыть БД в ValidateOnly провалит тест.
    source = tmp_path / 'client.cs'
    source.write_text('''namespace FirebirdSql.Data.FirebirdClient {
public class FbConnectionStringBuilder {
 public string DataSource {get;set;} public int Port {get;set;}
 public string Database {get;set;} public string UserID {get;set;}
 public string Password {get;set;} public string Charset {get;set;}
 public bool Pooling {get;set;} public int ConnectionTimeout {get;set;}
}}''', encoding='utf-8')
    builder = tmp_path / 'build.ps1'
    builder.write_text("param($Source,$Destination)\nAdd-Type -Path $Source -OutputAssembly $Destination\n", encoding='utf-8')
    dll = tmp_path / 'fake.dll'
    subprocess.run([PWSH, '-NoProfile', '-File', str(builder), str(source), str(dll)], check=True, capture_output=True, timeout=30)
    ini = tmp_path / 'settings.ini'
    ini.write_text('[other]\nPassword=do-not-use\n[database]\nPassword=synthetic-sensitive-value\n', encoding='utf-8')
    config = tmp_path / 'profile.json'
    config.write_text(json.dumps(dict(DataSource='example.invalid', Database='synthetic', UserID='reader', ClientDllPath='fake.dll', PasswordIniPath='settings.ini', PasswordIniSection='database', PasswordIniKey='Password')), encoding='utf-8')
    return config, ini

def test_validate_only_uses_relative_profile_paths_without_connecting(profile):
    config, _ = profile
    result = run('-ConfigPath', str(config), '-ValidateOnly')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'ProfileValid': True, 'DatabaseChecked': False}
    assert 'synthetic-sensitive-value' not in result.stdout + result.stderr

@pytest.mark.parametrize('contents', ['[other]\nPassword=synthetic-sensitive-value\n', '[database]\nPassword=synthetic-sensitive-value\nPassword=duplicate-sensitive-value\n'])
def test_missing_or_duplicate_credential_is_rejected_without_exposure(profile, contents):
    config, ini = profile
    ini.write_text(contents, encoding='utf-8')
    result = run('-ConfigPath', str(config), '-ValidateOnly')
    assert result.returncode != 0
    assert 'единственного непустого ключа' in result.stderr
    assert 'synthetic-sensitive-value' not in result.stdout + result.stderr
    assert 'duplicate-sensitive-value' not in result.stdout + result.stderr

def test_ambiguous_selector_is_rejected_before_reading_config():
    result = run('-Address', 'Тестовая', '-BookingId', '100001', '-ConfigPath', 'absent.json')
    assert result.returncode != 0
    assert 'либо адрес, либо номер заявки' in result.stderr
    assert 'Resolve-Path' not in result.stderr
