"""Правила скоростей, безопасный выбор исходника и независимая проверка сжатия."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins/team-skills/skills/uskorenie-zapisi-ekrana/scripts"


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("narration"), importlib.import_module("compact")


@pytest.mark.parametrize(("gap", "expected"), [(2, 1), (2.001, 2), (4, 2), (4.001, 2.5),
                                               (6, 2.5), (10, 3), (16, 3.5), (26, 4),
                                               (42, 4.5), (42.001, 5)])
def test_strict_silence_thresholds(modules, gap, expected):
    n, _ = modules
    rules = n.thresholds("2:2,4:2.5,6:3,10:3.5,16:4,26:4.5,42:5")
    length = round(gap * n.RATE)
    tail = [(length, length + n.RATE)]
    result = n.make_parts(tail[0][1], tail, rules, 1, {"voice": 1.5}, [])
    assert result[0]["speed"] == expected


def test_visual_speeds_protect_voice_and_keep_whole_gap(modules):
    n, _ = modules
    rate = n.RATE
    voices = [(6 * rate, 8 * rate)]
    marks = [(2 * rate, 5 * rate, "keyboard"), (5 * rate, 11 * rate, "wait"),
             (12 * rate, 14 * rate, "answer")]
    rates = dict(voice=1.5, wait=10, keyboard=2, answer=1.5)
    def portions(rules):
        rows = n.make_parts(16 * rate, voices, rules, 1, rates, marks)
        assert n.map_times(rows, 16 * rate)[-1][0] == 16 * rate
        return [(p["start"] // rate, p["end"] // rate, p["kind"], p["speed"]) for p in rows]
    assert portions([]) == [(0, 2, "pause", 1), (2, 5, "keyboard", 2), (5, 6, "wait", 10),
                            (6, 8, "voice", 1.5), (8, 11, "wait", 10), (11, 12, "pause", 1),
                            (12, 14, "answer", 1.5), (14, 16, "pause", 1)]
    scaled = portions(n.thresholds("4:2.5,6:3"))
    assert scaled[0][-1] == 2.5 and scaled[-1][-1] == 3


def test_speech_edges_and_silent_clip(modules):
    n, _ = modules
    assert n.voiced_intervals([0.0] * 30, 15360) == []
    probs = [0.] * 10 + [.8] * 5 + [0.] * 20
    assert n.voiced_intervals(probs, len(probs) * 512) == [[1920, 10880]]
    assert n.voiced_intervals([.9] * 2, 900) == [[0, 900]]


def test_refuse_unverified_or_overlapping_labels(modules, tmp_path):
    n, _ = modules
    p = tmp_path / "labels.json"
    p.write_text(json.dumps([{"kind": "wait", "start": 0, "end": 1, "evidence": ""}]))
    with pytest.raises(ValueError, match="признак"):
        n.visual_labels(p, n.RATE, {"wait": 10})
    row = {"kind": "wait", "start": 0, "end": 1, "evidence": "Индикатор обработки"}
    p.write_text(json.dumps([row, row]))
    with pytest.raises(ValueError, match="пересекающиеся"):
        n.visual_labels(p, n.RATE, {"wait": 10})
    p.write_text(json.dumps([dict(row, end="end")]))
    assert n.visual_labels(p, n.RATE, {"wait": 10}) == [(0, n.RATE, "wait")]


def test_missing_voice_source_and_unconfirmed_export_stop_early(modules, tmp_path, monkeypatch):
    n, _ = modules
    monkeypatch.setattr(n, "probe_source", lambda _: {"has_audio": False})
    out = tmp_path / "result.mp4"
    with pytest.raises(ValueError, match="нет звуковой дорожки"):
        n.make_plan(SimpleNamespace(src=tmp_path, out=out))
    with pytest.raises(ValueError, match="подтверждение"):
        n.render(SimpleNamespace(confirmed=False, out=out))
    assert not out.exists()


def test_reject_changed_audio_or_timeline_in_compact(modules, monkeypatch):
    _, c = modules
    fmt = {"duration": "12", "start_time": "0"}
    audio = {"codec_type": "audio", "duration": "12", "start_time": "0"}
    video = {"codec_type": "video", "width": 800, "height": 600, "duration": "12"}
    def pair(_):
        return fmt, [video, audio]
    monkeypatch.setattr(c, "tracks", pair)
    monkeypatch.setattr(c, "audio_hashes", lambda path: str(path))
    with pytest.raises(ValueError, match="Звуковые дорожки"):
        c.compare_timing("a", "b", 15)
    monkeypatch.setattr(c, "audio_hashes", lambda _: "одинаковые данные")
    c.compare_timing("a", "b", 15)
    monkeypatch.setattr(c, "tracks", lambda path: (fmt, [video, dict(audio, start_time="0.1")])
                        if path == "b" else pair(path))
    with pytest.raises(ValueError, match="начало"):
        c.compare_timing("a", "b", 15)
