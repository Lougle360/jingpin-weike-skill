# -*- coding: utf-8 -*-
"""Create projects/<课名>/ skeleton and _state.md."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

DIRS = ["10-内容稿", "20-页图/pages", "30-口播字幕", "40-成片"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course", help="课名，也是目录名")
    parser.add_argument("--goal", default="", help="课程目标")
    parser.add_argument("--folk", default="", help="兼容旧参数；等价于 --goal")
    parser.add_argument("--audience", default="零基础成年学员")
    parser.add_argument("--format", default="图文讲义", dest="lesson_format")
    parser.add_argument("--structure", default="", help="金字塔/FABE/四段式/五问式/ERTA/三幕剧/你来定；空则先荐结构")
    parser.add_argument("--kb", default="", help="只读知识库根目录；不传则按课名/目标自动路由")
    parser.add_argument("--brand", default="谷子")
    args = parser.parse_args()

    goal = (args.goal or args.folk).strip()
    if not goal:
        raise SystemExit("请用 --goal 提供课程目标")
    kb = args.kb.strip() or mini.route_kb(args.course, goal)

    brand = mini.brand_dir(args.brand)
    if not (brand / "品牌包.md").is_file():
        raise SystemExit(f"品牌包不存在: {brand}")

    root = mini.work_root() / "projects" / args.course
    if (root / "_state.md").exists():
        raise SystemExit(f"已存在: {root / '_state.md'}")
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)

    template = (
        mini.skill_file("精品微课", "templates", "_state.md")
    ).read_text(encoding="utf-8")
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    text = (
        template.replace("{{course}}", args.course)
        .replace("{{goal}}", goal)
        .replace("{{audience}}", args.audience)
        .replace("{{format}}", args.lesson_format)
        .replace("{{structure}}", args.structure)
        .replace("{{brand}}", args.brand)
        .replace("{{kb}}", kb)
        .replace("{{created}}", now)
    )
    (root / "_state.md").write_text(text, encoding="utf-8")

    plan_name = "待选结构.md" if not args.structure or args.structure == "待选" else "方案.md"
    plan_tpl = mini.skill_file("min-plan", "templates", plan_name)
    if plan_tpl.is_file():
        dest = root / "10-内容稿" / "方案.md"
        body = plan_tpl.read_text(encoding="utf-8")
        body = (
            body            .replace("<课名>", args.course)
            .replace("<课程目标>", goal)
            .replace("<民间话>", goal)
        )
        dest.write_text(body, encoding="utf-8")

    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
