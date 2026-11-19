"""Сжатие готового скринкаста без изменения скорости; сравнение одинаковых кадров."""
import argparse
import math
import os
from pathlib import Path
import tempfile

from build import Fail, ffmpeg, ffprobe_json, probe_source


def encoding(fps, crf, preset):
    return ["-c:v", "libx265", "-preset", preset, "-crf", str(crf),
            "-x265-params", f"pools=4:frame-threads=3:aq-mode=3:sao=0:keyint={fps * 30}:log-level=error",
            "-tag:v", "hvc1", "-video_track_timescale", "48000", "-movie_timescale", "48000",
            "-movflags", "+faststart"]


def tracks(path):
    data = ffprobe_json(["-show_entries",
                         "format=start_time,duration:stream=codec_type,width,height,start_time,duration",
                         str(path)])
    return data["format"], data["streams"]


def decode(path):
    ffmpeg(["-xerror", "-threads", "3", "-i", str(path), "-map", "0:v:0", "-map", "0:a?",
            "-enc_time_base:v", "1/48000", "-fps_mode", "passthrough", "-f", "null", "-"],
           "проверка файла целиком")


def audio_hashes(path):
    return ffmpeg(["-i", str(path), "-map", "0:a", "-c", "copy", "-f", "streamhash",
                   "-hash", "sha256", "-"], "сверка звуковых дорожек").stdout


def compare_timing(src, result, fps):
    old_format, old = tracks(src)
    new_format, new = tracks(result)
    before = [s for s in old if s["codec_type"] == "audio"]
    after = [s for s in new if s["codec_type"] == "audio"]
    if len(before) != len(after) or (before and audio_hashes(src) != audio_hashes(result)):
        raise ValueError("Звуковые дорожки изменились при сжатии.")
    if abs(float(old_format["duration"]) - float(new_format["duration"])) > 1 / fps + .002:
        raise ValueError("Изменилась длительность монтажа.")
    for kind in ("audio", "video"):
        src_tracks = [s for s in old if s["codec_type"] == kind]
        dst_tracks = [s for s in new if s["codec_type"] == kind]
        for a, b in zip(src_tracks, dst_tracks):
            if kind == "video" and (a["width"], a["height"]) != (b["width"], b["height"]):
                raise ValueError("Изменился размер кадра.")
            offset_a = float(a.get("start_time", 0)) - float(old_format.get("start_time", 0))
            offset_b = float(b.get("start_time", 0)) - float(new_format.get("start_time", 0))
            tolerance = .002 if kind == "audio" else 1 / fps + .002
            if abs(offset_a - offset_b) > tolerance:
                raise ValueError("После сжатия сместилось начало дорожки.")
            if "duration" in a and "duration" in b and abs(float(a["duration"]) - float(b["duration"])) > tolerance:
                raise ValueError("После сжатия изменилась длина дорожки.")


def compare_frames(src, result, fps, crop, times, folder):
    x, y, width, height = crop
    frames = sorted({math.floor(t * fps + .5) for t in times})
    selection = "+".join(f"eq(n,{n})" for n in frames)
    for label, path in [("source", src), ("compact", result)]:
        filters = ([f"fps={fps}:round=near"] if label == "source" else [])
        filters.extend([f"select='{selection}'", f"crop={width}:{height}:{x}:{y}:exact=1"])
        ffmpeg(["-threads", "3", "-i", str(path), "-map", "0:v:0", "-an", "-filter_threads", "2",
                "-vf", ",".join(filters), "-fps_mode", "passthrough", "-threads", "2",
                "-frames:v", str(len(frames)), str(folder / (label + "-%03d.png"))],
               "сравнение мелкого текста в исходном масштабе")
        if len(list(folder.glob(label + "-*.png"))) != len(frames):
            raise ValueError("Не удалось получить все заказанные контрольные кадры.")
    (folder / "frames.txt").write_text("\n".join(f"{i:03d} {n / fps:.4f}" for i, n in enumerate(frames, 1)) + "\n")


def compact(src, out, fps, crf, preset, crop, times, proof, target_mb=None):
    info = probe_source(src)
    if out.exists() or out.suffix.lower() != ".mp4":
        raise ValueError("Нужен новый выходной файл MP4.")
    if not 1 <= fps <= 120 or not 0 <= crf <= 51:
        raise ValueError("Проверьте частоту кадров и качество кодирования.")
    x, y, width, height = crop
    if min(x, y) < 0 or min(width, height) <= 0 or x + width > info["width"] or y + height > info["height"]:
        raise ValueError("Область с мелким текстом выходит за кадр.")
    if not times or not all(math.isfinite(t) and 0 <= t < info["duration"] for t in times):
        raise ValueError("Контрольная метка находится за пределами файла.")
    if target_mb is not None and not (math.isfinite(target_mb) and target_mb > 0):
        raise ValueError("Лимит в мегабайтах должен быть положительным.")
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "compact.mp4"
        ffmpeg(["-xerror", "-threads", "3", "-i", str(src), "-map", "0:v:0", "-map", "0:a?",
                "-map_metadata", "-1", "-map_chapters", "-1", "-filter_threads", "2",
                "-vf", f"fps={fps}:round=near", *encoding(fps, crf, preset), "-c:a", "copy",
                str(stage)], "сжатие видеоряда")
        size = stage.stat().st_size
        if size >= info["size"] or (target_mb is not None and size > target_mb * 1_000_000):
            raise ValueError(f"Проба дала {size / 1e6:.2f} МБ при исходных {info['size'] / 1e6:.2f} МБ. Цель не достигнута.")
        compare_timing(src, stage, fps)
        decode(stage)
        proof.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="frames-", dir=proof))
        compare_frames(src, stage, fps, crop, times, folder)
        os.link(stage, out)
    print(f"{info['size'] / 1e6:.2f} → {size / 1e6:.2f} МБ (−{100 * (1 - size / info['size']):.1f}%). "
          f"Сверьте парные кадры при 100%: {folder}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--fps", type=int, required=True)
    p.add_argument("--crf", type=int, required=True)
    p.add_argument("--preset", choices=["fast", "medium", "slow"], default="slow")
    p.add_argument("--crop", nargs=4, type=int, required=True, metavar=("X", "Y", "W", "H"))
    p.add_argument("--at", type=float, nargs="+", required=True)
    p.add_argument("--proof", type=Path, required=True)
    p.add_argument("--target-mb", type=float)
    args = p.parse_args()
    try:
        compact(args.src, args.out, args.fps, args.crf, args.preset, args.crop, args.at, args.proof, args.target_mb)
    except (Fail, ValueError, OSError) as exc:
        p.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
