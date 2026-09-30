# -*- coding: utf-8 -*-
"""Hard checks for 知识校准简报.

Exit 1 when any error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED = (
    "第二部分｜本轮知识校准简报",
    "第三部分｜待人工审核知识简报",
)
BANNED_IN_COURSE = ("【修改】", "【错误】", "【待审核】", "原文：", "修改后：")
OLD_ID = re.compile(r"\b(?:FW|TH|TOOL|SC|DL|EX)-[A-Za-z0-9-]*\d{2}\b")
DOT_ID = re.compile(
    r"\b(?:foundation|core|advanced)?\.?(?:concept|principle|viewpoint|misconception|"
    r"guideline|framework|rule|workflow|tool|solution|scene|case|analogy|story|boundary|"
    r"source|data|quote|paradigm)\.[a-z0-9-]{3,}\b"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    if not args.report.is_file():
        print(f"errors=1 warnings=0")
        print("ERROR: 知识校准简报不存在")
        return 1

    text = args.report.read_text(encoding="utf-8")
    for heading in REQUIRED:
        if heading not in text:
            errors.append(f"简报缺「{heading}」")

    part2 = "第二部分" in text and "无" in text
    if "修正01" not in text and not part2:
        if "第二部分｜本轮知识校准简报" in text:
            after = text.split("第二部分｜本轮知识校准简报", 1)[1]
            before3 = after.split("第三部分", 1)[0] if "第三部分" in after else after
            if not before3.strip():
                errors.append("第二部分不能空白，无修正时写「无」")

    course = args.report.parent / "内容稿.md"
    draft = args.report.parent / "内容稿草稿.md"
    if not course.is_file():
        errors.append("校正后的正稿不存在：内容稿.md。校正结果必须写成正稿，不能只交简报")
    if draft.is_file() and not draft.read_text(encoding="utf-8").strip():
        errors.append("内容稿草稿.md 是空的。草稿要按方案写完，再做知识库校正")
    if course.is_file():
        body = course.read_text(encoding="utf-8")
        for token in BANNED_IN_COURSE:
            if token in body:
                errors.append(f"{course.name} 残留审校痕迹：{token}")
        if OLD_ID.search(body) or DOT_ID.search(body):
            errors.append(f"{course.name} 泄漏组件 ID")

    print(f"errors={len(errors)} warnings=0")
    for e in errors:
        print("ERROR:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
