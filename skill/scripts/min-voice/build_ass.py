# -*- coding: utf-8 -*-
"""Cinema-style one-line captions from the voiced script and word timestamps.

    build_ass.py <course_dir> [--brand 谷子]

Style (font, size, colour, outline, max chars per line) comes from
config/品牌包/<brand>/字幕.md. Cue times come from the TTS word timestamps in
每页秒数.json. （停顿） holds the previous line for the silence that was
actually mixed. Character-count timing is not used.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

_VO_PATH = Path(__file__).with_name("gen_pages_vo.py")
_VO_SPEC = importlib.util.spec_from_file_location("gen_pages_vo", _VO_PATH)
assert _VO_SPEC and _VO_SPEC.loader
_vo = importlib.util.module_from_spec(_VO_SPEC)
_VO_SPEC.loader.exec_module(_vo)

STAGE_DIR = re.compile(r"（停顿）|（互动）|（讲案例）")
PAUSE_SAY = re.compile(r"停\s*([一二三四五六七八九十两零\d]+)\s*秒")
CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def parse_pause_number(raw: str, default: float = 20.0) -> float:
    raw = raw.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return float(raw)
    if raw == "十":
        return 10.0
    if raw.startswith("十"):
        return 10.0 + CN_DIGIT.get(raw[1:], 0)
    if raw.endswith("十") and len(raw) == 2:
        return float(CN_DIGIT.get(raw[0], 0) * 10)
    if "十" in raw:
        left, right = raw.split("十", 1)
        return float(CN_DIGIT.get(left, 1) * 10 + CN_DIGIT.get(right, 0))
    return float(CN_DIGIT.get(raw, default) or default)
HAN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
# 句号、引号、括号、书名号不上屏；顿号逗号冒号分号要留
DROP = str.maketrans("", "", "。「」“”‘’（）()《》【】！!")
CONJ = ("或者", "还是", "以及", "并且", "而且", "但是", "因为")


def ass_time(seconds: float) -> str:
    seconds = max(seconds, 0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def han_len(text: str) -> int:
    return len(HAN.findall(text))


def clean(text: str) -> str:
    text = STAGE_DIR.sub("", text)
    keep_q = text.rstrip().endswith(("？", "?"))
    text = text.translate(DROP).replace(" ", "").replace("?", "")
    text = text.replace("？", "")
    text = re.sub(r"[，、；：]{2,}", lambda m: m.group(0)[0], text)
    text = text.strip("，、；：")
    if keep_q:
        text += "？"
    return text


def _soft_cut(text: str, max_line: int) -> list[str]:
    """Last resort: break a punctuation-less clause without orphaning 1–2 chars."""
    chars = list(text)
    han_idx = [i for i, ch in enumerate(chars) if HAN.match(ch)]
    if len(han_idx) <= max_line + 2:
        return [text]
    cut_at = None
    for word in CONJ:
        pos = text.rfind(word, 0, han_idx[min(max_line, len(han_idx) - 1)] + 1)
        if pos > 0 and han_len(text[:pos]) >= 4:
            cut_at = pos
            break
    if cut_at is None:
        target = han_idx[max_line - 1] + 1
        rest_han = han_len(text[target:])
        if rest_han < 3:
            return [text]
        cut_at = target
    return [text[:cut_at], text[cut_at:]]


def split_breaths(text: str, max_line: int) -> list[str]:
    text = STAGE_DIR.sub("。", text)
    chunks = re.split(r"(?<=[。？！；?])", text)
    out: list[str] = []
    for chunk in chunks:
        piece = chunk.strip()
        if not piece:
            continue
        if han_len(piece) <= max_line:
            out.append(piece)
            continue
        hold = ""
        for clause in re.split(r"(?<=[，,、：:])", piece):
            clause = clause.strip()
            if not clause:
                continue
            if han_len(clause) > max_line + 2:
                if hold:
                    out.append(hold)
                    hold = ""
                out.extend(_soft_cut(clause, max_line))
                continue
            trial = hold + clause
            if hold and han_len(trial) > max_line:
                out.append(hold)
                hold = clause
            else:
                hold = trial
        if hold:
            out.append(hold)
    return [b for b in out if clean(b)]


def pause_seconds(text: str, default: float = 0.0) -> float:
    hit = PAUSE_SAY.search(text)
    if hit:
        return parse_pause_number(hit.group(1), default or 20)
    if "（停顿）" in text:
        return default
    return 0.0


def weight(text: str) -> float:
    spoken = han_len(text)
    spoken += 0.45 * (text.count("，") + text.count("、") + text.count("："))
    spoken += 0.8 * (text.count("。") + text.count("？") + text.count("！"))
    return max(spoken, 1.0)


def hex_to_ass(rgb: str) -> str:
    rgb = rgb.strip().lstrip("#")
    if len(rgb) != 6:
        return "&H00E2EFF6"
    r, g, b = rgb[0:2], rgb[2:4], rgb[4:6]
    return f"&H00{b}{g}{r}".upper()


def header_pause(doc) -> float:
    raw = (doc.header.get("停顿") or doc.header.get("停顿秒数") or "").strip()
    hit = re.search(r"(\d+(?:\.\d+)?)", raw)
    return float(hit.group(1)) if hit else 0.0


def parse_ass_time(raw: str) -> float:
    hour, minute, second = raw.split(":")
    return int(hour) * 3600 + int(minute) * 60 + float(second)


def max_line_for(course: Path) -> int:
    brand = "谷子"
    state = course / "_state.md"
    if state.is_file():
        brand = mini.read_table(state).get("brand") or brand
    sub = mini.read_table(mini.brand_dir(brand) / "字幕.md")
    match = re.search(r"(\d+)\s*[～~\-–]\s*(\d+)", sub.get("每行", "12～16"))
    return int(match.group(2)) if match else 16


def alignment_error(course: Path) -> str:
    """Refuse a caption track whose cue times are not the spoken word times."""
    mismatch = mini.timed_voice_error(course)
    if mismatch:
        return mismatch
    vo_dir = course / "30-口播字幕"
    oral = oral_script_for_audio(vo_dir)
    doc = mini.parse_script(oral)
    report = json.loads((vo_dir / "每页秒数.json").read_text(encoding="utf-8"))
    pages = report.get("pages") or []
    if not any(page.speech.strip() for page in doc.pages):
        return ""
    ass_path = vo_dir / "字幕轨.ass"
    if not ass_path.is_file():
        return "字幕轨还没生成"
    got: list[tuple[float, str]] = []
    for line in ass_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        cells = line.split(",", 3)
        if len(cells) < 3:
            return "字幕轨格式读不了"
        got.append((parse_ass_time(cells[1]), line.rsplit(",,", 1)[-1].strip()))
    expected: list[tuple[float, str]] = []
    cursor = 0.0
    pause = header_pause(doc)
    line_limit = max_line_for(course)
    for page, item in zip(doc.pages, pages):
        for start, _end, text in cues_from_timed_words(
            page.speech,
            item.get("words") or [],
            item.get("holds") or [],
            pause,
            line_limit,
            cursor,
        ):
            expected.append((start, text))
        cursor += float(item["seconds"])
    if len(got) != len(expected):
        return f"字幕 {len(got)} 条，按逐字时间应是 {len(expected)} 条。先重出字幕。"
    for index, ((seen_at, seen), (want_at, want)) in enumerate(zip(got, expected), 1):
        if seen != want or abs(seen_at - want_at) > 0.03:
            return f"第{index}条字幕没有落在发音时间上。先重出字幕，不能按字数摊。"
    return ""


def oral_script_for_audio(vo_dir: Path) -> Path:
    """Use the script whose page titles match 每页秒数.json, the file that was voiced."""
    pages: list = []
    dur_path = vo_dir / "每页秒数.json"
    if dur_path.is_file():
        data = json.loads(dur_path.read_text(encoding="utf-8"))
        pages = data.get("pages") or []
    chosen = mini._script_matching_voice(vo_dir, pages)
    if chosen is None:
        raise SystemExit("缺 30-口播字幕/口播稿.md；字幕不能回读内容正稿。")
    return chosen


def expand_timed_chars(words: list[dict]) -> list[tuple[str, float, float]]:
    """One spoken character, with punctuation time attached to the previous character."""
    spans: list[tuple[str, float, float]] = []
    for word in words:
        start = float(word["start"])
        end = float(word["end"])
        chars = HAN.findall(str(word.get("word") or ""))
        if not chars:
            if spans and end > spans[-1][2]:
                text, char_start, _ = spans[-1]
                spans[-1] = (text, char_start, end)
            continue
        step = max(end - start, 0.001) / len(chars)
        for index, char in enumerate(chars):
            spans.append((char, start + index * step, start + (index + 1) * step))
    return spans


def cues_from_timed_words(
    speech: str,
    words: list[dict],
    holds: list[dict],
    default_pause: float,
    max_line: int,
    cursor: float = 0.0,
) -> list[tuple[float, float, str]]:
    """Place each caption on the words that were actually spoken."""
    spans = expand_timed_chars(words)
    index = 0
    hold_index = 0
    cues: list[tuple[float, float, str]] = []
    for kind, payload in _vo.tts_segments(speech, default_pause):
        if kind == "silence":
            if not cues or hold_index >= len(holds):
                raise SystemExit("停顿段数和成音里的静音不一致")
            hold = holds[hold_index]
            hold_index += 1
            start, _, text = cues[-1]
            cues[-1] = (start, max(cues[-1][1], cursor + float(hold["end"])), text)
            continue
        for breath in split_breaths(str(payload), max_line):
            line = clean(breath)
            needed = HAN.findall(breath)
            if not line or not needed:
                continue
            if index + len(needed) > len(spans):
                raise SystemExit("逐字时间盖不住这一页口播")
            chunk = spans[index : index + len(needed)]
            heard = "".join(char for char, _, _ in chunk)
            if heard != "".join(needed):
                raise SystemExit(f"逐字时间和口播对不上：期望「{''.join(needed[:12])}」实际「{heard[:12]}」")
            start = cursor + chunk[0][1]
            end = cursor + chunk[-1][2]
            if cues and start < cues[-1][1]:
                prev_start, _, prev_text = cues[-1]
                cues[-1] = (prev_start, start, prev_text)
            if end <= start:
                end = start + 0.2
            cues.append((start, end, line))
            index += len(needed)
    if index != len(spans):
        raise SystemExit("逐字时间比口播多出一段，停止")
    if hold_index != len(holds):
        raise SystemExit("成音里的静音没有对应的（停顿）")
    return cues


def layout_page_cues(
    speech: str,
    page_seconds: float,
    default_pause: float,
    max_line: int,
    cursor: float = 0.0,
) -> list[tuple[float, float, str]]:
    """Character-weight estimate kept for pause-shape checks. Production captions use word timestamps."""
    groups: list[list[str] | float] = []
    for kind, payload in _vo.tts_segments(speech, default_pause):
        if kind == "silence":
            groups.append(float(payload))
            continue
        breaths = split_breaths(str(payload), max_line)
        if breaths:
            groups.append(breaths)
    spoken = [breath for group in groups if isinstance(group, list) for breath in group]
    reserved = sum(group for group in groups if isinstance(group, float))
    usable = max(page_seconds - 0.16 - reserved, 0.4 if spoken else 0.0)
    weights = [weight(breath) for breath in spoken]
    total_w = sum(weights) or 1.0
    t = cursor + 0.08
    page_end = cursor + page_seconds - 0.04
    cues: list[tuple[float, float, str]] = []
    for group in groups:
        if isinstance(group, float):
            hold_until = min(t + group, page_end)
            if cues:
                start, end, text = cues[-1]
                cues[-1] = (start, max(end, hold_until), text)
            t = hold_until
            continue
        for breath in group:
            line = clean(breath)
            if not line:
                continue
            dur = usable * (weight(breath) / total_w)
            end = min(t + max(dur, 0.3), page_end)
            if end <= t:
                end = min(t + 0.3, page_end)
            cues.append((t, end, line))
            t = min(end + 0.03, page_end)
    return cues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_dir", type=Path)
    parser.add_argument("--brand", default="谷子")
    args = parser.parse_args()

    sub = mini.read_table(mini.brand_dir(args.brand) / "字幕.md")
    font = sub.get("字体", "Microsoft YaHei")
    size = int(re.sub(r"\D", "", sub.get("字号", "54")) or 54)
    cm = re.search(r"#[0-9A-Fa-f]{6}", sub.get("字色", ""))
    colour = hex_to_ass(cm.group(0) if cm else "#F6EFE2")
    outline = int(re.sub(r"\D", "", sub.get("描边", "3")) or 3)
    m = re.search(r"(\d+)\s*[～~\-–]\s*(\d+)", sub.get("每行", "12～16"))
    max_line = int(m.group(2)) if m else 16

    mismatch = mini.timed_voice_error(args.course_dir)
    if mismatch:
        raise SystemExit(mismatch)
    vo_dir = args.course_dir / "30-口播字幕"
    oral_script = oral_script_for_audio(vo_dir)
    doc = mini.parse_script(oral_script)
    report = json.loads((vo_dir / "每页秒数.json").read_text(encoding="utf-8"))
    pages = report.get("pages") or []
    if len(pages) != len(doc.pages):
        raise SystemExit(f"pages {len(doc.pages)} durations {len(pages)}")
    default_pause = header_pause(doc)
    print(f"script={oral_script.name} pause={default_pause:g} timing=words")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Course,{font},{size},{colour},{colour},&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{outline},0,2,80,80,76,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    cursor = 0.0
    for page, item in zip(doc.pages, pages):
        seconds = float(item["seconds"])
        for start, end, line in cues_from_timed_words(
            page.speech,
            item.get("words") or [],
            item.get("holds") or [],
            default_pause,
            max_line,
            cursor,
        ):
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Course,,0,0,0,,{line}")
        cursor += seconds

    out = vo_dir / "字幕轨.ass"
    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    long = [e for e in events if han_len(e.rsplit(",,", 1)[-1].rstrip("？")) > max_line + 2]
    print(f"{out} cues={len(events)} over_{max_line}={len(long)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
