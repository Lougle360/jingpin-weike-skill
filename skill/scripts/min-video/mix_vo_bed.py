# -*- coding: utf-8 -*-
"""Mix voiceover with ducked bed music + page-turn SFX. Voice stays full level.

    mix_vo_bed.py --vo 口播.wav --bgm bed.mp3 --sfx page.mp3 --video in.mp4 --out out.mp4
                  --cuts 37.2,83.6,...                   [--bgm-level 0.38] [--sfx-level 0.38]
                  [--threshold 0.04 --ratio 6 --attack 140 --release 480 --knee 6]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402


@dataclass
class Levels:
    bgm: float = 0.16
    sfx: float = 0.38
    threshold: float = 0.04
    ratio: float = 6.5
    attack: float = 55.0
    release: float = 420.0
    knee: float = 6.0
    fade_in: float = 1.6
    fade_out: float = 6.0


def flatten_bed() -> str:
    """Keep bed out of the speech band so 谷子 doesn't smear into the pad."""
    return (
        "highpass=f=220,"
        "equalizer=f=350:t=q:w=1.0:g=-4,"
        "equalizer=f=1200:t=q:w=1.6:g=-9,"
        "equalizer=f=2500:t=q:w=1.2:g=-6,"
        "lowpass=f=6500"
    )


def loop_bgm(src: Path, dest: Path, duration: float, overlap: float = 2.5) -> None:
    src_dur = mini.probe_seconds(src)
    if src_dur >= duration:
        mini.run(["ffmpeg", "-y", "-i", str(src), "-t", f"{duration:.3f}", "-c:a", "pcm_s16le", str(dest)])
        return
    copies = 2
    acc = src_dur
    while acc < duration + overlap:
        copies += 1
        acc += src_dur - overlap
    inputs: list[str] = []
    for _ in range(copies):
        inputs.extend(["-i", str(src)])
    if copies == 2:
        graph = f"[0:a][1:a]acrossfade=d={overlap:.2f}:c1=tri:c2=tri[out]"
    else:
        parts = [f"[0:a][1:a]acrossfade=d={overlap:.2f}:c1=tri:c2=tri[a1]"]
        last = "a1"
        for index in range(2, copies):
            label = "out" if index == copies - 1 else f"a{index}"
            parts.append(f"[{last}][{index}:a]acrossfade=d={overlap:.2f}:c1=tri:c2=tri[{label}]")
            last = label
        graph = ";".join(parts)
    mini.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
         "-t", f"{duration:.3f}", "-c:a", "pcm_s16le", str(dest)]
    )


def mix(vo: Path, bgm: Path, sfx: Path, video: Path, out: Path, cuts: list[float], lv: Levels) -> Path:
    for p in (vo, bgm, sfx, video):
        if not p.is_file():
            raise SystemExit(f"missing: {p}")
    if not cuts:
        raise SystemExit("need at least one page cut")
    duration = mini.probe_seconds(vo)
    fade_out_at = max(duration - lv.fade_out, 2.0)

    work = out.parent / "_audio"
    work.mkdir(parents=True, exist_ok=True)
    bgm_src = work / ("bgm" + bgm.suffix.lower())
    sfx_src = work / ("page" + sfx.suffix.lower())
    bgm_loop = work / "bgm_loop.wav"
    mixed = work / "mix.wav"
    shutil.copyfile(bgm, bgm_src)
    shutil.copyfile(sfx, sfx_src)
    loop_bgm(bgm_src, bgm_loop, duration)

    n = len(cuts)
    labels = "".join(f"[s{i}]" for i in range(n))
    delayed = []
    for i, sec in enumerate(cuts):
        start = max(sec - 0.18, 0.01)  # peak lands on the fade
        ms = max(int(round(start * 1000)), 1)
        delayed.append(f"[s{i}]adelay={ms}|{ms}[d{i}]")
    mix_in = "".join(f"[d{i}]" for i in range(n))
    sfx_graph = (
        f"[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        f"volume={lv.sfx},asplit={n}{labels};"
        + "".join(part + ";" for part in delayed)
        + f"{mix_in}amix=inputs={n}:duration=longest:normalize=0[sfx]"
    )
    graph = (
        "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        "volume=1.0,asplit[vo_main][vo_sc];"
        "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        f"{flatten_bed()},volume={lv.bgm},"
        f"afade=t=in:st=0:d={lv.fade_in},afade=t=out:st={fade_out_at:.3f}:d={lv.fade_out}[bgm];"
        f"{sfx_graph};"
        f"[bgm][vo_sc]sidechaincompress=threshold={lv.threshold}:ratio={lv.ratio}:attack={lv.attack}:"
        f"release={lv.release}:makeup=1:detection=rms:knee={lv.knee}:mix=0.92[ducked_bgm];"
        "[ducked_bgm][sfx]amix=inputs=2:duration=first:normalize=0[bed];"
        "[vo_main][bed]amix=inputs=2:duration=first:normalize=0:weights=1 1[out]"
    )
    mini.run(
        ["ffmpeg", "-y", "-i", str(vo.resolve()), "-i", str(bgm_loop.resolve()), "-i", str(sfx_src.resolve()),
         "-filter_complex", graph, "-map", "[out]", "-t", f"{duration:.3f}",
         "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(mixed.resolve())]
    )
    tmp = out.with_suffix(".tmp.mp4")
    mini.run(
        ["ffmpeg", "-y", "-i", str(video.resolve()), "-i", str(mixed.resolve()),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(tmp.resolve())]
    )
    tmp.replace(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vo", type=Path, required=True)
    parser.add_argument("--bgm", type=Path, required=True)
    parser.add_argument("--sfx", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cuts", required=True, help="Comma-separated page-cut seconds (not including t=0)")
    parser.add_argument("--bgm-level", type=float, default=Levels.bgm)
    parser.add_argument("--sfx-level", type=float, default=Levels.sfx)
    parser.add_argument("--threshold", type=float, default=Levels.threshold)
    parser.add_argument("--ratio", type=float, default=Levels.ratio)
    parser.add_argument("--attack", type=float, default=Levels.attack)
    parser.add_argument("--release", type=float, default=Levels.release)
    parser.add_argument("--knee", type=float, default=Levels.knee)
    args = parser.parse_args()
    lv = Levels(
        bgm=args.bgm_level, sfx=args.sfx_level, threshold=args.threshold, ratio=args.ratio,
        attack=args.attack, release=args.release, knee=args.knee,
    )
    cuts = [float(x) for x in args.cuts.split(",") if x.strip()]
    print(mix(args.vo, args.bgm, args.sfx, args.video, args.out, cuts, lv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
