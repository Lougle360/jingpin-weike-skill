# -*- coding: utf-8 -*-
"""Check 20-页图/pages against 20-页图/PPT大纲.md: count, numbering, size."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_dir", type=Path)
    args = parser.parse_args()

    doc = mini.parse_script(args.course_dir / "20-页图" / "PPT大纲.md")
    pages_dir = args.course_dir / "20-页图" / "pages"
    files = sorted(pages_dir.glob("*.png"), key=lambda p: p.name.casefold())
    errors: list[str] = []

    if len(files) != len(doc.pages):
        errors.append(f"页图 {len(files)} 张，PPT大纲 {len(doc.pages)} 页")
    for i, f in enumerate(files, 1):
        if not f.name[:2].isdigit() or int(f.name[:2]) != i:
            errors.append(f"文件名页号不对: {f.name} 应以 {i:02d} 开头")
    try:
        from PIL import Image

        for f in files:
            with Image.open(f) as im:
                w, h = im.size
            if abs(w / h - 16 / 9) > 0.01:
                errors.append(f"{f.name} 不是 16:9 ({w}x{h})")
            elif w < 1600:
                errors.append(f"{f.name} 太小 ({w}x{h})")
    except ImportError:
        print("WARN: PIL missing, size check skipped")

    print(f"pages={len(files)} script_pages={len(doc.pages)} errors={len(errors)}")
    for e in errors:
        print("ERROR:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
