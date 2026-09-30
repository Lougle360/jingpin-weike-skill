# -*- coding: utf-8 -*-
"""Hard checks for the complete written content manuscript."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402
import speakable  # noqa: E402

REQUIRED = ("课名", "课程目标", "学员", "内容定位", "不讲")
OLD_ID = re.compile(r"\b(?:FW|TH|TOOL|SC|DL|EX)-[A-Za-z0-9-]*\d{2}\b")
DOT_ID = re.compile(
    r"\b(?:foundation|core|advanced)?\.?(?:concept|principle|viewpoint|misconception|"
    r"guideline|framework|rule|workflow|tool|solution|scene|case|analogy|story|boundary|"
    r"source|data|quote|paradigm)\.[a-z0-9-]{3,}\b"
)
FATAL = re.compile(r"(注定会|必然会|一定会|已被科学证实|科学证明命理)")
PAGE_FORM = re.compile(r"^##\s*第\d{2}页｜|^###\s*(?:上屏字|口播)\s*$|页任务[：:]", re.M)
PLATFORM_CALL = re.compile(r"(点赞|关注我|点个关注|评论区扣|购买链接|私信领取)")
PRODUCTION_LANGUAGE = re.compile(r"(这一页|下一页|第\d{1,3}页|停(?:顿)?\s*\d+\s*秒|上屏字|逐页口播|画面建议)")
EVIDENCE_FORM = re.compile(r"(案例|示例|例如|比如|教学假设|应用推演|完整演示)")
ACTION_FORM = re.compile(r"(第一步|步骤|方法|检查清单|行动清单|可以依次|如何|怎么做)")
EXERCISE_FORM = re.compile(r"(练习|填空|当堂|自检清单|检查清单|行动清单)")


def section(text: str, heading: str) -> str:
    hit = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.M)
    if not hit:
        return ""
    rest = text[hit.end() :]
    nxt = re.search(r"^##\s+", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def plain_chars(text: str) -> int:
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    body = re.sub(r"^#{1,6}\s+.*$", "", body, flags=re.M)
    body = re.sub(r"^\|.*\|$", "", body, flags=re.M)
    return len(re.sub(r"\s+", "", body))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--min-chars", type=int, default=1500)
    parser.add_argument(
        "--manual-edit",
        action="store_true",
        help="审核页上手动改过的正稿不卡字数",
    )
    args = parser.parse_args()

    text = args.script.read_text(encoding="utf-8")
    header = mini.read_table(args.script)
    errors: list[str] = []
    warnings: list[str] = []

    if not re.search(r"^#\s+内容稿：\S+", text, re.M):
        errors.append("文头须为「# 内容稿：<课名>」")
    for key in REQUIRED:
        if not header.get(key, "").strip():
            errors.append(f"文头缺「{key}」")

    plan_path = args.script.parent / "方案.md"
    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    roster = mini.read_page_roster(plan_text) if plan_text else []
    page_heads = re.findall(r"^##\s*第(\d{2})页｜(.+?)\s*$", text, re.M)
    if roster and page_heads:
        expected = [(num, task) for num, task in roster]
        if page_heads != expected:
            errors.append("内容稿标题必须和方案页表逐字一致，不能增页、删页或改任务")
            errors.append("页表：" + "；".join(f"第{num}页｜{task}" for num, task in expected))
        prose_text = "\n".join(line for line in text.splitlines() if not re.match(r"^##\s*第\d{2}页｜", line))
        if PAGE_FORM.search(prose_text):
            errors.append("内容稿正文不要写上屏字、口播或页任务；这些属于 PPT 大纲和口播稿")
        if PRODUCTION_LANGUAGE.search(prose_text):
            errors.append("内容稿正文不要写停顿、上屏或制作说明")
    else:
        for heading in ("引言", "结语", "参考与说明"):
            if len(re.sub(r"\s+", "", section(text, heading))) < 40:
                errors.append(f"「{heading}」缺失或内容过短")
        if PAGE_FORM.search(text):
            errors.append("内容稿不得分页、写页任务、上屏字或逐页口播；这些属于 PPT 大纲和口播稿")
        if PRODUCTION_LANGUAGE.search(text):
            errors.append("内容稿含页面、停顿或制作语言，不能直接作为文章发布")

    h2 = re.findall(r"^##\s+(.+?)\s*$", text, re.M)
    body_sections = [name for name in h2 if name not in {"引言", "常见误区", "结语", "参考与说明"} and not re.match(r"第\d{2}页｜", name)]
    if roster and page_heads:
        body_sections = [title for _num, title in page_heads]
    if len(body_sections) < 3:
        errors.append(f"正文至少需要 3 个完整章节，现在 {len(body_sections)} 个")
    paragraphs = [
        item.strip()
        for item in re.split(r"\n\s*\n", text)
        if not item.lstrip().startswith(("#", "|", "-", ">", "```"))
        and len(re.sub(r"\s+", "", item)) >= 60
    ]
    if len(paragraphs) < 6:
        errors.append(f"完整文章至少需要 6 个有实质内容的段落，现在 {len(paragraphs)} 个")

    chars = plain_chars(text)
    if chars < args.min_chars and not args.manual_edit:
        errors.append(f"完整内容稿至少 {args.min_chars} 字符，现在 {chars}")
    if not EVIDENCE_FORM.search(text):
        errors.append("内容稿缺具体案例、教学示例、事实论证或完整应用推演")
    title = re.search(r"^#\s+内容稿：(.+?)\s*$", text, re.M)
    title_text = title.group(1) if title else ""
    if re.search(r"(教你|方法|步骤|清单|怎么|如何)", title_text) and not ACTION_FORM.search(text):
        errors.append("标题承诺方法或步骤，但正文没有可执行的方法、步骤或检查清单")

    if plan_text:
        exercise = mini.section_text(plan_text, "练习与互动")
        if exercise.strip() and not EXERCISE_FORM.search(text):
            errors.append("方案有「练习与互动」，内容稿必须写出可执行的练习、填空或清单")

    if OLD_ID.search(text) or DOT_ID.search(text):
        errors.append("内容稿泄漏组件 ID")
    if FATAL.search(text):
        errors.append("内容稿含宿命论或伪科学绝对表述")
    if PLATFORM_CALL.search(text):
        errors.append("内容母稿不得写平台专属关注、评论、购买话术")
    errors.extend(speakable.source_errors(text, speakable.course_dir_of(args.script)))

    print(f"sections={len(body_sections)} chars={chars} errors={len(errors)} warnings={len(warnings)}")
    for item in errors:
        print("ERROR:", item)
    for item in warnings:
        print("WARN:", item)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
