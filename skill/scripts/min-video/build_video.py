# -*- coding: utf-8 -*-
"""One-shot: pages + 口播 + 字幕 + 秒数 + brand 配乐 -> 40-成片/成片.mp4 + 质检记录.md

    build_video.py <course_dir> [--brand 谷子] [--mix-only] [--bgm 清冷观察]

Bed music / SFX files and levels come from config/品牌包/<brand>/配乐.md
(table 「曲库」+「缺省」; line 「压低参数」). Files are relative to
config/素材库.md 「素材根」. 底乐按内容稿关键词打分，平手回退缺省。
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

HERE = Path(__file__).resolve().parent
LAYER_W = (("title", 4), ("quote", 3), ("goal", 3), ("visual", 3), ("pages", 2), ("speech", 1))
NARRATIVE_BONUS = {"体验先导": "清冷观察", "正序": "温和推进"}


def _load_voice():
    path = HERE.parents[0] / "min-voice" / "build_ass.py"
    spec = importlib.util.spec_from_file_location("build_ass", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = mod  # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


@dataclass
class BedTrack:
    name: str
    path: Path
    scene: str
    keywords: list[str]
    level: float


@dataclass
class MusicPick:
    bgm: Path
    sfx: Path
    lv: object
    name: str
    scene: str
    reason: str
    scores: dict[str, int] = field(default_factory=dict)


def _parse_keywords(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[、,，;；/]", raw) if p.strip()]


def _parse_level(raw: str, default: float) -> float:
    return float(raw) if re.fullmatch(r"[\d.]+", raw.strip()) else default


def course_layers(course: Path) -> dict[str, str]:
    layers = {
        "title": course.name,
        "quote": "",
        "goal": "",
        "pages": "",
        "speech": "",
        "narrative": "",
        "visual": "",
    }
    content_path = course / "10-内容稿" / "内容稿.md"
    outline_path = course / "20-页图" / "PPT大纲.md"
    oral_path = course / "30-口播字幕" / "口播稿.md"
    if not content_path.is_file():
        return layers
    content = content_path.read_text(encoding="utf-8")
    header = mini.read_table(content_path)
    title_match = re.search(r"^#\s+内容稿[：:]\s*(.+?)\s*$", content, re.M)
    layers["title"] = title_match.group(1).strip() if title_match else course.name
    layers["goal"] = header.get("课程目标", "")
    layers["narrative"] = header.get("叙事", "")
    if outline_path.is_file():
        outline = mini.parse_script(outline_path)
        layers["pages"] = " ".join(
            [p.title for p in outline.pages] + [" ".join(p.visible) for p in outline.pages]
        )
    if oral_path.is_file():
        oral = mini.parse_script(oral_path)
        layers["speech"] = " ".join(p.speech for p in oral.pages)
    prompt_dir = course / "20-页图" / "_prompts"
    if prompt_dir.is_dir():
        layers["visual"] = " ".join(
            p.read_text(encoding="utf-8") for p in sorted(prompt_dir.glob("*.txt"))
        )
    return layers


def pick_track(tracks: list[BedTrack], layers: dict[str, str], fallback: BedTrack) -> tuple[BedTrack, str, dict[str, int]]:
    scores = {t.name: 0 for t in tracks}
    hits: dict[str, list[str]] = {t.name: [] for t in tracks}
    for track in tracks:
        for kw in track.keywords:
            weight = 0
            for layer, layer_w in LAYER_W:
                if kw and kw in layers.get(layer, ""):
                    weight = max(weight, layer_w)
            if weight:
                scores[track.name] += weight
                hits[track.name].append(kw)
        if NARRATIVE_BONUS.get(layers.get("narrative", "")) == track.name:
            scores[track.name] += 2
            hits[track.name].append(f"叙事:{layers['narrative']}")
    best = max(scores.values()) if scores else 0
    winners = [t for t in tracks if scores[t.name] == best and best > 0]
    if not winners:
        chosen = fallback
        reason = f"没有关键词命中，回退缺省「{fallback.name}」"
    elif len(winners) == 1:
        chosen = winners[0]
        reason = "、".join(hits[chosen.name][:8]) or chosen.scene
    else:
        chosen = next((t for t in winners if t.name == fallback.name), winners[0])
        reason = "平手，回退缺省" if chosen.name == fallback.name else "、".join(hits[chosen.name][:8])
    return chosen, reason, scores


def match_named(tracks: list[BedTrack], raw: str) -> BedTrack | None:
    key = raw.strip().lower()
    for track in tracks:
        if key in {track.name.lower(), track.path.stem.lower(), track.path.name.lower()}:
            return track
    return None


def read_music(brand: str, course: Path, forced: str = "") -> MusicPick:
    """Return ducked bed + SFX. 底乐按内容稿选，可 --bgm 指定。"""
    mix_mod = _load("mix_vo_bed")
    lv = mix_mod.Levels()
    music_md = mini.brand_dir(brand) / "配乐.md"
    root = mini.asset_root()
    tracks: list[BedTrack] = []
    fallback = sfx = None
    for cells in mini.read_table_rows(music_md):
        if len(cells) < 3:
            continue
        head, file = cells[0], cells[1]
        if head in ("曲目", "用途"):
            continue
        if head == "翻页":
            sfx = root / file
            lv.sfx = _parse_level(cells[2], lv.sfx)
            continue
        if head == "底乐":
            fallback = BedTrack("缺省", root / file, "缺省", [], _parse_level(cells[2], lv.bgm))
            continue
        if file.startswith("背景音乐/") and "活动" not in file:
            tracks.append(
                BedTrack(
                    name=head,
                    path=root / file,
                    scene=cells[2] if len(cells) > 2 else "",
                    keywords=_parse_keywords(cells[3]) if len(cells) > 3 else [],
                    level=_parse_level(cells[4], lv.bgm) if len(cells) > 4 else lv.bgm,
                )
            )
    text = music_md.read_text(encoding="utf-8")
    m = re.search(
        r"threshold\s*([\d.]+).*?ratio\s*([\d.]+).*?attack\s*([\d.]+).*?release\s*([\d.]+).*?knee\s*([\d.]+)",
        text,
        re.S,
    )
    if m:
        lv.threshold, lv.ratio, lv.attack, lv.release, lv.knee = (float(x) for x in m.groups())
    if fallback is None and tracks:
        fallback = tracks[0]
    if fallback is None or sfx is None:
        raise SystemExit("配乐.md 缺「曲库」或「翻页」")
    if not tracks:
        tracks = [fallback]
    fallback_track = next((t for t in tracks if t.path.resolve() == fallback.path.resolve()), tracks[0])
    if forced:
        chosen = match_named(tracks, forced)
        if chosen is None:
            names = "、".join(t.name for t in tracks)
            raise SystemExit(f"--bgm {forced} 不在曲库：{names}")
        reason = f"人工指定 {chosen.name}"
        scores = {t.name: 0 for t in tracks}
    else:
        chosen, reason, scores = pick_track(tracks, course_layers(course), fallback_track)
    lv.bgm = chosen.level
    for path in (chosen.path, sfx):
        if not path.is_file():
            raise SystemExit(f"素材不存在: {path}")
    return MusicPick(chosen.path, sfx, lv, chosen.name, chosen.scene, reason, scores)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_dir", type=Path)
    parser.add_argument("--brand", default="谷子")
    parser.add_argument("--mix-only", action="store_true", help="页图/字幕没变，只重混配乐")
    parser.add_argument("--bgm", default="", help="指定曲目名或文件名，跳过自动选曲")
    args = parser.parse_args()

    course = args.course_dir.resolve()
    pages = course / "20-页图" / "pages"
    vo_dir = course / "30-口播字幕"
    vo = vo_dir / "口播.wav"
    subs = vo_dir / "字幕轨.ass"
    dur_json = vo_dir / "每页秒数.json"
    out_dir = course / "40-成片"
    dry = out_dir / "_dry.mp4"  # assemble() puts its work dir at out_dir/_assemble
    final = out_dir / "成片.mp4"

    voice_mod = _load_voice()
    mismatch = voice_mod.alignment_error(course)
    if mismatch:
        raise SystemExit(mismatch)
    if not subs.is_file():
        raise SystemExit("字幕轨还没生成")
    if subs.stat().st_mtime + 1 < dur_json.stat().st_mtime:
        raise SystemExit("字幕轨比逐字时间旧，先重出字幕。")
    durations = mini.load_durations(dur_json)
    page_nums = [str(item.get("page") or "") for item in json.loads(dur_json.read_text(encoding="utf-8")).get("pages") or []]

    if not args.mix_only or not dry.is_file():
        asm = _load("assemble_vo_slideshow")
        asm.assemble(pages, vo, subs, dry, durations, page_nums)

    pick = read_music(args.brand, course, args.bgm)
    score_txt = " ".join(f"{k}={v}" for k, v in pick.scores.items())
    print(f"选曲 {pick.name} ← {pick.reason}" + (f" （{score_txt}）" if score_txt else ""))
    cuts = mini.cuts_from_durations(durations)
    mix_mod = _load("mix_vo_bed")
    mix_mod.mix(vo, pick.bgm, pick.sfx, dry, final, cuts, pick.lv)

    total = mini.probe_seconds(final)
    cues = sum(1 for line in subs.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:"))
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    (out_dir / "质检记录.md").write_text(
        f"""# 质检记录

| 项 | 值 |
|---|---|
| 时间 | {now} |
| 成片 | `40-成片/成片.mp4` |
| 时长 | {total:.1f} 秒（口播 {sum(durations):.1f} 秒） |
| 页数 | {len(durations)} |
| 字幕 | {cues} 条，`字幕轨.ass` |
| 字幕时间 | 逐字对齐 |
| 底乐 | `{pick.bgm.name}` · {pick.lv.bgm} · {pick.name} |
| 选曲 | {pick.reason} |
| 翻页 | `{pick.sfx.name}` · {pick.lv.sfx}，{len(cuts)} 处 |
| 压低 | threshold {pick.lv.threshold} · ratio {pick.lv.ratio} · attack {pick.lv.attack} · release {pick.lv.release} |
| 画面 | 页内静止，页间淡入淡出 |

## 看片意见

- 
""",
        encoding="utf-8",
    )
    print(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
