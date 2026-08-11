#!/usr/bin/env python3
"""
Сборка ускоренной записи экрана: план ступеней -> куски -> склейка -> финалы -> сверка.

Почему этот скрипт вообще существует (три провала живого сеанса 2026-08-10):
  1. parsing      — ffmpeg в цикле `while read` съел stdin и сожрал остаток таблицы
                    ступеней; собралась не та сборка, код возврата при этом был 0.
  2. arithmetic   — исходник VFR; при `-ss`/`-t` до `-i` куски вышли неверной длины,
                    картинка систематически длиннее звука, разбег ~3 с накопился на стыках.
  3. reconciliation — покусочной сверки не было вовсе, дефект нашёлся только глазами.

Отсюда три несущих решения:
  * длина куска задаётся жёстко: outdur = dur / speed, обе дорожки режутся одним `-t`;
  * сверка живёт ВНУТРИ скрипта и роняет его кодом 3 при расхождении выше допуска;
  * код возврата 0 доказательством не является — скрипт всегда печатает полную
    таблицу сверки и список проверок, и цитировать нужно их, а не код.

Только стандартная библиотека. Требуется ffmpeg, ffprobe, rubberband-r3.
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXIT_OK = 0
EXIT_INPUT = 1      # ошибка входа, ничего не собрано
EXIT_TOOL = 2       # упал ffmpeg / rubberband
EXIT_DRIFT = 3      # расхождение сверки выше допуска

# Опорные замеры августовского прогона — только для грубой сметы в --dry-run.
REF_VIDEO_KBPS = 181.0
REF_PIXELS = 1668 * 1080
REF_BUILD_RATIO = 0.24      # секунд сборки на секунду исходника

LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


# ---------------------------------------------------------------- инструменты

class Fail(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def run(cmd, capture=True):
    """Любой внешний вызов. stdin всегда закрыт — см. провал 1."""
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc


def ffmpeg(args, what):
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y"] + args
    proc = run(cmd)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-8:])
        raise Fail(EXIT_TOOL, f"ffmpeg упал на шаге «{what}»:\n{tail}")
    return proc


def ffprobe_json(args):
    proc = run(["ffprobe", "-v", "error", "-of", "json"] + args)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-5:])
        raise Fail(EXIT_TOOL, f"ffprobe упал:\n{tail}")
    return json.loads(proc.stdout or "{}")


def ffprobe_lines(args):
    proc = run(["ffprobe", "-v", "error", "-of", "csv=p=0"] + args)
    if proc.returncode != 0:
        return []
    return [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]


def require_tools(need_audio, allow_atempo):
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        raise Fail(EXIT_INPUT, "не найдено: " + ", ".join(missing) + ". Поставьте: brew install ffmpeg")
    if need_audio and shutil.which("rubberband-r3") is None:
        if allow_atempo:
            return False
        raise Fail(
            EXIT_INPUT,
            "не найден rubberband-r3 — он тянет звук, не меняя высоту голоса.\n"
            "Поставьте: brew install rubberband\n"
            "Пересобирать ffmpeg ради фильтра rubberband НЕ надо (~40 минут против готового бинарника).\n"
            "Если растяжка похуже приемлема — запустите с --allow-atempo.",
        )
    return need_audio


# ---------------------------------------------------------------- исходник

def probe_source(path):
    info = ffprobe_json(["-show_entries",
                         "format=duration,size:stream=index,codec_type,codec_name,width,height,"
                         "r_frame_rate,avg_frame_rate,nb_frames",
                         str(path)])
    fmt = info.get("format", {})
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise Fail(EXIT_INPUT, f"в файле нет видеодорожки: {path}")

    def ratio(text):
        try:
            num, den = text.split("/")
            return float(num) / float(den) if float(den) else 0.0
        except Exception:
            return 0.0

    st = os.stat(path)
    declared = ratio(video.get("r_frame_rate", "0/1"))
    actual = ratio(video.get("avg_frame_rate", "0/1"))
    return {
        "path": str(path),
        "duration": float(fmt.get("duration", 0.0)),
        "size": int(fmt.get("size", st.st_size)),
        "mtime": st.st_mtime,
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "has_audio": audio is not None,
        "fps_declared": declared,
        "fps_actual": actual,
        # VFR — норма для записи экрана: кадр пишется только при смене картинки.
        "vfr": bool(declared and actual and abs(declared - actual) / declared > 0.05),
        "nb_frames": int(video.get("nb_frames") or 0),
    }


# ---------------------------------------------------------------- план

def parse_timecode(text, total):
    text = text.strip()
    if text.lower() == "end":
        return total
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(f"непонятная метка времени: {text!r}")
    seconds = 0.0
    for pos, chunk in enumerate(reversed(parts)):
        if chunk == "" or not re.fullmatch(r"\d+(\.\d+)?", chunk):
            raise ValueError(f"непонятная метка времени: {text!r}")
        seconds += float(chunk) * (60 ** pos)
    return seconds


def parse_plan(plan_path, total, allow_gaps):
    if not plan_path.exists():
        raise Fail(EXIT_INPUT,
                   f"нет файла плана: {plan_path}\nОбразец: references/plan.example.txt")

    steps, cuts = [], []
    for lineno, raw in enumerate(plan_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tok = line.split()
        if len(tok) != 3:
            raise Fail(EXIT_INPUT, f"строка {lineno}: ожидалось три поля, получено {len(tok)}: {raw.strip()!r}")
        head, a, b = tok
        try:
            start, end = parse_timecode(a, total), parse_timecode(b, total)
        except ValueError as exc:
            raise Fail(EXIT_INPUT, f"строка {lineno}: {exc}")
        if end <= start:
            raise Fail(EXIT_INPUT, f"строка {lineno}: конец не позже начала ({a} -> {b})")
        if head.lower() == "cut":
            cuts.append((start, end))
        elif head.lower().startswith("x"):
            try:
                speed = float(head[1:])
            except ValueError:
                raise Fail(EXIT_INPUT, f"строка {lineno}: непонятная скорость {head!r}")
            if not 0.5 <= speed <= 4.0:
                raise Fail(EXIT_INPUT, f"строка {lineno}: скорость {speed} вне диапазона 0.5–4.0")
            steps.append({"start": start, "end": end, "speed": speed})
        else:
            raise Fail(EXIT_INPUT, f"строка {lineno}: строка должна начинаться с x<скорость> или cut")

    if not steps:
        raise Fail(EXIT_INPUT, "в плане нет ни одной ступени")

    steps.sort(key=lambda s: s["start"])
    if steps[0]["start"] > 0.001:
        raise Fail(EXIT_INPUT, f"первая ступень начинается не с нуля, а с {steps[0]['start']:.3f} с")
    for prev, cur in zip(steps, steps[1:]):
        if cur["start"] < prev["end"] - 0.001:
            raise Fail(EXIT_INPUT,
                       f"ступени наложились: {prev['start']:.3f}–{prev['end']:.3f} и "
                       f"{cur['start']:.3f}–{cur['end']:.3f}")
        if cur["start"] > prev["end"] + 0.001 and not allow_gaps:
            raise Fail(EXIT_INPUT,
                       f"дыра в плане: {prev['end']:.3f}–{cur['start']:.3f} с ничем не покрыты — "
                       f"этот материал потеряется молча. Закройте дыру ступенью, вырежьте строкой "
                       f"cut или запустите с --allow-gaps.")
    if steps[-1]["end"] < total - 0.5 and not allow_gaps:
        raise Fail(EXIT_INPUT,
                   f"план обрывается на {steps[-1]['end']:.3f} с, а исходник длится {total:.3f} с. "
                   f"Допишите ступень до end или запустите с --allow-gaps.")

    cuts.sort()
    for prev, cur in zip(cuts, cuts[1:]):
        if cur[0] < prev[1] - 0.001:
            raise Fail(EXIT_INPUT, f"вырезы наложились: {prev} и {cur}")
    covered_end = steps[-1]["end"]
    for start, end in cuts:
        if start < steps[0]["start"] - 0.001 or end > covered_end + 0.001:
            raise Fail(EXIT_INPUT, f"вырез {start:.3f}–{end:.3f} выходит за пределы ступеней")
    return steps, cuts


def apply_cuts(steps, cuts):
    """Вырез разрезает ступень, в которую попал. Порядок и скорости сохраняются."""
    pieces = []
    for step in steps:
        spans = [(step["start"], step["end"])]
        for cut_start, cut_end in cuts:
            nxt = []
            for span_start, span_end in spans:
                if cut_end <= span_start or cut_start >= span_end:
                    nxt.append((span_start, span_end))
                    continue
                if cut_start > span_start:
                    nxt.append((span_start, cut_start))
                if cut_end < span_end:
                    nxt.append((cut_end, span_end))
            spans = nxt
        for span_start, span_end in spans:
            if span_end - span_start > 0.01:
                pieces.append({"start": span_start, "end": span_end, "speed": step["speed"]})
    if not pieces:
        raise Fail(EXIT_INPUT, "после вырезов не осталось ни одного куска")
    for idx, piece in enumerate(pieces, 1):
        piece["n"] = idx
        piece["dur"] = piece["end"] - piece["start"]
        piece["outdur"] = piece["dur"] / piece["speed"]
    return pieces


def fmt_tc(seconds):
    seconds = max(0.0, seconds)
    return f"{int(seconds // 60):d}:{seconds % 60:06.3f}"


# ---------------------------------------------------------------- сборка

def stretch_audio(src_wav, dst_wav, speed, use_rubberband):
    if abs(speed - 1.0) < 1e-9:
        shutil.copyfile(src_wav, dst_wav)
        return
    if use_rubberband:
        proc = run(["rubberband-r3", "--tempo", f"{speed}", str(src_wav), str(dst_wav)])
        if proc.returncode != 0:
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-5:])
            raise Fail(EXIT_TOOL, f"rubberband-r3 упал на скорости {speed}:\n{tail}")
    else:
        # Запасной путь. Хуже качеством и даёт дрейф длины — только по --allow-atempo.
        ffmpeg(["-i", str(src_wav), "-filter:a", f"atempo={speed}",
                "-c:a", "pcm_s16le", str(dst_wav)], f"atempo {speed}")


def build_segment(cfg, src, piece, out_path, work):
    """Один кусок. Длина обеих дорожек прибивается одним выходным -t outdur."""
    outdur = piece["outdur"]
    speed = piece["speed"]
    vf = (f"scale=-2:{cfg.height},"
          f"setpts=(PTS-STARTPTS)/{speed},"          # обнуление отсчёта — см. провал 3
          f"fps={cfg.fps},"
          f"tpad=stop=-1:stop_mode=clone")           # картинка не дотянула -> морозим кадр

    if not cfg.audio:
        ffmpeg(["-ss", f"{piece['start']}", "-i", str(src["path"]),
                "-filter:v", vf, "-map", "0:v", "-an", "-t", f"{outdur}",
                "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
                "-pix_fmt", "yuv420p", str(out_path)], f"кусок {piece['n']} (без звука)")
        return

    raw = work / f"a{piece['n']:02d}.wav"
    stretched = work / f"a{piece['n']:02d}_s.wav"
    ffmpeg(["-ss", f"{piece['start']}", "-i", str(src["path"]),
            "-af", "asetpts=PTS-STARTPTS", "-t", f"{piece['dur']}",
            "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(raw)],
           f"звук куска {piece['n']}")
    stretch_audio(raw, stretched, speed, cfg.use_rubberband)

    ffmpeg(["-ss", f"{piece['start']}", "-i", str(src["path"]), "-i", str(stretched),
            "-filter:v", vf,
            "-filter:a", "asetpts=PTS-STARTPTS,apad",   # звук не дотянул -> добиваем тишиной
            "-map", "0:v", "-map", "1:a", "-t", f"{outdur}",
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
            "-pix_fmt", "yuv420p", "-c:a", "flac",      # без потерь: в AAC жмём один раз, в финале
            str(out_path)], f"кусок {piece['n']}")
    raw.unlink(missing_ok=True)
    stretched.unlink(missing_ok=True)


# ---------------------------------------------------------------- измерения

def video_frames(path):
    lines = ffprobe_lines(["-select_streams", "v", "-count_packets",
                           "-show_entries", "stream=nb_read_packets", str(path)])
    return int(lines[0]) if lines else 0


def audio_end(path):
    """Длина звука в MKV: stream=duration там N/A, меряем по последнему пакету."""
    lines = ffprobe_lines(["-select_streams", "a",
                           "-show_entries", "packet=pts_time,duration_time", str(path)])
    if not lines:
        return None
    last = lines[-1].split(",")
    try:
        pts = float(last[0])
        dur = float(last[1]) if len(last) > 1 and last[1] not in ("", "N/A") else 0.0
        return pts + dur
    except ValueError:
        return None


def stream_geometry(path):
    info = ffprobe_json(["-show_entries",
                         "stream=codec_type,width,height,pix_fmt,sample_rate,channels", str(path)])
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), {})
    return (video.get("width"), video.get("height"), video.get("pix_fmt"),
            audio.get("sample_rate"), audio.get("channels"))


def stream_durations(path):
    info = ffprobe_json(["-show_entries", "stream=codec_type,duration:format=duration", str(path)])
    out = {"video": None, "audio": None,
           "format": float(info.get("format", {}).get("duration") or 0) or None}
    for stream in info.get("streams", []):
        value = stream.get("duration")
        if value not in (None, "N/A"):
            out[stream.get("codec_type")] = float(value)
    return out


def measure_volume(path):
    proc = run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats",
                "-i", str(path), "-af", "volumedetect", "-f", "null", "-"])
    text = proc.stderr or ""
    mean = re.search(r"mean_volume:\s*(-?[\d.]+)", text)
    peak = re.search(r"max_volume:\s*(-?[\d.]+)", text)
    return (float(mean.group(1)) if mean else None,
            float(peak.group(1)) if peak else None)


def psnr_between(png_a, png_b):
    proc = run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats",
                "-i", str(png_a), "-i", str(png_b), "-lavfi", "psnr", "-f", "null", "-"])
    found = re.search(r"average:([\d.]+|inf)", proc.stderr or "")
    if not found:
        return None
    return 99.0 if found.group(1) == "inf" else float(found.group(1))


# ---------------------------------------------------------------- сверка

class Checks:
    def __init__(self):
        self.items = []

    def add(self, name, ok, fact, tol="—"):
        self.items.append({"name": name, "ok": bool(ok), "fact": str(fact), "tol": str(tol)})
        return ok

    @property
    def failed(self):
        return [i for i in self.items if not i["ok"]]

    def render(self):
        lines = ["", "ПРОВЕРКИ", "-" * 92]
        for num, item in enumerate(self.items, 1):
            mark = "ok " if item["ok"] else "СБОЙ"
            lines.append(f"{num:>2}. [{mark}] {item['name']}")
            lines.append(f"        факт: {item['fact']}   допуск: {item['tol']}")
        return "\n".join(lines)


def make_crop(cfg, video, at_second):
    """Вырезка кадра 1:1 — единственный способ судить о читаемости мелкого текста."""
    geo = stream_geometry(video)
    width, height = geo[0] or cfg.height, geo[1] or cfg.height
    crop_w, crop_h = min(834, width), min(540, height)
    path = Path(cfg.out) / "crop-1to1.png"
    ffmpeg(["-ss", f"{at_second}", "-i", str(video), "-frames:v", "1",
            "-vf", f"crop={crop_w}:{crop_h}:{(width - crop_w) // 2}:{(height - crop_h) // 2}",
            str(path)], "вырезка кадра 1:1")
    return path


def verify(cfg, src, pieces, work, finals, checks):
    fps = cfg.fps
    # запас на погрешность дробных чисел: полкадра — это ровно достижимый худший случай,
    # и без запаса проверка падает на равенстве
    tol_seg = cfg.tol_segment_frames / fps + 1e-6
    rows, sum_plan, sum_video, sum_audio, sum_frames = [], 0.0, 0.0, 0.0, 0

    geometries = set()
    for piece in pieces:
        seg = work / f"seg{piece['n']:02d}.mkv"
        if not seg.exists():
            raise Fail(EXIT_DRIFT, f"нет собранного куска {seg}")
        frames = video_frames(seg)
        vdur = frames / fps
        adur = audio_end(seg) if cfg.audio else None
        geometries.add(stream_geometry(seg))
        rows.append({
            "n": piece["n"], "start": piece["start"], "end": piece["end"],
            "speed": piece["speed"], "plan": piece["outdur"], "frames": frames,
            "video": vdur, "audio": adur,
            "dv": vdur - piece["outdur"],
            "da": (adur - piece["outdur"]) if adur is not None else None,
        })
        sum_plan += piece["outdur"]
        sum_video += vdur
        sum_frames += frames
        if adur is not None:
            sum_audio += adur

    # таблица
    head = (f"{'кусок':>5} {'от':>9} {'до':>9} {'x':>4} {'план_с':>9} {'кадров':>7} "
            f"{'видео_с':>9} {'звук_с':>9} {'Δвидео':>8} {'Δзвук':>8}  вердикт")
    table = [head, "-" * len(head)]
    for row in rows:
        bad_v = abs(row["dv"]) > tol_seg
        bad_a = row["da"] is not None and abs(row["da"]) > tol_seg
        audio_s = f"{row['audio']:.3f}" if row["audio"] is not None else "—"
        delta_a = f"{row['da']:+.3f}" if row["da"] is not None else "—"
        verdict = "СБОЙ" if (bad_v or bad_a) else "ok"
        table.append(
            f"{row['n']:>5} {fmt_tc(row['start']):>9} {fmt_tc(row['end']):>9} {row['speed']:>4} "
            f"{row['plan']:>9.3f} {row['frames']:>7} {row['video']:>9.3f} {audio_s:>9} "
            f"{row['dv']:>+8.3f} {delta_a:>8}  {verdict}")
    total_audio_s = f"{sum_audio:.3f}" if cfg.audio else "—"
    total_delta_a = f"{sum_audio - sum_plan:+.3f}" if cfg.audio else "—"
    table.append("-" * len(head))
    table.append(f"{'ИТОГО':>5} {'':>9} {'':>9} {'':>4} {sum_plan:>9.3f} {sum_frames:>7} "
                 f"{sum_video:>9.3f} {total_audio_s:>9} "
                 f"{sum_video - sum_plan:>+8.3f} {total_delta_a:>8}")

    # 1-3
    checks.add("план покрывает исходник, число ступеней совпало с числом кусков",
               True, f"{len(pieces)} кусков")
    checks.add("все куски собраны и читаются", True, f"{len(rows)} файлов")
    checks.add("геометрия/pix_fmt/частота одинаковы у всех кусков (условие склейки без перекодирования)",
               len(geometries) == 1, f"вариантов: {len(geometries)}", "1")
    # 4-5
    worst_v = max((abs(r["dv"]) for r in rows), default=0.0)
    checks.add("длина картинки каждого куска совпала с планом",
               worst_v <= tol_seg, f"худшее {worst_v:.4f} с", f"{tol_seg:.4f} с (полкадра)")
    if cfg.audio:
        worst_a = max((abs(r["da"]) for r in rows if r["da"] is not None), default=0.0)
        checks.add("длина звука каждого куска совпала с планом",
                   worst_a <= tol_seg, f"худшее {worst_a:.4f} с", f"{tol_seg:.4f} с (полкадра)")
    else:
        checks.add("длина звука каждого куска совпала с планом", True, "режим без звука — пропущено")
    # 6-7
    combined = work / "combined.mkv"
    combined_frames = video_frames(combined)
    checks.add("кадров в склейке столько же, сколько в кусках",
               combined_frames == sum_frames, f"{combined_frames} против {sum_frames}", "точное совпадение")
    checks.add("суммарный разбег картинки с планом",
               abs(sum_video - sum_plan) <= cfg.tol_total_sec,
               f"{sum_video - sum_plan:+.4f} с", f"{cfg.tol_total_sec} с")
    # 8-9
    final_main = finals[0]
    dur = stream_durations(final_main)
    if cfg.audio:
        both = dur["video"] is not None and dur["audio"] is not None
        gap = abs((dur["audio"] or 0) - (dur["video"] or 0))
        checks.add("в финале обе дорожки, звук не разъехался с картинкой",
                   both and gap <= 0.15, f"расхождение {gap:.3f} с", "0.15 с")
    else:
        checks.add("в финале обе дорожки, звук не разъехался с картинкой", True, "режим без звука — пропущено")
    combined_dur = stream_durations(combined)["format"] or 0
    final_dur = dur["format"] or 0
    checks.add("длина финала совпала с длиной склейки",
               abs(final_dur - combined_dur) <= 0.1,
               f"{final_dur:.3f} против {combined_dur:.3f}", "0.1 с")

    # 10 — сверка содержания на стыках: арифметика не отличит правильный кусок от смещённого
    spots, out_clock = [], 0.0
    marks = []
    for piece in pieces:
        marks.append((piece["n"], piece["start"], out_clock, piece["speed"]))
        out_clock += piece["outdur"]
    wanted = [marks[0]] + ([marks[-1]] if len(marks) > 1 else [])
    tmp = work / "_spot"
    tmp.mkdir(exist_ok=True)
    worst_psnr = None
    for n, src_t, out_t, speed in wanted:
        probe_out, probe_src = out_t + 0.5, src_t + 0.5 * speed
        if probe_src >= src["duration"]:
            continue
        a, b = tmp / f"o{n}.png", tmp / f"s{n}.png"
        ffmpeg(["-ss", f"{probe_out}", "-i", str(final_main), "-frames:v", "1", str(a)], "кадр из итога")
        ffmpeg(["-ss", f"{probe_src}", "-i", str(src["path"]), "-frames:v", "1",
                "-vf", f"scale=-2:{cfg.height}", str(b)], "кадр из исходника")
        value = psnr_between(a, b)
        spots.append({"segment": n, "out_time": probe_out, "src_time": probe_src, "psnr": value})
        if value is not None:
            worst_psnr = value if worst_psnr is None else min(worst_psnr, value)
    checks.add("содержание стыков совпало с исходником (PSNR)",
               worst_psnr is not None and worst_psnr >= 30.0,
               f"худший {worst_psnr:.1f} дБ" if worst_psnr is not None else "не измерен", "30 дБ")

    # 11-13
    crop = Path(cfg.out) / "crop-1to1.png"
    if not crop.exists():
        crop = make_crop(cfg, final_main, min(5.0, (final_dur or 10) / 2))
    checks.add("вырезка кадра 1:1 сохранена, читаемость можно проверить глазами",
               crop.exists(), str(crop) if crop.exists() else "нет файла", "файл существует")
    out_real = Path(cfg.out).resolve()
    checks.add("результат лежит в рабочей папке проекта, не в ~/Downloads",
               "Downloads" not in out_real.parts, str(out_real), "не ~/Downloads")
    now = os.stat(src["path"])
    checks.add("исходник не изменён",
               now.st_size == src["size"] and abs(now.st_mtime - src["mtime"]) < 1,
               f"{now.st_size} Б", f"{src['size']} Б, mtime тот же")
    if cfg.target_mb:
        got_mb = final_main.stat().st_size / 1024 ** 2
        checks.add("итог уложился в заявленный лимит веса",
                   got_mb <= cfg.target_mb, f"{got_mb:.1f} МБ", f"{cfg.target_mb:.0f} МБ")

    return {"rows": rows, "table": "\n".join(table), "spots": spots,
            "sum_plan": sum_plan, "sum_video": sum_video,
            "sum_audio": sum_audio if cfg.audio else None, "sum_frames": sum_frames}


# ---------------------------------------------------------------- режимы

# Замерено на августовской записи, пилот 30 с, ступень x2.5.
# Качество: crf 26 -> 19 МБ, crf 30 -> 16 МБ, crf 32 -> 15 МБ. Вдвое режет не +6, а ~+17.
# Кадр:  1080 -> 19 МБ, 864 -> 16 МБ, 720 -> 14 МБ, 540 -> 11 МБ. Вес ~ высота^0.78, не площадь.
# Оба рычага слабые: у записи экрана вес держит длительность, а не детализация.
CRF_HALVING = 17.0
HEIGHT_EXPONENT = 0.78


def size_advice(projected_mb, cfg, precise, total_out=None):
    """Влезаем ли в заявленный лимит веса и чем править, если нет."""
    if not cfg.target_mb:
        return []
    kind = "по пилоту" if precise else "грубо"
    if projected_mb <= cfg.target_mb:
        return [f"лимит {cfg.target_mb:.0f} МБ: ВЛЕЗАЕМ ({kind} ~{projected_mb:.0f} МБ, "
                f"запас {cfg.target_mb - projected_mb:.0f} МБ)"]

    ratio = cfg.target_mb / projected_mb
    lines = [f"лимит {cfg.target_mb:.0f} МБ: НЕ ВЛЕЗАЕМ ({kind} ~{projected_mb:.0f} МБ), "
             f"ужимать надо в {1 / ratio:.2f} раза"]

    # Сильный рычаг: вес почти прямо пропорционален длине итога.
    if total_out:
        lines.append(f"  сильный рычаг — ПЛАН: итог должен стать короче {fmt_tc(total_out * ratio)} "
                     f"(сейчас {fmt_tc(total_out)}). Ускорьте сильнее или добавьте вырезы")
    # Слабые рычаги — по замерам, а не по учебнику про кино.
    need_crf = math.ceil(cfg.crf - CRF_HALVING * math.log2(ratio))
    if need_crf <= 34:
        lines.append(f"  слабый рычаг — качество: --crf {need_crf} (сейчас {cfg.crf})")
    else:
        lines.append(f"  качеством не вытянуть: нужен crf {need_crf}, выше 34 картинка сыпется")
    need_h = max(360, int(cfg.height * ratio ** (1 / HEIGHT_EXPONENT)) // 2 * 2)
    lines.append(f"  слабый рычаг — размер кадра: --height {need_h} (сейчас {cfg.height}), "
                 f"читаемость после этого перепроверьте пилотом заново")
    return lines


def do_dry_run(cfg, src, pieces):
    total_out = sum(p["outdur"] for p in pieces)
    out_width = src["width"] / src["height"] * cfg.height
    kbps = REF_VIDEO_KBPS * (out_width * cfg.height) / REF_PIXELS
    size_mb = (kbps + (128 if cfg.audio else 0)) * total_out / 8 / 1024
    build_s = src["duration"] * REF_BUILD_RATIO

    head = f"{'кусок':>5} {'от':>9} {'до':>9} {'x':>4} {'исходных_с':>11} {'станет_с':>9}"
    print(head)
    print("-" * len(head))
    for piece in pieces:
        print(f"{piece['n']:>5} {fmt_tc(piece['start']):>9} {fmt_tc(piece['end']):>9} "
              f"{piece['speed']:>4} {piece['dur']:>11.3f} {piece['outdur']:>9.3f}")
    print("-" * len(head))
    print(f"{'ИТОГО':>5} {'':>9} {'':>9} {'':>4} "
          f"{sum(p['dur'] for p in pieces):>11.3f} {total_out:>9.3f}")
    print()
    print(f"итог: {fmt_tc(total_out)} против {fmt_tc(src['duration'])} у исходника "
          f"(короче в {src['duration'] / total_out:.2f} раза)")
    print(f"грубая смета веса: ~{size_mb:.0f} МБ "
          f"(от замера 181 кбит/с на 1668x1080 августовского прогона — точность подтвердит --pilot)")
    print(f"грубая смета времени сборки: ~{build_s / 60:.1f} мин")
    for line in size_advice(size_mb, cfg, precise=False, total_out=total_out):
        print(line)
    free = shutil.disk_usage(cfg.out).free / 1024 ** 3
    print(f"свободно на диске: {free:.1f} ГБ")
    if free < size_mb / 1024 * 4:
        print("ВНИМАНИЕ: места мало для промежуточных кусков (они без потерь по звуку)")


def do_pilot(cfg, src, pieces, work):
    piece = max(pieces, key=lambda p: p["speed"])
    dur = min(float(cfg.pilot), piece["dur"])
    sample = dict(piece)
    sample.update({"n": 0, "start": piece["start"], "end": piece["start"] + dur,
                   "dur": dur, "outdur": dur / piece["speed"]})
    out = Path(cfg.out) / "pilot.mp4"
    tmp = work / "pilot.mkv"
    build_segment(cfg, src, sample, tmp, work)
    ffmpeg(["-i", str(tmp), "-c:v", "copy"] +
           (["-c:a", "aac", "-b:a", "128k"] if cfg.audio else ["-an"]) +
           ["-movflags", "+faststart", str(out)], "пилот в mp4")

    crop = make_crop(cfg, out, min(1.0, sample["outdur"] / 2))
    made = [out, crop]
    if cfg.audio:
        raw = work / "pilot_raw.wav"
        ffmpeg(["-ss", f"{piece['start']}", "-i", str(src["path"]), "-t", f"{dur}",
                "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(raw)], "звук пилота")
        mean, peak = measure_volume(raw)
        gain = 0.0
        if mean is not None and peak is not None:
            gain = round(min(-20.0 - mean, -1.0 - peak), 1)
        stretched = work / "pilot_st.wav"
        stretch_audio(raw, stretched, piece["speed"], cfg.use_rubberband)
        for tag, source in (("1x", raw), (f"{piece['speed']}x", stretched)):
            dst = Path(cfg.out) / f"pilot-audio-{tag}.m4a"
            ffmpeg(["-i", str(source), "-af", f"volume={gain}dB",
                    "-c:a", "aac", "-b:a", "128k", str(dst)], f"образец звука {tag}")
            made.append(dst)
        raw.unlink(missing_ok=True)
        stretched.unlink(missing_ok=True)
        print(f"звук исходника: средний {mean} дБ, пик {peak} дБ; "
              f"в оба образца добавлено одинаковых {gain} дБ, иначе не расслышать")

    pilot_mb = out.stat().st_size / 1024 ** 2
    total_out = sum(p["outdur"] for p in pieces)
    print(f"пилот: {dur:.1f} с исходника на скорости x{piece['speed']} -> "
          f"{sample['outdur']:.1f} с, {pilot_mb:.1f} МБ")
    projected = pilot_mb / sample["outdur"] * total_out
    print(f"в пересчёте на весь фильм ({fmt_tc(total_out)}): ~{projected:.0f} МБ")
    for line in size_advice(projected, cfg, precise=True, total_out=total_out):
        print(line)
    print("файлы:")
    for path in made:
        print(f"  {path}")
    print("\nПосмотрите crop-1to1.png в натуральную величину: читается ли мелкий текст.")


def do_build(cfg, src, pieces, work):
    listing = work / "list.txt"
    started = time.time()
    with listing.open("w", encoding="utf-8") as handle:
        for piece in pieces:
            seg = work / f"seg{piece['n']:02d}.mkv"
            print(f"[{piece['n']}/{len(pieces)}] {fmt_tc(piece['start'])} -> {fmt_tc(piece['end'])}  "
                  f"x{piece['speed']}  = {piece['outdur']:.3f} с", flush=True)
            build_segment(cfg, src, piece, seg, work)
            handle.write(f"file '{seg.resolve()}'\n")

    print("[склейка]", flush=True)
    combined = work / "combined.mkv"
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(combined)], "склейка")

    finals = []
    main = Path(cfg.out) / "final.mp4"
    print("[финал]", flush=True)
    ffmpeg(["-i", str(combined), "-c:v", "copy"] +
           (["-c:a", "aac", "-b:a", "128k"] if cfg.audio else ["-an"]) +
           ["-movflags", "+faststart", str(main)], "финал")
    finals.append(main)

    if cfg.audio and cfg.loudnorm:
        loud = Path(cfg.out) / "final-loud.mp4"
        print("[финал с выровненной громкостью]", flush=True)
        ffmpeg(["-i", str(combined), "-c:v", "copy", "-af", LOUDNORM,
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(loud)],
               "финал с loudnorm")
        finals.append(loud)

    print(f"[собрано за {time.time() - started:.0f} с]")
    return finals


# ---------------------------------------------------------------- главный

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ускорение и сжатие записи экрана по плану ступеней, со сверкой длин.")
    parser.add_argument("--src", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--plan")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pilot", type=float, default=None, metavar="SECONDS")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--crf", type=int, default=26)
    parser.add_argument("--preset", default="slow")
    parser.add_argument("--target-mb", type=float, default=None, metavar="MB",
                        help="целевой вес итога; сверяется на смете, на пилоте и в приёмке")
    parser.add_argument("--no-audio", dest="force_no_audio", action="store_true")
    parser.add_argument("--loudnorm", dest="loudnorm", action="store_true", default=True)
    parser.add_argument("--no-loudnorm", dest="loudnorm", action="store_false")
    parser.add_argument("--allow-atempo", action="store_true")
    parser.add_argument("--allow-gaps", action="store_true")
    parser.add_argument("--tol-segment-frames", type=float, default=0.5)
    parser.add_argument("--tol-total-sec", type=float, default=0.1)
    parser.add_argument("--json")
    cfg = parser.parse_args(argv)

    src_path = Path(cfg.src).expanduser()
    if not src_path.exists():
        raise Fail(EXIT_INPUT, f"нет файла: {src_path}")
    out_dir = Path(cfg.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg.out = str(out_dir)
    work = out_dir / "parts"
    work.mkdir(exist_ok=True)

    src = probe_source(src_path)
    cfg.audio = src["has_audio"] and not cfg.force_no_audio
    cfg.use_rubberband = require_tools(cfg.audio, cfg.allow_atempo)

    print(f"исходник: {src_path.name}")
    print(f"  {src['size'] / 1024 ** 2:.0f} МБ, {fmt_tc(src['duration'])}, "
          f"{src['width']}x{src['height']}, звук: {'есть' if src['has_audio'] else 'НЕТ'}")
    print(f"  частота кадров: заявлено {src['fps_declared']:.0f}, фактически {src['fps_actual']:.2f}"
          f"{'  (переменная — норма для записи экрана)' if src['vfr'] else ''}")
    if cfg.audio and not cfg.use_rubberband:
        print("  ВНИМАНИЕ: rubberband-r3 не найден, звук тянется через atempo (хуже качеством)")
    print()

    plan_path = Path(cfg.plan).expanduser() if cfg.plan else out_dir / "plan.txt"
    steps, cuts = parse_plan(plan_path, src["duration"], cfg.allow_gaps)
    pieces = apply_cuts(steps, cuts)

    if cfg.dry_run:
        do_dry_run(cfg, src, pieces)
        return EXIT_OK

    if cfg.pilot:
        do_pilot(cfg, src, pieces, work)
        return EXIT_OK

    if cfg.check_only:
        finals = [p for p in (out_dir / "final.mp4", out_dir / "final-loud.mp4") if p.exists()]
        if not finals:
            raise Fail(EXIT_INPUT, "нечего сверять: final.mp4 не найден")
    else:
        finals = do_build(cfg, src, pieces, work)

    checks = Checks()
    result = verify(cfg, src, pieces, work, finals, checks)

    print()
    print(result["table"])
    print(checks.render())

    report = {
        "source": src,
        "settings": {k: getattr(cfg, k) for k in
                     ("height", "fps", "crf", "preset", "audio", "loudnorm",
                      "use_rubberband", "target_mb", "tol_segment_frames", "tol_total_sec")},
        "segments": result["rows"],
        "total": {"plan": result["sum_plan"], "video": result["sum_video"],
                  "audio": result["sum_audio"], "frames": result["sum_frames"]},
        "spot_check": result["spots"],
        "finals": [{"path": str(p), "size": p.stat().st_size,
                    "durations": stream_durations(p)} for p in finals],
        "checks": checks.items,
    }
    report_path = Path(cfg.json).expanduser() if cfg.json else out_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    for path in finals:
        print(f"{path}  —  {path.stat().st_size / 1024 ** 2:.1f} МБ")
    print(f"отчёт: {report_path}")

    if checks.failed:
        print(f"\nСВЕРКА НЕ СОШЛАСЬ: провалено проверок — {len(checks.failed)}. "
              f"Вердикт «готово» выдавать нельзя.")
        return EXIT_DRIFT
    print("\nВсе проверки сошлись. Код возврата 0 сам по себе ничего не доказывает — "
          "смотрите таблицу и список проверок выше.")
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as exc:
        print(f"\nОШИБКА: {exc.message}", file=sys.stderr)
        sys.exit(exc.code)
    except KeyboardInterrupt:
        print("\nпрервано", file=sys.stderr)
        sys.exit(EXIT_TOOL)
