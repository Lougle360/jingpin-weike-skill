# -*- coding: utf-8 -*-
"""Generate 4 cover candidates from the 3 Chaoyun styles locked in the brand pack.

    python Skills/min-visual/scripts/gen_covers.py --title "一命二运三风水" --quote "一命二运三风水是顺口溜，不是施工单。" --yes
    python Skills/min-visual/scripts/gen_covers.py projects/<课名> --yes
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

COVERS = (
    ("1", "003", "极简杂志-浅", "ivory"),
    ("2", "003", "极简杂志-深", "ink"),
    ("3", "008", "梦幻水彩", "wash"),
    ("4", "038", "中式曲线", "curve"),
)


def style_lock(kind: str) -> str:
    return mini.style_lock_text(kind)


def prompt_for(title: str, quote: str, kind: str) -> str:
    return (
        f"生成一张16:9横版完整PPT成品页。{style_lock(kind)}。"
        "本页是课程封面，要让观众一眼读到课名。"
        f"画面只允许出现以下中文，不增字、不漏字、不改字：「{title}」" + (f"「{quote}」" if quote else "") + "。"
        "构图：课名是最大标题，必须用中文毛笔行楷来写；如有副句，靠近标题，用较小的端正行楷；一页一个视觉焦点。"
        "可用一件克制日常物件暗示课题，不要画人物、不要画命盘、不要画风水摆件、不要画Logo。"
        "将背景、图片、插画、图形、标题和正文直接整合成同一张页面图片，"
        "图片垫底，禁止把图片与文字拆开。"
        "不要额外文字、伪字、水印、商标、无关人物或陌生品牌。"
    )


def title_quote_from_course(course: Path) -> tuple[str, str]:
    path = course / "10-内容稿" / "内容稿.md"
    if not path.is_file():
        return "", ""
    text = path.read_text(encoding="utf-8")
    title_hit = re.search(r"^#\s+内容稿[：:]\s*(.+?)\s*$", text, re.M)
    title = title_hit.group(1).strip() if title_hit else ""
    header = mini.read_table(path)
    subtitle = header.get("课程目标", "").strip()
    return title, subtitle


def out_dir_for(course: Path | None, dest: Path | None) -> Path:
    if dest:
        return dest
    if course:
        return course / "20-页图"
    return mini.brand_dir() / "模板" / "封面预览"


def generate(out_dir: Path, title: str, quote: str, force: bool) -> list[Path]:
    kie = mini.skill_root() / "scripts" / "kie" / "kie.py"
    mini.load_key("KIE_API_KEY")
    prompt_dir = out_dir / "_cover_prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    for num, catalog, name, kind in COVERS:
        prompt_path = prompt_dir / f"{num}-{name}.txt"
        prompt_path.write_text(prompt_for(title, quote, kind), encoding="utf-8")
        out = out_dir / f"封面候选-{num}.png"
        if out.is_file() and out.stat().st_size > 100_000 and not force:
            print("skip", out.name)
            results.append(out)
            continue
        prompt = prompt_path.read_text(encoding="utf-8")
        model = "gpt-image-2-text-to-image"
        ok = False
        for attempt in range(1, 3):
            cmd = [
                sys.executable,
                str(kie),
                "image",
                "--model",
                model,
                "--prompt",
                prompt,
                "--aspect",
                "16:9",
                "--quality",
                "2K",
                "--wait",
                "--timeout",
                "900",
                "--out",
                str(out),
            ]
            print("GEN", out.name, catalog, name, f"model={model}", f"try={attempt}", flush=True)
            if subprocess.run(cmd).returncode == 0 and out.is_file() and out.stat().st_size > 10_000:
                ok = True
                break
            print("RETRY", out.name, flush=True)
        if not ok:
            raise SystemExit(f"FAIL {out.name}")
        results.append(out)
    return results


def write_index(out_dir: Path, title: str, quote: str) -> None:
    lines = [
        f"# 四种封面",
        "",
        f"- 课名：{title}",
        f"- 副句：{quote}" if quote else "- 副句：无",
        "- 同一文案，四套气质。人选一张，内页跟选定风格走。",
        "",
        "| 候选 | 模板 | 文件 |",
        "|---|---|---|",
    ]
    for num, catalog, name, _kind in COVERS:
        lines.append(f"| {num} | {catalog} {name} | `封面候选-{num}.png` |")
    (out_dir / "四种封面.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_dir", nargs="?", type=Path)
    parser.add_argument("--title", default=None)
    parser.add_argument("--quote", default=None)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    course = args.course_dir.resolve() if args.course_dir else None
    title = (args.title or "").strip()
    quote = (args.quote or "").strip()
    if course and (not title or not quote):
        t, q = title_quote_from_course(course)
        title = title or t
        quote = quote or q
    if not title:
        raise SystemExit("给 --title，或先写内容稿再接到课程目录")
    if not args.yes:
        raise SystemExit("将付费出 4 张封面。确认后加 --yes。")

    dest = out_dir_for(course, args.out.resolve() if args.out else None)
    dest.mkdir(parents=True, exist_ok=True)
    generate(dest, title, quote, args.force)
    write_index(dest, title, quote)
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
