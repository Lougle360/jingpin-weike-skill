# -*- coding: utf-8 -*-
"""Generate full-page images through tools/kie/kie.py (gpt-image-2 text-to-image).

    gen_page.py <course_dir> <NN> [--force]
    gen_page.py <course_dir> --all [--yes] [--force]

Prompts are read from <course_dir>/20-页图/_prompts/NN.txt. Style comes from
选定模板.json as a text lock only. Do not attach 选定封面.png or vendor
国潮 references — those switch Kie to image-to-image and flatten the page.

Raw output goes to 20-页图/pages-raw/NN-<页名>.png (no logo). Then run stamp_pages.py.
Paid call: --all needs --yes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

KIE = mini.skill_root() / "scripts" / "kie" / "kie.py"
QA_PROMPTS = Path(__file__).with_name("qa_prompts.py")


def require_style(course: Path) -> mini.SelectedStyle:
    style = mini.load_selected_style(course)
    if style is None:
        raise SystemExit("未选定模板，禁止出内页。")
    return style


def refs_for(course: Path) -> list[Path]:
    require_style(course)
    return []


def gen_one(course: Path, page: mini.Page, force: bool) -> Path:
    prompt_file = course / "20-页图" / "_prompts" / f"{page.num}.txt"
    if not prompt_file.is_file():
        raise SystemExit(f"缺提示词: {prompt_file}")
    out_dir = course / "20-页图" / "pages-raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{page.num}-{page.title}.png"
    if out.is_file() and out.stat().st_size > 100_000 and not force:
        print("skip", out.name)
        return out
    style = require_style(course)
    prompt = mini.apply_style_lock(prompt_file.read_text(encoding="utf-8"), style)
    model = "gpt-image-2-text-to-image"
    print("GEN", out.name, f"style={style.catalog}-{style.variant}", "t2i", flush=True)
    for attempt in range(1, 3):
        cmd = [
            sys.executable, str(KIE), "image",
            "--model", model,
            "--prompt", prompt,
            "--aspect", "16:9", "--quality", "2K", "--wait", "--timeout", "900",
            "--out", str(out),
        ]
        print("try", attempt, model, flush=True)
        if subprocess.run(cmd).returncode == 0 and out.is_file() and out.stat().st_size > 10_000:
            return out
    raise SystemExit(f"FAIL {out.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_dir", type=Path)
    parser.add_argument("page", nargs="?", default="", help="页号，如 06")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--yes", action="store_true", help="确认付费批量出图")
    parser.add_argument("--layout", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--typo", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--force", action="store_true", help="已有图也重出")
    args = parser.parse_args()

    course = args.course_dir.resolve()
    doc = mini.parse_script(course / "20-页图" / "PPT大纲.md")
    qa = subprocess.run([sys.executable, str(QA_PROMPTS), str(course)])
    if qa.returncode != 0:
        raise SystemExit("文生图提示词审核未通过，禁止付费出图。")
    mini.load_key("KIE_API_KEY")  # fail early, never printed

    if args.all:
        if not args.yes:
            raise SystemExit(f"将付费出图 {len(doc.pages)} 页。确认后加 --yes。")
        for p in doc.pages:
            gen_one(course, p, args.force)
        return 0

    if not args.page:
        raise SystemExit("给页号，或 --all")
    num = args.page.zfill(2)
    match = [p for p in doc.pages if p.num == num]
    if not match:
        raise SystemExit(f"PPT大纲没有第{num}页")
    gen_one(course, match[0], args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
