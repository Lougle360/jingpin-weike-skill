# -*- coding: utf-8 -*-
"""Check S3 口播稿.md against the approved 内容稿.md."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402
import speakable  # noqa: E402

REQUIRED = ["课名", "课程目标", "学员", "时长", "不讲"]
DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*[～~\-–至]\s*(\d+(?:\.\d+)?)\s*分")
PAUSE = re.compile(r"(\d+(?:\.\d+)?)")
NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
PAGE_WORD = re.compile(r"第\s*[0-9一二三四五六七八九十]+\s*页")
OLD_ID = re.compile(r"\b(?:FW|TH|TOOL|SC|DL|EX)-[A-Za-z0-9-]*\d{2}\b")
DOT_ID = re.compile(
    r"\b(?:foundation|core|advanced)?\.?(?:concept|principle|viewpoint|misconception|"
    r"guideline|framework|rule|workflow|tool|solution|scene|case|analogy|story|boundary|"
    r"source|data|quote|paradigm)\.[a-z0-9-]{3,}\b"
)
AI_PHRASES = (
    "在当今社会",
    "随着时代的发展",
    "值得注意的是",
    "不难发现",
    "综上所述",
    "让我们共同期待",
    "开启全新篇章",
    "赋能美好生活",
    "实现人生跃迁",
    "全方位、多维度、深层次地",
    "具有重要意义",
    "提供强有力的支撑",
)
HOST_PHRASES = (
    "各位亲爱的家人",
    "家人们",
    "我看到大家都说",
    "我看评论区",
    "各位都在问",
)
TEACHER_MARKERS = {
    "开题": ("那我们先搞清楚", "大家想过没有", "我先问大家", "你更像哪一种"),
    "解释": ("什么意思", "我给大家一个画面", "我给你们打个比方", "我再拆开给你们听", "你把这个听懂了"),
    "确认": ("对不对", "是不是", "大家听懂了吗"),
    "落锤": ("所以你们记住一句话", "这就叫", "不是没机会，是没接住"),
}
PUNCT = str.maketrans("", "", "。，、；：,.;:「」“”‘’（）()《》！!？? \n\r\t")
NOT_BUT = re.compile(r"不是[^。！？\n]{0,40}而是")
HOUR = re.compile(r"\d+\s*小时")


def norm(text: str) -> str:
    return text.translate(PUNCT)


def char_limit_error(
    total: int,
    duration: str,
    pause: float,
    cpm_low: float,
    cpm_high: float,
    *,
    skip: bool,
) -> str | None:
    """机器稿超出语速区间时报错。人工改稿传 skip=True，不因字数失败。"""
    match = DURATION.search(duration or "")
    if not match:
        return None
    low, high = float(match.group(1)), float(match.group(2))
    min_chars = int(max(0.0, low * 60.0 - pause) / 60.0 * cpm_low)
    max_chars = int(max(0.0, high * 60.0 - pause) / 60.0 * cpm_high)
    if min_chars >= max_chars:
        return f"停顿 {pause:g} 秒后时长区间无效"
    if skip or min_chars <= total <= max_chars:
        return None
    return f"口播 {total} 字，时长 {duration}（扣停顿 {pause:g} 秒）应在 {min_chars}～{max_chars}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_dir", type=Path)
    parser.add_argument("--cpm-low", type=float, default=230.0)
    parser.add_argument("--cpm-high", type=float, default=260.0)
    parser.add_argument(
        "--manual-edit",
        "--skip-char-limit",
        dest="manual_edit",
        action="store_true",
        help="审核页上手动改过的口播稿不卡页数、时长和字数",
    )
    args = parser.parse_args()

    source_path = args.course_dir / "10-内容稿" / "内容稿.md"
    outline_path = args.course_dir / "20-页图" / "PPT大纲.md"
    oral_path = args.course_dir / "30-口播字幕" / "口播稿.md"
    legacy_path = args.course_dir / "30-口播字幕" / "口播逐字稿.md"
    if not oral_path.is_file() and legacy_path.is_file():
        oral_path = legacy_path
    if not source_path.is_file():
        raise SystemExit("缺 10-内容稿/内容稿.md")
    if not outline_path.is_file():
        raise SystemExit("缺 20-页图/PPT大纲.md")
    if not oral_path.is_file():
        raise SystemExit("缺 30-口播字幕/口播稿.md")

    scale = mini.read_plan_scale(args.course_dir)
    source_header = mini.read_table(source_path)
    source_text = source_path.read_text(encoding="utf-8")
    outline = mini.parse_script(outline_path)
    oral = mini.parse_script(oral_path)
    errors: list[str] = []
    warns: list[str] = []

    for key in REQUIRED:
        if not oral.header.get(key):
            errors.append(f"口播稿文头缺「{key}」")
        elif args.manual_edit:
            continue
        elif source_header.get(key) and oral.header.get(key) != source_header.get(key):
            errors.append(f"文头「{key}」与内容正稿不一致")

    source_shape = [(p.num, p.title) for p in outline.pages]
    oral_shape = [(p.num, p.title) for p in oral.pages]
    if oral_shape != source_shape and not args.manual_edit:
        errors.append("口播稿页号、页名或页序与内容正稿不一致")

    for page in oral.pages:
        if not page.speech:
            errors.append(f"第{page.num}页 缺口播")
            continue
        if PAGE_WORD.search(page.speech):
            errors.append(f"第{page.num}页 念了「第 N 页」")
        if OLD_ID.search(page.speech) or DOT_ID.search(page.speech):
            errors.append(f"第{page.num}页 泄漏组件 ID")
        for phrase in AI_PHRASES:
            if phrase in page.speech:
                errors.append(f"第{page.num}页 含 AI 腔硬禁语「{phrase}」")
        for phrase in HOST_PHRASES:
            if phrase in page.speech:
                errors.append(f"第{page.num}页 含通用主播腔「{phrase}」")
        if len(NOT_BUT.findall(page.speech)) > 1:
            errors.append(f"第{page.num}页「不是……而是……」超过一组")
        if HOUR.search(page.speech):
            errors.append(f"第{page.num}页把「N小时」作业时限写进了口播")

    source_speech = source_text
    oral_speech = "".join(p.speech for p in oral.pages)
    if norm(source_speech) == norm(oral_speech):
        warns.append("口播稿与内容正稿逐字相同，确认已完成老师化口播改写")

    source_numbers = Counter(NUMBER.findall(source_speech))
    oral_numbers = Counter(NUMBER.findall(oral_speech))
    extra_numbers = oral_numbers - source_numbers
    if extra_numbers:
        errors.append(
            f"口播稿出现内容母稿没有的数字事实：{dict(extra_numbers)}"
        )

    for label, needles in TEACHER_MARKERS.items():
        hits = [(needle, oral_speech.count(needle)) for needle in needles if needle in oral_speech]
        total = sum(count for _needle, count in hits)
        if total > 1:
            shown = "、".join(needle for needle, _count in hits)
            errors.append(f"口头禅「{label}」全课只能出现一次，现在有：{shown}")
    if not args.manual_edit:
        errors.extend(speakable.source_errors(oral_path.read_text(encoding="utf-8"), args.course_dir.resolve()))

    total = oral.speech_chars()
    duration = oral.header.get("时长", "") or mini.read_table(outline_path).get("预计时长", "")
    pause_raw = (
        oral.header.get("停顿")
        or oral.header.get("停顿秒数")
        or "0"
    )
    pm = PAUSE.search(pause_raw)
    pause = float(pm.group(1)) if pm else 0.0
    planned_range = scale.get("duration_range")
    if planned_range and not args.manual_edit:
        planned_match = DURATION.search(oral.header.get("时长", "") or "")
        if not planned_match:
            errors.append("口播稿时长须与方案「视频时长」一致")
        else:
            oral_range = (float(planned_match.group(1)), float(planned_match.group(2)))
            if oral_range != planned_range:
                errors.append(
                    f"口播稿时长「{oral.header.get('时长')}」与方案视频时长「{scale.get('duration')}」不一致"
                )
    if scale.get("pause") is not None and not args.manual_edit and pause != float(scale["pause"]):
        errors.append(f"口播停顿 {pause:g} 秒，方案停顿 {scale['pause']:g} 秒")

    if DURATION.search(duration):
        limit_error = char_limit_error(
            total,
            duration,
            pause,
            args.cpm_low,
            args.cpm_high,
            skip=args.manual_edit,
        )
        if limit_error:
            errors.append(limit_error)
    elif not args.manual_edit:
        warns.append(f"时长「{duration}」解析不出区间，跳过字数核对")

    print(f"pages={len(oral.pages)} chars={total} errors={len(errors)} warnings={len(warns)}")
    for error in errors:
        print("ERROR:", error)
    for warning in warns:
        print("WARN:", warning)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
