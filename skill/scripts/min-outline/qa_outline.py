# -*- coding: utf-8 -*-
"""Hard checks for PPT大纲.md before the outline gate."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402
import speakable  # noqa: E402

PAGE = re.compile(r"^##\s*第(\d{2})页｜(.+?)\s*$", re.M)
REQUIRED_BLOCKS = ("正文", "提示词")
OLD_ID = re.compile(r"\b(?:FW|TH|TOOL|SC|DL|EX)-[A-Za-z0-9-]*\d{2}\b")


def page_blocks(text: str) -> list[tuple[str, str, str]]:
    hits = list(PAGE.finditer(text))
    return [
        (hit.group(1), hit.group(2).strip(), text[hit.end() : hits[index + 1].start() if index + 1 < len(hits) else len(text)])
        for index, hit in enumerate(hits)
    ]


def block(body: str, name: str) -> str:
    hit = re.search(rf"^###\s+{re.escape(name)}\s*$", body, re.M)
    if not hit:
        return ""
    rest = body[hit.end() :]
    nxt = re.search(r"^###\s+", rest, re.M)
    return rest[: nxt.start()].strip() if nxt else rest.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outline", type=Path)
    args = parser.parse_args()
    text = args.outline.read_text(encoding="utf-8")
    aligned = mini.align_outline_text(text)
    if aligned != text:
        args.outline.write_text(aligned, encoding="utf-8")
        text = aligned
    pages = page_blocks(text)
    errors: list[str] = []
    warnings: list[str] = []

    title_hit = re.search(r"^#\s+PPT\s*大纲：\s*(.+?)\s*$", text, re.M)
    course_title = title_hit.group(1).strip() if title_hit else ""
    if not course_title:
        errors.append("文头须为「# PPT 大纲：<课名>」")
    if not 5 <= len(pages) <= 12:
        errors.append(f"PPT 页数须为 5～12 页，现在 {len(pages)}")

    scale = mini.read_plan_scale(args.outline.resolve().parents[1])
    planned = scale.get("pages")
    if planned and int(planned) != len(pages):
        errors.append(f"大纲 {len(pages)} 页，方案预计 PPT {planned} 页")

    for index, (num, title, body) in enumerate(pages, 1):
        if int(num) != index:
            errors.append(f"页号不连续：第 {index} 个页面写成 {num}")
        for name in REQUIRED_BLOCKS:
            value = block(body, name)
            if not value or value.startswith("（"):
                errors.append(f"第{num}页缺「{name}」")
        page_text = block(body, "正文")
        prompt = block(body, "提示词")
        if page_text and len(re.sub(r"\s+", "", page_text)) < 40:
            errors.append(f"第{num}页正文信息不足，不能只写口号")
        if prompt and (
            len(re.sub(r"\s+", "", prompt)) < 100
            or "请生成" not in prompt
            or "本页意图" not in prompt
            or "画面" not in prompt
        ):
            errors.append(f"第{num}页提示词不是可直接交给 Image2 的完整中文自然语言提示词")
        visible = [line.removeprefix("- ").strip() for line in block(body, "正文").splitlines() if line.strip()]
        for item in visible:
            if len(re.sub(r"\s+", "", item)) > 24:
                warnings.append(f"第{num}页正文单行偏长：{item}")
        if OLD_ID.search(body):
            errors.append(f"第{num}页泄漏组件 ID")
        if not title:
            errors.append(f"第{num}页缺页面标题")
        screen = block(body, "上屏字")
        on_screen = []
        for raw in screen.splitlines():
            item = raw.strip().removeprefix("- ").strip()
            if not item or item.startswith("（"):
                continue
            if item.startswith("「") and item.endswith("」") and item.count("「") == 1:
                item = item[1:-1].strip()
            if item:
                on_screen.append(item)
        if not on_screen:
            errors.append(f"第{num}页缺「上屏字」")
        if prompt:
            errors.extend(
                mini.image_prompt_errors(
                    label=f"第{num}页提示词",
                    page_num=num,
                    visible=on_screen,
                    prompt=prompt,
                    course_title=course_title,
                )
            )
            style = mini.load_selected_style(args.outline.resolve().parents[1])
            if style:
                errors.extend(mini.style_lock_errors(f"第{num}页提示词", prompt, style))

    spoken = re.sub(r"^###\s*提示词\s*\n.*?(?=^##\s|^###\s|\Z)", "", text, flags=re.M | re.S)
    errors.extend(speakable.source_errors(spoken, speakable.course_dir_of(args.outline)))

    print(f"pages={len(pages)} errors={len(errors)} warnings={len(warnings)}")
    for item in errors:
        print("ERROR:", item)
    for item in warnings:
        print("WARN:", item)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
