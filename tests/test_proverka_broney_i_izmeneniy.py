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


def city_request(number, unit, arrival, departure, status="Заселение", **fields):
    return {
        "BOOKING_ID": number, "KV": unit, "STATUS_NAME": status, "STATUS_TYPE": 1,
        "KV_STATUS": 2, "OTBOY": "F", "IN_TM": arrival, "OUT_TM": departure,
        "CHANNEL": "Тестовый канал", "REGISTERED_DATE": "2030-06-01", **fields,
    }


def city_report(tmp_path, units, bookings, *, first="2030-06-10", until="2030-06-13",
                db_time="2030-06-13T10:00", events=()):
    # Подменена только выборка строк. Классификация, календарь и переходы выполняет код навыка.
    fixture = tmp_path / "data.json"
    fixture.write_text(json.dumps({
        "units": [{"ID": n, "ADR": f"Учебная {n}"} for n in units],
        "bookings": bookings, "events": events,
    }, ensure_ascii=False), encoding="utf-8")
    runner = tmp_path / "run-city.ps1"
    runner.write_text("""
param($Script, $Fixture, $First, $Until, $Now)
$ErrorActionPreference = 'Stop'
$data = Get-Content -Raw -Encoding utf8 $Fixture | ConvertFrom-Json
function Read-Query($sql, $parameters) {
    if ($sql -match 'from SPR_CITY') { return [pscustomobject]@{NAME='Тест'} }
    if ($sql -match 'from KV k where') { return $data.units }
    if ($sql -match 'from ZAIVKA z join') {
        foreach ($row in $data.bookings) {
            $row.IN_TM = [datetime]$row.IN_TM
            $row.OUT_TM = [datetime]$row.OUT_TM
            $row
        }
        return
    }
    if ($sql -match 'from ZAIVKA_HIS h') { return $data.events }
    if ($sql -match 'from ARH_ZAIVKA') { return }
    throw "Неизвестный запрос в тесте: $sql"
}
$cities = [pscustomobject]@{'Тест'=[pscustomobject]@{BranchId=7;OwnerId=9}}
& $Script -City 'Тест' -Cities $cities -From $First -Until $Until -DbTime $Now -StartHour 22 -EndHour 6 | ConvertTo-Json -Depth 8
""", encoding="utf-8")
    output = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(runner), str(SCRIPT.with_name("city-nights.ps1")),
         str(fixture), first, until, db_time],
        check=True, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    return json.loads(output.stdout)


def test_three_nights_counts_and_transitions_follow_the_same_apartments(tmp_path):
    nights = city_report(tmp_path, range(1, 10), [
        city_request(21, 1, "2030-06-12T01:00", "2030-06-14T12:00"),
        city_request(22, 2, "2030-06-12T20:00", "2030-06-14T12:00",
                     status="Подтверждена", CHANNEL="Сотрудник компании", ZERO_CHARGE=0),
        city_request(23, 3, "2030-06-12T22:00", "2030-06-14T12:00"),
        city_request(24, 4, "2030-06-12T23:00", "2030-06-14T12:00"),
        city_request(25, 5, "2030-06-10T14:00", "2030-06-14T12:00", OTBOY="T"),
        city_request(26, 6, "2030-06-10T14:00", "2030-06-14T12:00", "Уборка прогнозная", STATUS_TYPE=4),
        city_request(27, 7, "2030-06-10T14:00", "2030-06-14T12:00", "Ремонт", STATUS_TYPE=6),
        city_request(28, 8, "2030-06-10T14:00", "2030-06-14T12:00", "Особый статус", KV_STATUS=None),
        city_request(29, 9, "2030-06-10T14:00", "2030-06-14T12:00", CHANNEL="Сотрудник компании", ZERO_CHARGE=1),
    ], events=[{"ID": 21, "FIRST_RESERVE_AT": "2030-06-08T16:45:00"}])["Nights"]
    assert [n["Counts"]["Free"] for n in nights] == [5, 4, 1]
    assert all(sum(n["Counts"].values()) == 9 for n in nights)
    assert all(n["Counts"][kind] == 1 for n in nights for kind in ("Cleaning", "Blocked", "Unknown", "InternalStay"))
    closed = [[booking for unit in n["Apartments"] for booking in unit["ClosedByBookings"]] for n in nights]
    assert [[(b["KV"], b["BOOKING_ID"]) for b in night] for night in closed] == [[], [(1, 21)], [(2, 22), (3, 23), (4, 24)]]
    assert closed[1][0]["FirstReserveAt"].startswith("2030-06-08T16:45")
    assert closed[2][0]["FirstReserveAt"] is None
    assert closed[1][0]["CHANNEL"] == "Тестовый канал"


def test_single_night_reads_previous_even_if_vacancy_count_is_unchanged(tmp_path):
    night, = city_report(tmp_path, [1, 2, 3], [
        city_request(31, 1, "2030-06-10T21:00", "2030-06-11T12:00"),
        city_request(32, 2, "2030-06-09T21:00", "2030-06-10T12:00"),
        city_request(33, 3, "2030-06-10T16:00", "2030-06-10T22:00"),
        city_request(34, 3, "2030-06-11T06:00", "2030-06-11T10:00"),
    ], until="2030-06-11", db_time="2030-06-11T01:00")["Nights"]
    assert night["Counts"]["Free"] == 2
    assert night["IsPartial"] is True
    assert [b["BOOKING_ID"] for u in night["Apartments"] for b in u["ClosedByBookings"]] == [31]
    assert [u["ID"] for u in night["Apartments"] if u["State"] == "Free"] == [2, 3]
