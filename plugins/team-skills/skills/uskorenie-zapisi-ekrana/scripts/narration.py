"""Разметка речи, целых пауз и подтверждённых по кадрам этапов скринкаста."""
import argparse
import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import wave

from build import Fail, ffmpeg, parse_timecode, probe_source, require_tools
from compact import decode, encoding, tracks

RATE = 48000
WINDOW = 512
VAD_RATE = 16000
VISUAL = ("keyboard", "wait", "answer")


def source_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def speed(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Скорость должна быть конечной и положительной.")
    return number


def thresholds(text):
    pairs = []
    for item in text.split(",") if text else []:
        duration, multiplier = item.split(":")
        seconds = float(duration)
        if not math.isfinite(seconds) or seconds < 0 or (pairs and seconds * RATE <= pairs[-1][0]):
            raise ValueError("Пороги пауз должны возрастать.")
        pairs.append((round(seconds * RATE), speed(multiplier)))
    return pairs


def voiced_intervals(probabilities, samples):
    """Вернуть защищённые интервалы по образцам 16 кГц, включая края слов."""
    raw = []
    start = low = None
    for i, prob in enumerate(probabilities):
        t = i * WINDOW
        if prob >= .30:
            if start is None:
                start = t
            low = None
        elif prob < .15 and start is not None:
            if low is None:
                low = t
            if t - low >= 2048:
                raw.append([start, low])
                start = low = None
    if start is not None:
        raw.append([start, samples])
    pad = 3200
    for i in range(len(raw) - 1):
        space = min(pad, (raw[i + 1][0] - raw[i][1]) // 2)
        raw[i][1] += space
        raw[i + 1][0] -= space
    if raw:
        raw[0][0] = max(0, raw[0][0] - pad)
        raw[-1][1] = min(samples, raw[-1][1] + pad)
    return raw


def speech(src, total, model_file, track=0):
    try:
        import torch
        if model_file is None:
            from silero_vad import load_silero_vad
            model = load_silero_vad()
        else:
            model = torch.jit.load(str(model_file), map_location="cpu")
    except ImportError as exc:
        raise ValueError("Для распознавания речи нужен локальный Python с silero-vad и torch.") from exc
    torch.set_num_threads(2)
    model.eval()
    model.reset_states()
    size = round(total * VAD_RATE / RATE)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "analysis.wav"
        ffmpeg(["-i", str(src), "-map", f"0:a:{track}", "-ac", "1", "-af",
                f"aresample={VAD_RATE}:async=1:first_pts=0,apad,atrim=end_sample={size}",
                "-c:a", "pcm_s16le", str(wav)], "чтение речи")
        with wave.open(str(wav), "rb") as audio, torch.inference_mode():
            def probs():
                while data := audio.readframes(WINDOW):
                    frame = torch.frombuffer(bytearray(data.ljust(WINDOW * 2, b"\0")), dtype=torch.int16)
                    yield float(model(frame.float() / 32768, VAD_RATE).item())

            return [(a * 3, min(b * 3, total)) for a, b in voiced_intervals(probs(), size)]


def visual_labels(path, total, rates):
    if path is None:
        return []
    rows = json.loads(path.read_text())
    spans = []
    if not isinstance(rows, list):
        raise ValueError("Ожидается список визуальных меток.")
    for row in rows:
        kind = row["kind"]
        evidence = row.get("evidence")
        if kind not in VISUAL or kind not in rates or not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("Для каждого этапа нужны известный тип, согласованная скорость и видимый признак.")
        a, b = (round(parse_timecode(str(row[k]), total / RATE) * RATE) for k in ("start", "end"))
        if not 0 <= a < b <= total:
            raise ValueError("Визуальная метка выходит за пределы исходника.")
        spans.append((a, b, kind))
    spans.sort()
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise ValueError("Уточните пересекающиеся визуальные этапы.")
    return spans


def make_parts(total, voices, rules, base, rates, labels):
    bounds = {0, total}
    for a, b in voices:
        bounds.update([a, b])
    for a, b, _ in labels:
        bounds.update([a, b])
    voice_ends = [b for _, b in voices]
    label_ends = [b for _, b, _ in labels]
    points = sorted(bounds)
    parts = []
    for a, b in zip(points, points[1:]):
        v = bisect.bisect_right(voice_ends, a)
        j = bisect.bisect_right(label_ends, a)
        if v < len(voices) and voices[v][0] <= a:
            kind, factor = "voice", rates["voice"]
        elif j < len(labels) and labels[j][0] <= a:
            kind = labels[j][2]
            factor = rates[kind]
        else:
            # Визуальные границы не должны менять ступень оставшихся частей одной паузы.
            start = voices[v - 1][1] if v else 0
            end = voices[v][0] if v < len(voices) else total
            factor = next((n for threshold, n in reversed(rules) if end - start > threshold), base)
            kind = "pause"
        if parts and (parts[-1]["kind"], parts[-1]["speed"]) == (kind, factor):
            parts[-1]["end"] = b
        else:
            parts.append(dict(start=a, end=b, kind=kind, speed=factor))
    return parts


def map_times(parts, total):
    pts = [(0, 0)]
    ideal = 0.0
    for part in parts:
        a, b = part["start"], part["end"]
        if type(a) is not int or type(b) is not int or a != pts[-1][0] or not a < b <= total:
            raise ValueError("В плане разрыв, наложение или неверная граница.")
        ideal += (b - a) / speed(part["speed"])
        if round(ideal) <= pts[-1][1]:
            raise ValueError("Интервал короче звукового отсчёта на выбранной скорости.")
        pts.append((b, round(ideal)))
    if total <= 0 or pts[-1][0] != total:
        raise ValueError("План должен покрывать весь исходник.")
    return pts


def make_plan(args):
    info = probe_source(args.src)
    if not info["has_audio"]:
        raise ValueError("В указанном файле нет звуковой дорожки. Сверьте исходник с голосом до монтажа.")
    _, streams = tracks(args.src)
    number = sum(s["codec_type"] == "audio" for s in streams)
    if number > 1 and args.audio_track is None:
        raise ValueError("Несколько звуковых дорожек. Выберите дорожку с комментарием для монтажа (--audio-track, с нуля).")
    track = 0 if args.audio_track is None else args.audio_track
    if not 0 <= track < number:
        raise ValueError("Выбранной звуковой дорожки нет.")
    total = round(info["duration"] * RATE)
    rates = {k: speed(getattr(args, k)) for k in ("voice", *VISUAL) if getattr(args, k) is not None}
    rules = thresholds(args.pauses)
    base = speed(args.short_pause)
    if args.no_pause_scale and base != 1:
        raise ValueError("При отключённой шкале прочие участки идут в исходном темпе.")
    labels = visual_labels(args.visual, total, rates)
    voices = speech(args.src, total, args.vad_model, track)
    if not voices:
        raise ValueError("На имеющейся дорожке речь не обнаружена. Проверьте запись и выбор аудиодорожки.")
    parts = make_parts(total, voices, rules, base, rates, labels)
    timing = map_times(parts, total)
    plan = dict(source_sha256=source_hash(args.src), samples=total, sample_rate=RATE, audio_track=track,
                speech_intervals=len(voices), criteria=dict(rates=rates, pause_steps=args.pauses,
                short_pause=base), parts=parts)
    # Полностью готовый план публикуется под новым именем без перезаписи.
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        stage = Path(tmp) / "plan.json"
        stage.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        os.link(stage, args.out)
    print(f"Речевых интервалов: {len(voices)}. Длительность {total / RATE:.3f} → {timing[-1][1] / RATE:.3f} с.")
    names = dict(voice="Речь", keyboard="Ввод с клавиатуры", wait="Ожидание модели",
                 answer="Появление ответа", pause="Остальное без речи")
    for kind in (*rates, "pause"):
        length = sum(p["end"] - p["start"] for p in parts if p["kind"] == kind)
        print(f"{names[kind]}: {length / RATE:.3f} с исходника")


def pts_expression(points):
    def section(lo, hi):
        a, t = points[lo]
        b, u = points[hi]
        if hi == lo + 1:
            return f"{t}+(PTS-{a})*{u-t}/{b-a}"
        mid = (lo + hi) // 2
        return f"if(lt(PTS,{points[mid][0]}),{section(lo,mid)},{section(mid,hi)})"
    return section(0, len(points) - 1)


def render(args):
    if not args.confirmed:
        raise ValueError("Сначала покажите пользователю скорости и получите подтверждение.")
    if args.out.exists() or args.out.suffix.lower() != ".mp4":
        raise ValueError("Укажите новый выходной файл MP4.")
    info = probe_source(args.src)
    plan = json.loads(args.plan.read_text())
    total = round(info["duration"] * RATE)
    if (plan["source_sha256"] != source_hash(args.src) or plan["samples"] != total or plan["sample_rate"] != RATE):
        raise ValueError("План построен для другого исходника.")
    if not 1 <= args.fps <= 120 or not 0 <= args.crf <= 51:
        raise ValueError("Проверьте частоту кадров и качество кодирования.")
    require_tools(True, False)
    points = map_times(plan["parts"], total)
    out_samples = points[-1][1]
    frames = max(1, round(out_samples * args.fps / RATE))
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        tmp = Path(tmp)
        wav, edited, stage = tmp / "input.wav", tmp / "edited.wav", tmp / "edited.mp4"
        ffmpeg(["-i", str(args.src), "-map", f"0:a:{plan['audio_track']}", "-af",
                f"aresample={RATE}:async=1:first_pts=0,apad,atrim=end_sample={total}",
                "-c:a", "pcm_s16le", str(wav)], "подготовка звука")
        command = ["rubberband-r3", "--quiet", "--formant", "--time", str(out_samples / total)]
        if len(points) > 2:
            anchors = tmp / "anchors.txt"
            anchors.write_text("".join(f"{a} {b}\n" for a, b in points[1:-1]))
            command.extend(["--timemap", str(anchors)])
        result = subprocess.run([*command, str(wav), str(edited)], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True)
        if result.returncode or "NaN" in result.stderr or "Inf" in result.stderr:
            raise ValueError("Не удалось сохранить согласованную шкалу времени звука. " + result.stderr[-350:])
        with wave.open(str(edited), "rb") as audio:
            if abs(audio.getnframes() - out_samples) > 1:
                raise ValueError("Длина обработанного звука расходится с планом.")
        filters = tmp / "video.filter"
        filters.write_text(f"settb=1/{RATE},setpts='{pts_expression(points)}',"
                           f"fps={args.fps}:start_time=0:round=near,tpad=stop=-1:stop_mode=clone,trim=end_frame={frames}")
        ffmpeg(["-xerror", "-threads", "3", "-i", str(args.src), "-i", str(edited),
                "-map", "0:v:0", "-map", "1:a:0", "-filter_threads", "2", "-/filter:v", str(filters),
                *encoding(args.fps, args.crf, args.preset), "-c:a", "aac", "-b:a", "96k", str(stage)], "монтаж")
        _, streams = tracks(stage)
        for kind in ("audio", "video"):
            stream = next(s for s in streams if s["codec_type"] == kind)
            if abs(float(stream["duration"]) - out_samples / RATE) > .5 / args.fps + .001:
                raise ValueError("Картинка или звук разошлись с согласованным планом.")
        decode(stage)
        os.link(stage, args.out)
    print(f"Длительность {out_samples / RATE:.3f} с. Размер {args.out.stat().st_size / 1e6:.2f} МБ.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    plan = modes.add_parser("plan")
    plan.add_argument("--voice", type=float, required=True)
    pauses = plan.add_mutually_exclusive_group(required=True)
    pauses.add_argument("--pauses", help="Возрастающие пороги в секундах, например 2:2,6:3.")
    pauses.add_argument("--no-pause-scale", action="store_true", help="Прочие паузы оставить на 1×.")
    plan.add_argument("--short-pause", type=float, default=1)
    plan.add_argument("--vad-model", type=Path, help="Проверенная локальная модель Silero в формате TorchScript.")
    plan.add_argument("--audio-track", type=int, help="Номер выбранной дорожки комментария, начиная с нуля.")
    plan.add_argument("--visual", type=Path)
    for key in VISUAL:
        plan.add_argument("--" + key, type=float)
    export = modes.add_parser("render")
    export.add_argument("--plan", type=Path, required=True)
    export.add_argument("--confirmed", action="store_true")
    export.add_argument("--fps", type=int, default=30)
    export.add_argument("--crf", type=int, default=24)
    export.add_argument("--preset", choices=["fast", "medium", "slow"], default="medium")
    for mode in (plan, export):
        mode.add_argument("--src", type=Path, required=True)
        mode.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "plan":
            make_plan(args)
        else:
            render(args)
    except (Fail, ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
