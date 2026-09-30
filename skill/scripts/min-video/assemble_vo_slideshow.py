# -*- coding: utf-8 -*-
"""Assemble 16:9 page PNGs + voiceover + ASS/SRT into one MP4.

Stills stay locked. Only a short fade at the page cut.

    assemble_vo_slideshow.py <pages_dir> <audio> <subs> <output> --durations-json <每页秒数.json>
    assemble_vo_slideshow.py <pages_dir> <audio> <subs> <output> --durations 37.2,46.4,...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402


def still_filter(seconds: float) -> str:
    fade = min(0.4, max(0.16, seconds * 0.06))
    fade_out_at = max(seconds - fade, 0.01)
    return (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
        f"fade=t=in:st=0:d={fade:.3f},"
        f"fade=t=out:st={fade_out_at:.3f}:d={fade:.3f},"
        "format=yuv420p"
    )


def pages_for_voice(pages_dir: Path, durations: list[float], page_nums: list[str] | None = None) -> list[Path]:
    """Use the oral page numbers when the slide folder has extra images."""
    files = sorted(pages_dir.glob("*.png"), key=lambda p: p.name.casefold())
    if len(files) == len(durations):
        return files
    nums = [str(num).zfill(2) for num in (page_nums or [])]
    if len(nums) != len(durations):
        raise SystemExit(f"pages={len(files)} durations={len(durations)}")
    chosen: list[Path] = []
    for num in nums:
        hits = [path for path in files if path.name.startswith(num)]
        if len(hits) != 1:
            raise SystemExit(f"第{num}页页图有 {len(hits)} 张，对不上口播稿")
        chosen.append(hits[0])
    return chosen


def assemble(
    pages_dir: Path,
    audio: Path,
    subs: Path,
    output: Path,
    durations: list[float],
    page_nums: list[str] | None = None,
) -> Path:
    pages = pages_for_voice(pages_dir, durations, page_nums)
    if not audio.is_file() or not subs.is_file():
        raise SystemExit("audio or subs missing")

    work = output.parent / "_assemble"
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for index, (page, seconds) in enumerate(zip(pages, durations), 1):
        clip = work / f"{index:02d}.mp4"
        mini.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", str(page),
                "-t", f"{seconds:.3f}", "-vf", still_filter(seconds), "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(clip),
            ]
        )
        clips.append(clip)

    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="ascii")
    silent = work / "silent.mp4"
    mini.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat.name,
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", silent.name],
        cwd=work,
    )

    suffix = subs.suffix.lower()
    sub_copy = work / ("subs.ass" if suffix == ".ass" else "subs.srt")
    sub_copy.write_bytes(subs.read_bytes())
    vf = f"ass={sub_copy.name}" if suffix == ".ass" else f"subtitles={sub_copy.name}"

    output.parent.mkdir(parents=True, exist_ok=True)
    mini.run(
        ["ffmpeg", "-y", "-i", silent.name, "-i", str(audio.resolve()), "-vf", vf,
         "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-shortest",
         "-pix_fmt", "yuv420p", str(output.resolve())],
        cwd=work,
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages_dir", type=Path)
    parser.add_argument("audio", type=Path)
    parser.add_argument("subs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--durations", default="", help="Comma-separated seconds per page")
    parser.add_argument("--durations-json", type=Path, default=None)
    args = parser.parse_args()

    if args.durations_json:
        durations = mini.load_durations(args.durations_json)
    else:
        durations = [float(x) for x in args.durations.split(",") if x.strip()]
    if not durations:
        raise SystemExit("need --durations or --durations-json")
    print(assemble(args.pages_dir, args.audio, args.subs, args.output, durations))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
