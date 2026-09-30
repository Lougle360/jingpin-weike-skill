# -*- coding: utf-8 -*-
"""Measure lecture-bed candidates: integrated LUFS, LRA, suggested mix level.

    python Skills/min-bgm/scripts/measure_bed.py [path ...]
    python Skills/min-bgm/scripts/measure_bed.py --vo projects/<课>/30-口播字幕/口播.wav
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import sys
sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini

UNDER_DB = 7.0
LRA_MAX = 5.0
DEFAULT_VO_I = -21.5


def ebur128(path: Path) -> tuple[float | None, float | None]:
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    integ = rng = None
    for ln in r.stderr.splitlines():
        if "I:" in ln and "LUFS" in ln:
            try:
                integ = float(ln.split("I:")[1].split("LUFS")[0].strip())
            except ValueError:
                pass
        if "LRA:" in ln and "LU" in ln:
            try:
                rng = float(ln.split("LRA:")[1].split("LU")[0].strip())
            except ValueError:
                pass
    return integ, rng


def suggest_level(bed_i: float, vo_i: float) -> float:
    target = vo_i - UNDER_DB
    return round(10 ** ((target - bed_i) / 20.0), 2)


def collect(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix.lower() in {".mp3", ".m4a", ".wav", ".ogg"}:
            out.append(p)
        elif p.is_dir():
            for ext in ("*.mp3", "*.m4a", "*.wav", "*.ogg"):
                out.extend(sorted(p.glob(ext)))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--vo", type=Path, default=None)
    args = parser.parse_args()
    root = None
    default_dir = mini.asset_root() / "背景音乐"
    files = collect(args.paths) if args.paths else collect([default_dir])
    if not files:
        print("没有可量的音频", file=sys.stderr)
        return 1
    vo_i = DEFAULT_VO_I
    if args.vo and args.vo.is_file():
        vo_i, _ = ebur128(args.vo)
        if vo_i is None:
            print(f"口播量不到: {args.vo}", file=sys.stderr)
            return 1
        print(f"口播 I={vo_i:.1f} LUFS  目标垫乐约 {vo_i - UNDER_DB:.1f}（低 {UNDER_DB:.0f} dB）")
    else:
        print(f"口播按 {vo_i:.1f} LUFS 估  目标垫乐约 {vo_i - UNDER_DB:.1f}")
    print(f"{'文件':<22} {'I':>7} {'LRA':>6} {'建议电平':>8} 收?")
    for path in files:
        integ, rng = ebur128(path)
        if integ is None or rng is None:
            print(f"{path.name:<22} {'?':>7} {'?':>6} {'?':>8} 量不到")
            continue
        level = suggest_level(integ, vo_i)
        admit = "可" if rng <= LRA_MAX else f"否 LRA>{LRA_MAX}"
        print(f"{path.name:<22} {integ:7.1f} {rng:6.1f} {level:8.2f} {admit}")
    print("LRA≤5 只是机器关。还要听 20 秒：像乐、不哭、无句读，才进配乐.md。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
