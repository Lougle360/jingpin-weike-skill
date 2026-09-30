# -*- coding: utf-8 -*-
"""Hard checks for 精品微课 方案.md before the plan gate.

Exit 1 when any error. Warnings do not block.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402
import speakable  # noqa: E402

EVAL_KEYS = ("课程类型", "以前发过没有", "能不能写", "已有篇目")
OUTPUT_KEYS = ("内容稿字数", "视频时长", "停顿秒数", "PPT页数", "下游产品")
STRUCTURES = ("金字塔", "FABE", "四段式", "五问式", "ERTA", "三幕剧")
TIEBREAK = ("FABE", "五问式", "四段式", "ERTA", "三幕剧", "金字塔")
SCORE_DIMS = ("带走", "状态", "产出", "情绪", "密度")
INTENT_KEYS = ("学员此刻", "主收获", "当堂产出", "情绪温度", "知识密度", "红线")
NOW = ("还没信", "已经要学", "卡住要改")
HARVESTS = (
    "值不值得用",
    "能复述一句",
    "能做一步",
    "改一个行为",
    "过一层情绪",
    "被故事翻过去",
    "搭出知识树",
)
OUTPUTS = ("一句话", "一次观察", "一个小练习", "一个小成品")
MOODS = ("冷静认知", "轻卷入", "高卷入")
DENSITIES = ("一个观点", "一套方法", "一层系统")
HAVE_WRITE = ("未发过", "邻近同题")
HAVE_ALL = ("未发过", "邻近同题", "同题已发")
NARRATIVES = ("正序", "体验先导")
OLD_ID = re.compile(r"\b(?:FW|TH|TOOL|SC|DL|EX)-[A-Za-z0-9-]*\d{2}\b")
DOT_ID = re.compile(
    r"\b(?:foundation|core|advanced)?\.?(?:concept|principle|viewpoint|misconception|"
    r"guideline|framework|rule|workflow|tool|solution|scene|case|analogy|story|boundary|"
    r"source|data|quote|paradigm)\.[a-z0-9-]{3,}\b"
)
VERDICT = re.compile(r"\*\*结论[：:]\s*(建议做|待选结构|建议回流)\*\*")
RANGE = re.compile(r"(\d+)\s*[～~\-–至]\s*(\d+)")
PAGE_COUNT = re.compile(r"(\d+)\s*页")
FATAL = re.compile(r"(注定会|必然会|一定会|已被科学证实|科学证明命理)")
PUNCT = str.maketrans("", "", "。，、；：,.;:「」“”‘’（）()《》！!？? ")
PLACEHOLDER = re.compile(
    r"^(一句话|若用了|相对路径|先对齐|2～3 句|主标题|300|能够$|按选定|至少 1|100～200|明确区间|明确页数)"
)


def norm(text: str) -> str:
    return text.translate(PUNCT)


def section_after(text: str, heading: str) -> str:
    pat = re.compile(rf"^## {re.escape(heading)}\s*$", re.M)
    m = pat.search(text)
    if not m:
        return ""
    rest = text[m.end() :]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def prose(block: str) -> str:
    lines: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("|") or line.startswith("#"):
            continue
        if line.startswith(">"):
            line = line.lstrip("> ").strip()
        if line.startswith("- "):
            line = line[2:].strip()
        lines.append(line)
    return "\n".join(lines).strip()


def two_col(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in block.splitlines():
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$", line)
        if not m:
            continue
        k, v = m.group(1).strip(), m.group(2).strip()
        if k in ("要素", "项", "---") or set(k) <= {"-", ":"}:
            continue
        out[k] = v
    return out


def parse_outline(block: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"\d{2}", cells[0]):
            continue
        rows.append({"page": cells[0], "task": cells[1], "landing": cells[2]})
    return rows


def judge_of(total: int) -> str:
    if total >= 22:
        return "主推"
    if total >= 16:
        return "能用"
    if total >= 10:
        return "能讲"
    return "劝退"


def parse_scores(block: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8 or cells[0] not in STRUCTURES:
            continue
        rows.append(
            {
                "name": cells[0],
                "dims": cells[1:6],
                "total": cells[6],
                "judge": cells[7],
            }
        )
    return rows


def check_intent(text: str, errors: list[str]) -> None:
    card = two_col(section_after(text, "意图卡"))
    if not card:
        errors.append("待选结构缺「意图卡」")
        return
    for key in INTENT_KEYS:
        val = card.get(key, "").strip()
        if not val:
            errors.append(f"意图卡缺「{key}」")
    now = card.get("学员此刻", "").strip()
    if now and now not in NOW:
        errors.append("意图卡「学员此刻」只能是 还没信 / 已经要学 / 卡住要改")
    main = card.get("主收获", "").strip()
    if main and main not in HARVESTS:
        errors.append("意图卡「主收获」不在规定选项里")
    sub = card.get("次收获", "").strip()
    if sub and sub not in HARVESTS:
        errors.append("意图卡「次收获」不在规定选项里")
    if sub and main and sub == main:
        errors.append("次收获不能与主收获相同")
    out = card.get("当堂产出", "").strip()
    if out and out not in OUTPUTS:
        errors.append("意图卡「当堂产出」不在规定选项里")
    mood = card.get("情绪温度", "").strip()
    if mood and mood not in MOODS:
        errors.append("意图卡「情绪温度」不在规定选项里")
    dens = card.get("知识密度", "").strip()
    if dens and dens not in DENSITIES:
        errors.append("意图卡「知识密度」不在规定选项里")


def check_scores(text: str, recs: list[dict[str, str]], errors: list[str]) -> None:
    scores = parse_scores(section_after(text, "适配度评分"))
    if not scores:
        errors.append("待选结构缺「适配度评分」")
        return
    names = [row["name"] for row in scores]
    missing = [name for name in STRUCTURES if name not in names]
    if missing:
        errors.append("适配度评分缺：" + "、".join(missing))
    if len(names) != len(set(names)):
        errors.append("适配度评分结构重复")

    parsed: list[dict[str, object]] = []
    for row in scores:
        dims: list[int] = []
        ok = True
        for i, raw in enumerate(row["dims"]):
            if not re.fullmatch(r"[0-5]", raw):
                errors.append(f"{row['name']} 的{SCORE_DIMS[i]}须是 0～5 的整数")
                ok = False
            else:
                dims.append(int(raw))
        total_raw = row["total"].strip()
        if not re.fullmatch(r"\d{1,2}", total_raw):
            errors.append(f"{row['name']} 缺总分")
            continue
        total = int(total_raw)
        if ok and total != sum(dims):
            errors.append(f"{row['name']} 总分 {total} 与五维之和 {sum(dims)} 不一致")
        expected = judge_of(total)
        judge = row["judge"].strip()
        if judge != expected:
            errors.append(
                f"{row['name']} 判断应为 {expected}（总分 {total}），现在是「{judge}」"
            )
        parsed.append({"name": row["name"], "total": total})

    if len(parsed) == 6 and recs:
        rank = sorted(
            parsed,
            key=lambda x: (-int(x["total"]), TIEBREAK.index(str(x["name"]))),
        )
        top = [str(x["name"]) for x in rank[:3]]
        rec_names = [rec["name"] for rec in recs]
        if rec_names != top:
            errors.append(
                "结构推荐须按总分前三：" + " / ".join(top) + "，现在是 " + " / ".join(rec_names)
            )


def parse_recs(block: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0] in ("#", "---") or set(cells[0]) <= {"-", ":"}:
            continue
        if not cells[0].isdigit():
            continue
        rows.append({"id": cells[0], "name": cells[1], "why": cells[2]})
    return rows


def leak(text: str) -> bool:
    return bool(OLD_ID.search(text) or DOT_ID.search(text))


def selected_structure(text: str) -> dict[str, str]:
    chosen = two_col(section_after(text, "选定结构"))
    labels = mini.labeled_fields(text)
    for key in ("结构", "叙事", "选定方式", "理由"):
        if not chosen.get(key, "").strip() and labels.get(key):
            chosen[key] = labels[key]
    return chosen


def section_body(text: str, heading: str) -> str:
    found = prose(section_after(text, heading))
    if found:
        return found
    return prose(mini.bullet_span(text, heading))


def goal_lines(block: str) -> list[str]:
    goals: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if re.match(r"^\d+[.、．]\s+\S", line):
            goals.append(line)
            continue
        if not line.startswith("- "):
            continue
        body = line[2:].strip()
        if not body or body.startswith("学习目标"):
            continue
        labeled = mini.LABEL_LINE.match(line)
        if labeled and labeled.group(1).strip().strip("*") != "能够":
            continue
        goals.append(line)
    return goals


def learning_goals(text: str) -> list[str]:
    found = goal_lines(section_after(text, "学习目标"))
    if found:
        return found
    return goal_lines(mini.bullet_span(text, "学习目标"))


def goal_checkable(line: str) -> bool:
    body = re.sub(r"^(?:[-*]\s+|\d+[.、．]\s+)", "", line.strip())
    return bool(re.search(r"能够|能(?!力)|完成|说出|说清|掌握|识别|判断|列出|建立|写出|避开|复述", body))


def finished_scale(text: str) -> dict[str, str]:
    table = two_col(section_after(text, "预计成品"))
    if all(table.get(key, "").strip() for key in OUTPUT_KEYS):
        return table
    labels = mini.labeled_fields(mini.bullet_span(text, "预计成品") or section_after(text, "预计成品"))
    for key in OUTPUT_KEYS:
        if not table.get(key, "").strip() and labels.get(key):
            table[key] = labels[key]
    return table


def leftover_quote(text: str) -> str:
    q = two_col(section_after(text, "带走金句")) or two_col(section_after(text, "主推金句"))
    body = q.get("金句", "").strip()
    if body and not PLACEHOLDER.search(body):
        return body
    return ""


def check_do(text: str, header: dict[str, str], errors: list[str]) -> None:
    if header.get("能不能写", "").strip() != "能":
        errors.append("建议做时「能不能写」必须是 能")
    if header.get("以前发过没有", "").strip() not in HAVE_WRITE:
        errors.append("建议做时以前发过没有必须是 未发过 或 邻近同题")
    existing = header.get("已有篇目", "").strip()
    if header.get("以前发过没有", "").strip() == "未发过" and existing not in ("", "无"):
        errors.append("未发过时已有篇目应写「无」")
    if header.get("以前发过没有", "").strip() == "邻近同题" and (not existing or existing == "无"):
        errors.append("邻近同题须写下已有篇目")

    pitch = prose(section_after(text, "主旨确认"))
    if not pitch or PLACEHOLDER.search(pitch):
        errors.append("缺「主旨确认」")

    sel = selected_structure(text)
    name = sel.get("结构", "").strip()
    if name not in STRUCTURES:
        errors.append("建议做必须选定六种结构之一")
    if sel.get("选定方式", "").strip() == "待选":
        errors.append("建议做时选定方式不能是 待选")
    narr = sel.get("叙事", "").strip()
    if narr not in NARRATIVES:
        errors.append("建议做必须写叙事：正序 或 体验先导")

    title = section_body(text, "课程标题")
    if not title or PLACEHOLDER.search(title) or "主标题" in title:
        errors.append("缺课程标题")

    intro = section_body(text, "课程引言")
    if len(norm(intro)) < 200:
        errors.append("课程引言太短，至少把处境、意象和路径写清")

    goals = learning_goals(text)
    if not 3 <= len(goals) <= 5:
        errors.append(f"学习目标须 3～5 条，现在 {len(goals)} 条")
    if goals and not all(goal_checkable(g) for g in goals):
        errors.append("学习目标须可检验：写成学员做完能够完成的事")

    modules = section_body(text, "核心内容模块")
    if not modules or PLACEHOLDER.search(modules) or len(norm(modules)) < 80:
        errors.append("缺核心内容模块")

    exercise = section_body(text, "练习与互动")
    if not exercise or PLACEHOLDER.search(exercise):
        errors.append("缺练习与互动")

    ending = section_body(text, "小结与过渡")
    if not ending or PLACEHOLDER.search(ending):
        errors.append("缺小结与过渡")

    disclaimer = section_body(text, "免责说明")
    if not disclaimer or PLACEHOLDER.search(disclaimer):
        errors.append("缺免责说明")

    if FATAL.search(section_body(text, "课程引言") + section_body(text, "核心内容模块")):
        errors.append("正文踩了宿命论或伪科学红线")

    output = finished_scale(text)
    for key in OUTPUT_KEYS:
        if not output.get(key, "").strip():
            errors.append(f"预计成品缺「{key}」")

    words = RANGE.search(output.get("内容稿字数", ""))
    duration_text = output.get("视频时长", "")
    duration = RANGE.search(duration_text)
    exact_minutes = re.fullmatch(r"\s*(\d+)\s*分钟\s*", duration_text or "")
    if not words:
        errors.append("内容稿字数要写明确区间，如 1800～2500 字")
    elif int(words.group(1)) >= int(words.group(2)):
        errors.append("口播字数区间无效")
    if duration:
        low, high = int(duration.group(1)), int(duration.group(2))
        if low >= high or low < 4 or high > 7:
            errors.append("视频时长须为 4～7 分钟内的有效区间")
    elif exact_minutes and 4 <= int(exact_minutes.group(1)) <= 7:
        pass
    elif exact_minutes:
        errors.append("视频时长须为 4～7 分钟内的有效区间")
    else:
        errors.append("视频时长要写明确区间，如 5～6 分钟")
    if not re.search(r"\d", output.get("停顿秒数", "")):
        errors.append("停顿秒数要写数字，没有课堂停顿写 0")
    pages = PAGE_COUNT.search(output.get("PPT页数", "")) or re.search(r"^(\d+)$", (output.get("PPT页数") or "").strip())
    if not pages:
        errors.append("PPT页数要写明确页数，如 7 页")
    else:
        page_count = int(pages.group(1))
        if not 5 <= page_count <= 12:
            errors.append("PPT页数须为 5～12 页")
        else:
            roster = mini.read_page_roster(text)
            if not roster:
                errors.append(f"缺页表。要正好 {page_count} 行，每行只写页码和这一页做的一件事。参考与说明不占页。")
            elif len(roster) != page_count:
                errors.append(f"页表 {len(roster)} 行，PPT页数是 {page_count}")
            else:
                for index, (num, task) in enumerate(roster, 1):
                    if num != f"{index:02d}":
                        errors.append(f"页表页码不连续：第 {index} 行写成 {num}")
                    if task.startswith("（") or len(re.sub(r"\s+", "", task)) < 4:
                        errors.append(f"页表第 {num} 页没有写这一页做的事")
                    if "参考与说明" in task:
                        errors.append(f"页表第 {num} 页把参考与说明算进了页数")

    if leftover_quote(text):
        errors.append("精品微课不写带走金句")


def check_pick(text: str, header: dict[str, str], errors: list[str]) -> int:
    if header.get("能不能写", "").strip() != "能":
        errors.append("待选结构时「能不能写」必须是 能")
    if header.get("以前发过没有", "").strip() not in HAVE_WRITE:
        errors.append("待选结构时以前发过没有必须是 未发过 或 邻近同题")

    check_intent(text, errors)
    recs = parse_recs(section_after(text, "结构推荐"))
    if len(recs) != 3:
        errors.append(f"待选结构要推荐 3 种，现在 {len(recs)} 种")
    names = []
    for rec in recs:
        if rec["name"] not in STRUCTURES:
            errors.append(f"推荐结构不在结构库：{rec['name']}")
        if not rec["why"] or PLACEHOLDER.search(rec["why"]) or len(rec["why"]) < 12:
            errors.append(f"推荐 {rec['name'] or rec['id']} 缺理由")
        names.append(rec["name"])
    if len(set(names)) != len(names):
        errors.append("推荐结构重复")
    check_scores(text, recs, errors)

    if prose(section_after(text, "核心内容模块")):
        errors.append("待选结构时不要抢写核心内容模块")
    if parse_outline(section_after(text, "内容稿大纲")):
        errors.append("待选结构时不要写内容稿大纲")
    if leftover_quote(text):
        errors.append("待选结构时不要写带走金句")
    return len(recs)


def check_return(text: str, header: dict[str, str], errors: list[str]) -> None:
    if header.get("能不能写", "").strip() != "停回流":
        errors.append("建议回流时「能不能写」必须是 停回流")
    if header.get("以前发过没有", "").strip() != "同题已发":
        errors.append("建议回流时以前发过没有必须是 同题已发")
    existing = header.get("已有篇目", "").strip()
    if not existing or existing == "无":
        errors.append("建议回流须写下已有篇目")
    reason = prose(section_after(text, "为什么不写"))
    if not reason or PLACEHOLDER.search(reason):
        errors.append("缺「为什么不写」")
    if parse_outline(section_after(text, "内容稿大纲")):
        errors.append("建议回流时不要写内容稿大纲")
    if leftover_quote(text):
        errors.append("建议回流时不要写带走金句")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()

    text = args.plan.read_text(encoding="utf-8")
    header = mini.read_table(args.plan)
    labels = mini.labeled_fields(text)
    for key in EVAL_KEYS:
        if not header.get(key) and labels.get(key):
            header[key] = labels[key]
    errors: list[str] = []
    warns: list[str] = []

    vm = VERDICT.search(text)
    if not vm:
        errors.append("文头缺「**结论：建议做**」「**结论：待选结构**」或「**结论：建议回流**」")
        verdict = ""
    else:
        verdict = vm.group(1)

    for key in EVAL_KEYS:
        if not header.get(key):
            errors.append(f"评估缺「{key}」")

    have = header.get("以前发过没有", "").strip()
    can = header.get("能不能写", "").strip()
    if have and have not in HAVE_ALL:
        errors.append(f"以前发过没有只能是 未发过 / 邻近同题 / 同题已发，现在是「{have}」")
    if can and can not in ("能", "停回流"):
        errors.append(f"能不能写只能是 能 / 停回流，现在是「{can}」")

    extra = 0
    blocked = have == "同题已发" or can == "停回流"
    if verdict == "建议做":
        if blocked:
            errors.append("同题已发时不准出「建议做」，应回流")
        check_do(text, header, errors)
    elif verdict == "待选结构":
        if blocked:
            errors.append("同题已发时不准出「待选结构」，应回流")
        extra = check_pick(text, header, errors)
    elif verdict == "建议回流":
        check_return(text, header, errors)
    elif blocked:
        errors.append("同题已发时结论必须是「建议回流」")

    if leak(text):
        errors.append("方案正文泄漏组件 ID")
    if verdict == "建议做":
        errors.extend(speakable.source_errors(text, speakable.course_dir_of(args.plan)))

    print(
        f"verdict={verdict or '-'} published={have or '-'} can={can or '-'} "
        f"extra={extra} errors={len(errors)} warnings={len(warns)}"
    )
    for e in errors:
        print("ERROR:", e)
    for w in warns:
        print("WARN:", w)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
