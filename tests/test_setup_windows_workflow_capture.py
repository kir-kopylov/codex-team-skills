from __future__ import annotations

import codecs
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "setup-windows-workflow-capture"
    / "scripts"
    / "verify_capture_recording.ps1"
)


def find_windows_tool(name: str) -> str | None:
    on_path = shutil.which(name)
    if on_path:
        return on_path

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    package_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not package_root.exists():
        return None
    return next(
        (str(path) for path in package_root.rglob(name) if "Gyan.FFmpeg" in str(path)),
        None,
    )


POWERSHELL = shutil.which("powershell.exe")
FFMPEG = find_windows_tool("ffmpeg.exe")
FFPROBE = find_windows_tool("ffprobe.exe")


def test_verifier_keeps_windows_powershell_compatible_encoding() -> None:
    assert VERIFY_SCRIPT.read_bytes().startswith(codecs.BOM_UTF8), (
        "Windows PowerShell 5.1 требует UTF-8 BOM для надёжного разбора русского текста"
    )


@pytest.mark.skipif(
    not (POWERSHELL and FFMPEG and FFPROBE),
    reason="для проверки контейнера нужны Windows PowerShell и FFmpeg",
)
def test_verifier_rejects_mp4_even_when_video_and_audio_match(tmp_path: Path) -> None:
    sample = tmp_path / "synthetic-capture.mp4"
    output = tmp_path / "verification"

    generate = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:r=2:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=2",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "2:a:0",
            "-map",
            "3:a:0",
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-c:a",
            "aac",
            "-shortest",
            str(sample),
        ],
        capture_output=True,
        check=False,
    )
    assert generate.returncode == 0, generate.stderr.decode(errors="replace")

    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(VERIFY_SCRIPT),
            "-Path",
            str(sample),
            "-ExpectedWidth",
            "64",
            "-ExpectedHeight",
            "64",
            "-ExpectedFps",
            "2",
            "-MinimumAudioTracks",
            "3",
            "-AudioProbeSeconds",
            "1",
            "-OutputDirectory",
            str(output),
        ],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2, (result.stdout + result.stderr).decode(errors="replace")
    report = json.loads((output / "verification-report.json").read_text(encoding="utf-8-sig"))
    assert report["status"] == "AUTOMATIC_CHECK_FAILED"
    assert report["format"] != "matroska"
    assert report["errors"][:2] == [
        "Расширение файла '.mp4', ожидалось '.mkv'.",
        f"Контейнер '{report['format']}' не является Matroska (MKV).",
    ]
    assert not any(
        marker in error
        for error in report["errors"]
        for marker in ("Ширина", "Высота", "Частота кадров", "Аудиодорожек", "аудиодорожке")
    )
