# -*- coding: utf-8 -*-
"""Mechanical checks for every text-to-image prompt before paid generation."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

TITLE = re.compile(r"^#\s+PPT\s*大纲：\s*(.+?)\s*$", re.M)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_dir", type=Path)
    args = parser.parse_args()

    course = args.course_dir.resolve()
    script_path = course / "20-页图" / "PPT大纲.md"
    script_text = script_path.read_text(encoding="utf-8")
    doc = mini.parse_script(script_path)
    title_hit = TITLE.search(script_text)
    title = title_hit.group(1).strip() if title_hit else ""
    if not title and doc.pages and doc.pages[0].visible:
        title = doc.pages[0].visible[0].strip()
    errors: list[str] = []

    if not title:
        errors.append("PPT大纲第01页缺课程标题")

    prompt_dir = course / "20-页图" / "_prompts"
    prompt_files = sorted(prompt_dir.glob("*.txt"))
    expected_names = [f"{page.num}.txt" for page in doc.pages]
    actual_names = [path.name for path in prompt_files]
    if actual_names != expected_names:
        errors.append(f"提示词文件应为 {expected_names}，实际为 {actual_names}")

    for page in doc.pages:
        path = prompt_dir / f"{page.num}.txt"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        errors.extend(
            mini.image_prompt_errors(
                label=path.name,
                page_num=page.num,
                visible=page.visible,
                prompt=text,
                course_title=title,
            )
        )

    print(f"prompts={len(prompt_files)} pages={len(doc.pages)} errors={len(errors)}")
    for error in errors:
        print("ERROR:", error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
