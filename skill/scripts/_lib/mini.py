# -*- coding: utf-8 -*-
"""Shared helpers for 精品微课 scripts.

- parse 内容稿.md into header fields + pages
- read two-column markdown tables (品牌包 / 素材库)
- ffprobe / ffmpeg wrappers
- .env key loading

Import from any Skill script via:

    import sys; from pathlib import Path
    sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
    import mini
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------- paths


def skill_root() -> Path:
    """Read-only root shipped with the code.

    Source repo:  Skills/_lib/mini.py  -> repo root
    Skill bundle: scripts/_lib/mini.py -> bundle root
    """
    return Path(__file__).resolve().parents[2]


def work_root() -> Path:
    """Writable root: courses, knowledge bases, assets and keys live here.

    In the source repo it is the repo itself. Installed as a skill bundle the
    code sits read-only under the host app, so work lands in MINI_WORK_DIR or
    ~/精品微课.
    """
    configured = os.environ.get("MINI_WORK_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    here = skill_root()
    if (here / "projects").is_dir() or (here / "config" / "知识库.md").is_file():
        return here
    return Path.home() / "精品微课"


# 旧名，脚本里仍在用；语义等同 work_root
repo_root = work_root


def _first_existing(*candidates: Path) -> Path:
    """Prefer the customer's copy, fall back to the one shipped in the bundle."""
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def brand_dir(name: str = "谷子") -> Path:
    return _first_existing(
        work_root() / "config" / "品牌包" / name,
        skill_root() / "assets" / "品牌包" / name,
    )


def config_file(name: str) -> Path:
    return _first_existing(
        work_root() / "config" / name,
        skill_root() / "assets" / "工作目录模板" / "config" / name,
    )


def skill_file(*parts: str) -> Path:
    """A read-only file shipped with the code, wherever the layout puts it."""
    return _first_existing(
        skill_root() / "references" / Path(*parts),
        skill_root() / "Skills" / Path(*parts),
    )


def resolve_path(value: str) -> Path:
    """Absolute stays absolute; relative is resolved against the work root."""
    text = value.strip()
    # strip trailing notes like "（相对仓库根）"
    text = re.split(r"[（(]", text, 1)[0].strip()
    p = Path(text)
    return p if p.is_absolute() else (work_root() / p)


def env_file() -> Path:
    return work_root() / ".env"


KB_BAZI = "knowledge/z5fu-bazi"
KB_QIMEN = "knowledge/yizheng-qimen"
_QIMEN_MARKERS = (
    "奇门",
    "遁甲",
    "qimen",
    "dunjia",
    "八门",
    "九星",
    "八神",
    "值符",
    "值使",
    "阳遁",
    "阴遁",
    "三奇",
    "六仪",
    "天盘",
    "地盘",
    "置闰",
    "拆补",
    "门迫",
    "击刑",
    "九宫",
    "落宫",
    "星门",
    "伏吟",
    "反吟",
)


_KB_MARKER_SPLIT = re.compile(r"[、,，/；;\s]+")


@dataclass
class KnowledgeBase:
    name: str
    path: str
    markers: tuple[str, ...] = ()
    is_default: bool = False


def knowledge_bases() -> list[KnowledgeBase]:
    """Read config/知识库.md. Empty list when the table is missing."""
    table = config_file("知识库.md")
    if not table.is_file():
        return []
    out: list[KnowledgeBase] = []
    for cells in read_table_rows(table, first_table_only=True):
        if len(cells) < 2 or cells[0] in ("库名", "库") or not cells[1]:
            continue
        raw = cells[2] if len(cells) > 2 else ""
        markers = tuple(m for m in _KB_MARKER_SPLIT.split(raw) if m and m != "默认")
        out.append(KnowledgeBase(cells[0], cells[1], markers, "默认" in raw))
    return out


def is_qimen_course(*texts: str) -> bool:
    blob = " ".join(t or "" for t in texts).casefold()
    return any(marker.casefold() in blob for marker in _QIMEN_MARKERS)


def route_kb(*texts: str) -> str:
    """Pick the read-only knowledge base from course name / goal text.

    Driven by config/知识库.md; falls back to the built-in 八字 / 奇门 split
    when that table is missing.
    """
    bases = knowledge_bases()
    if not bases:
        return KB_QIMEN if is_qimen_course(*texts) else KB_BAZI
    blob = " ".join(t or "" for t in texts).casefold()
    for kb in bases:
        if any(m.casefold() in blob for m in kb.markers):
            return kb.path
    for kb in bases:
        if kb.is_default:
            return kb.path
    return bases[0].path


def ffmpeg_bin(name: str) -> str:
    """Prefer bundled tools/ffmpeg/bin/<name>.exe, else rely on PATH."""
    for candidate in (
        repo_root() / "tools" / "ffmpeg" / "bin" / f"{name}.exe",
        repo_root() / "tools" / "ffmpeg" / f"{name}.exe",
        repo_root() / "tools" / "ffmpeg" / "bin" / name,
    ):
        if candidate.is_file():
            return str(candidate)
    return name


# ---------------------------------------------------------------- tables

# strictly two columns; rows with more cells are ignored by read_table / header parsing
_CELL = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$")


def _strip_code(value: str) -> str:
    """`code` -> code. `code`（note） -> code. Plain text unchanged."""
    value = value.strip()
    if value.startswith("`"):
        end = value.find("`", 1)
        if end > 0:
            return value[1:end].strip()
    return value


def read_table(path: Path) -> dict[str, str]:
    """Read every two-column `| 字段 | 值 |` row in a markdown file into a dict.

    First column is the key. Header / separator rows are skipped.
    Later duplicate keys overwrite earlier ones.
    """
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = _CELL.match(raw)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if set(key) <= set("-: ") or key in ("字段", "用途", "表", "层", "列", "行名"):
            continue
        out[_strip_code(key)] = _strip_code(value)
    return out


def read_table_rows(path: Path, first_table_only: bool = False) -> list[list[str]]:
    """Read markdown table rows (any column count) as lists of cells.

    first_table_only stops at the end of the first table, so a doc can show
    further tables as examples without them being read as data.
    """
    rows: list[list[str]] = []
    started = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            if started and first_table_only:
                break
            continue
        started = True
        cells = [_strip_code(c) for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    return rows


def asset_root() -> Path:
    table = read_table(config_file("素材库.md"))
    root = table.get("素材根")
    if not root:
        raise SystemExit("config/素材库.md 缺「素材根」")
    return resolve_path(root)


# ---------------------------------------------------------------- 内容稿

PAGE_HEAD = re.compile(r"^##\s*第(\d{2})页｜(.+?)\s*$")
SPEECH_HEAD = re.compile(r"^###\s*口播\s*$")
VISIBLE_HEAD = re.compile(r"^###\s*上屏字\s*$")
BODY_HEAD = re.compile(r"^###\s*正文\s*$")
PROMPT_HEAD = re.compile(r"^###\s*提示词\s*$")
BULLET = re.compile(r"^-\s*([^：:]+)[：:]\s*(.*)$")


@dataclass
class Page:
    num: str
    title: str
    task: str = ""
    visible: list[str] = field(default_factory=list)
    speech: str = ""
    prompt: str = ""

    @property
    def index(self) -> int:
        return int(self.num)


@dataclass
class Script:
    path: Path
    header: dict[str, str]
    pages: list[Page]

    @property
    def title(self) -> str:
        return self.header.get("课名", self.path.stem)

    @property
    def quote(self) -> str:
        return self.header.get("金句", "")

    def speech_chars(self) -> int:
        return sum(len(re.sub(r"\s+", "", p.speech)) for p in self.pages)


def parse_script(path: Path) -> Script:
    """Parse 内容稿.md.

    Expected layout (see Skills/min-script/templates/内容稿.md):

        # 内容稿：<课名>
        | 字段 | 值 |
        ...
        ## 第01页｜<页名>
        - 页任务：...
        ### 上屏字
        - 一行
        ### 口播
        <paragraphs>
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    header: dict[str, str] = {}
    pages: list[Page] = []
    cur: Page | None = None
    mode = ""  # "", "visible", "speech", "prompt"
    in_pages = False

    for raw in lines:
        line = raw.rstrip()
        m = PAGE_HEAD.match(line)
        if m:
            in_pages = True
            cur = Page(num=m.group(1), title=m.group(2).strip())
            pages.append(cur)
            mode = ""
            continue
        if not in_pages:
            cm = _CELL.match(line)
            if cm and not set(cm.group(1)) <= set("-: "):
                header[_strip_code(cm.group(1))] = _strip_code(cm.group(2))
            continue
        if cur is None:
            continue
        if line.startswith("## "):
            # a non-page level-2 heading ends page parsing
            cur = None
            mode = ""
            continue
        if VISIBLE_HEAD.match(line):
            mode = "visible"
            continue
        if BODY_HEAD.match(line):
            mode = "visible" if not cur.visible else "body"
            continue
        if PROMPT_HEAD.match(line):
            mode = "prompt"
            continue
        if SPEECH_HEAD.match(line):
            mode = "speech"
            continue
        if line.startswith("### "):
            mode = ""
            continue
        if mode == "":
            bm = BULLET.match(line)
            if bm and bm.group(1).strip() == "页任务":
                cur.task = bm.group(2).strip()
            continue
        if mode == "visible":
            if line.strip():
                cur.visible.append(line[2:].strip() if line.startswith("- ") else line.strip())
            continue
        if mode == "speech":
            if line.strip():
                cur.speech = (cur.speech + line.strip()) if cur.speech else line.strip()
            continue
        if mode == "prompt":
            if line.strip():
                cur.prompt = f"{cur.prompt}\n{line.strip()}".strip()
            continue

    header.pop("字段", None)
    goal = header.get("课程目标") or header.get("民间话") or ""
    if goal:
        header["课程目标"] = goal
        header["民间话"] = goal
    return Script(path=path, header=header, pages=pages)


# ---------------------------------------------------------------- media

def probe_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            ffmpeg_bin("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    data = json.loads(result.stdout.decode("utf-8", errors="replace"))
    return float(data["format"]["duration"])


def run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a command; a leading 'ffmpeg' / 'ffprobe' is swapped for the bundled binary if present."""
    if cmd and cmd[0] in ("ffmpeg", "ffprobe"):
        cmd = [ffmpeg_bin(cmd[0]), *cmd[1:]]
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None)


# ---------------------------------------------------------------- durations json

SECTION_HEAD = re.compile(r"^##\s+(.+?)\s*$", re.M)
TWO_COL = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$")
DURATION_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[～~\-–至]\s*(\d+(?:\.\d+)?)\s*分")
NUMBER = re.compile(r"(\d+(?:\.\d+)?)")
LABEL_LINE = re.compile(
    r"^(?:[-*]\s+|\d+[.、．]\s+)?(?:\*\*)?([^*\n：:]{1,24}?)[：:]\s*(.*?)(?:\*\*)?\s*$"
)


def section_text(text: str, heading: str) -> str:
    hit = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.M)
    if not hit:
        return ""
    rest = text[hit.end() :]
    nxt = re.search(r"^##\s+", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def labeled_fields(text: str) -> dict[str, str]:
    """Read **字段：值** and `- 字段：值` lines. The first value for a key wins."""
    found: dict[str, str] = {}
    for raw in text.splitlines():
        match = LABEL_LINE.match(raw.strip())
        if not match:
            continue
        key = match.group(1).strip().strip("*")
        value = match.group(2).strip().strip("*")
        if key and value and key not in found:
            found[key] = value
    return found


def bullet_span(text: str, key: str) -> str:
    """Text of a labeled bullet, including indented lines under it."""
    lines = text.splitlines()
    start = None
    for index, raw in enumerate(lines):
        match = LABEL_LINE.match(raw.strip())
        if match and match.group(1).strip().strip("*") == key:
            start = index
            break
    if start is None:
        return ""
    base = len(lines[start]) - len(lines[start].lstrip(" \t"))
    chunk = [lines[start]]
    for raw in lines[start + 1 :]:
        if not raw.strip():
            chunk.append(raw)
            continue
        indent = len(raw) - len(raw.lstrip(" \t"))
        stripped = raw.strip()
        if indent <= base and (stripped.startswith("## ") or LABEL_LINE.match(stripped)):
            break
        chunk.append(raw)
    return "\n".join(chunk)


def read_section_table(text: str, heading: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in section_text(text, heading).splitlines():
        match = TWO_COL.match(raw.strip())
        if not match:
            continue
        key, value = match.group(1).strip(), match.group(2).strip()
        if key in {"项", "字段", "要素"} or set(key) <= set("-:"):
            continue
        out[key] = value
    return out


def read_page_roster(text: str) -> list[tuple[str, str]]:
    """页表是唯一的页数合同。每行是页码和这一页只做的一件事。参考与说明不在表里。"""
    block = section_text(text, "页表") or section_text(text, "内容稿大纲")
    rows: list[tuple[str, str]] = []
    for raw in block.splitlines():
        cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0].isdigit():
            continue
        task = cells[1].strip()
        if not task or set(task) <= set("-:"):
            continue
        rows.append((f"{int(cells[0]):02d}", task))
    return rows


QUOTED_COPY = re.compile(r"「([^」]+)」")
PROMPT_TITLE_MISUSE = ("课程标题是", "作为课程标题", "标题是画面核心")


def _screen_quote_sets(prompt: str, visible: list[str], course_title: str) -> tuple[set[str], set[str]]:
    """Course titles may themselves contain 「」. Shield the whole title before scanning quotes."""
    token = "\uE000"
    title = (course_title or "").strip()
    shielded = prompt.replace(title, token) if title else prompt
    quoted = set(QUOTED_COPY.findall(shielded))
    expected: set[str] = set()
    for item in visible:
        text = item.strip()
        if not text:
            continue
        if title and text == title:
            expected.add(token)
            if title in prompt:
                quoted.add(token)
        else:
            expected.add(text)
    return quoted, expected


def image_prompt_errors(label: str, page_num: str, visible: list[str], prompt: str, course_title: str) -> list[str]:
    """立场、课名、上屏字。大纲关和出图关共用，避免 S3 过了 S4 才爆。"""
    errors: list[str] = []
    if "本页意图" not in prompt:
        errors.append(f"{label} 缺「本页意图」")
    if "本页立场：" not in prompt:
        errors.append(f"{label} 缺「本页立场」，无法确认是否把误区当结论")
    quoted, expected = _screen_quote_sets(prompt, visible, course_title)
    if quoted != expected:
        errors.append(f"{label} 引号内文案不等于本页上屏字：{sorted(quoted)}")
    if page_num == "01":
        title = (course_title or "").strip()
        if title and (not visible or visible[0].strip() != title):
            errors.append("第01页第一条上屏字必须是课程标题")
        if title and title not in prompt:
            errors.append(f"{label} 未使用课程标题")
        if "课程标题" not in prompt:
            errors.append(f"{label} 未明确标记课程标题")
    elif any(marker in prompt for marker in PROMPT_TITLE_MISUSE):
        errors.append(f"{label} 把内容页主文案误称为课程标题")
    return errors


# ---------------------------------------------------------------- selected PPT style


@dataclass(frozen=True)
class SelectedStyle:
    catalog: str
    variant: str
    name: str
    lock: str
    cover: Path | None


STYLE_CLOSER = "风格以选定封面为准：提示词里若出现与此冲突的底色、画派或配色，一律忽略。"
TITLE_CALLIGRAPHY = (
    "大标题必须写成中文毛笔行楷：浓淡墨色、自然飞白、笔锋起收、水墨笔刷颗粒；"
    "浅底用墨褐主字，深底用浅象牙主字，关键字可点朱砂。"
    "禁止印刷黑体、无衬线杂志体、宋体铅字。不要狂草到难以辨认，每个汉字必须准确、完整、清晰可辨"
)
STYLE_SHOT = (
    "按高端品牌杂志整页摄影生成：有真实材质、光线和景深，文字是画面的一部分，不是后贴字。"
    "将背景、图片、插画、图形、标题和正文直接整合成同一张页面图片，图片垫底。"
    f"{TITLE_CALLIGRAPHY}。"
    "不要扁平图标、线框流程图、软件界面或信息图控件。"
)

_STYLE_LOCKS = {
    ("003", "ivory"): (
        "极简杂志-浅",
        "采用极简品牌杂志风格：象牙白纯净背景、大字号中文标题、高级摄影或克制编辑插画、强留白、精确对齐和少量强调色。"
        + TITLE_CALLIGRAPHY,
    ),
    ("003", "ink"): (
        "极简杂志-深",
        "采用极简品牌杂志风格：深墨或深夜蓝纯净背景、浅象牙大字号中文标题、高级摄影或克制编辑插画、强留白、精确对齐和少量金属强调色。"
        + TITLE_CALLIGRAPHY,
    ),
    ("008", "wash"): (
        "梦幻水彩",
        "采用梦幻水彩编辑插画风格：冷压水彩纸、透明晕染、松散笔触、柔和自然光、靛蓝与珊瑚红点缀，文字区域保持干净。"
        + TITLE_CALLIGRAPHY,
    ),
    ("038", "curve"): (
        "中式曲线",
        "采用中式曲线极简风格：编辑插画、海报式标题、克制留白与精确对齐、自然景观与纵深，少量曲线结构，不要宫廷堆金。"
        + TITLE_CALLIGRAPHY,
    ),
}

_VARIANT_KEYS = {
    "ivory": ("003", "ivory"),
    "ink": ("003", "ink"),
    "wash": ("008", "wash"),
    "curve": ("038", "curve"),
}

_STYLE_CONFLICTS = {
    ("003", "ivory"): ("中式曲线极简", "梦幻水彩", "暖象牙色宣纸", "青绿矿物山水"),
    ("003", "ink"): ("中式曲线极简", "梦幻水彩", "暖象牙色宣纸", "青绿矿物山水"),
    ("008", "wash"): ("极简品牌杂志", "中式曲线极简", "暖象牙色宣纸", "青绿矿物山水"),
    ("038", "curve"): ("极简品牌杂志", "梦幻水彩编辑"),
}


def style_lock_text(variant: str) -> str:
    key = _VARIANT_KEYS.get((variant or "").strip())
    if key is None:
        raise KeyError(variant)
    return _STYLE_LOCKS[key][1]


def resolve_style(catalog: str, variant: str, name: str = "") -> SelectedStyle | None:
    catalog = (catalog or "").strip()
    variant = (variant or "").strip()
    key: tuple[str, str] | None = (catalog, variant)
    if key not in _STYLE_LOCKS:
        key = _VARIANT_KEYS.get(variant)
    if key is None or key not in _STYLE_LOCKS:
        return None
    catalog, variant = key
    lock_name, lock = _STYLE_LOCKS[key]
    return SelectedStyle(
        catalog=catalog,
        variant=variant,
        name=(name or lock_name).strip() or lock_name,
        lock=lock,
        cover=None,
    )


def load_selected_style(course: Path) -> SelectedStyle | None:
    path = course / "20-页图" / "选定模板.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    style = resolve_style(
        str(data.get("catalog") or ""),
        str(data.get("variant") or ""),
        str(data.get("name") or ""),
    )
    if style is None:
        return None
    cover = course / "20-页图" / "选定封面.png"
    return SelectedStyle(
        catalog=style.catalog,
        variant=style.variant,
        name=style.name,
        lock=style.lock,
        cover=cover if cover.is_file() else None,
    )


def apply_style_lock(prompt: str, style: SelectedStyle) -> str:
    text = (prompt or "").strip()
    if style.lock not in text:
        text = (
            f"请生成一张16:9横版完整PPT成品页。{style.lock}。"
            f"必须延续选定封面的底色、字体与气质。\n{text}"
        )
    if STYLE_SHOT not in text:
        text = text.rstrip() + "\n" + STYLE_SHOT
    if STYLE_CLOSER not in text:
        text = text.rstrip() + "\n\n" + STYLE_CLOSER
    return text.rstrip() + "\n"


def style_refs(course: Path, style: SelectedStyle | None = None) -> list[Path]:
    """Inner pages are text-to-image. Keep the hook for tools that only need the cover path."""
    del course, style
    return []


def style_lock_errors(label: str, prompt: str, style: SelectedStyle) -> list[str]:
    errors: list[str] = []
    if style.lock not in prompt:
        errors.append(f"{label} 未写入选定风格「{style.name}」")
    for phrase in _STYLE_CONFLICTS.get((style.catalog, style.variant), ()):
        if phrase in prompt:
            errors.append(f"{label} 与选定风格冲突：出现「{phrase}」")
    return errors


_OUTLINE_PAGE = re.compile(r"^##\s*第(\d{2})页｜(.+?)\s*$", re.M)
_OUTLINE_TITLE = re.compile(r"^#\s+PPT\s*大纲：\s*(.+?)\s*$", re.M)


def _outline_block_span(body: str, name: str) -> tuple[int, int, str] | None:
    hit = re.search(rf"^###\s+{re.escape(name)}\s*$", body, re.M)
    if not hit:
        return None
    rest_start = hit.end()
    nxt = re.search(r"^###\s+", body[rest_start:], re.M)
    end = rest_start + nxt.start() if nxt else len(body)
    return hit.start(), end, body[rest_start:end]


def _outline_screen_lines(section: str) -> list[str]:
    lines: list[str] = []
    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.startswith("（"):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        if line.startswith("「") and line.endswith("」") and line.count("「") == 1:
            line = line[1:-1].strip()
        if line:
            lines.append(line)
    return lines


def _poster_lines(prompt: str) -> list[str]:
    found: list[str] = []
    capture = False
    for raw in prompt.splitlines():
        if "画面仅出现" in raw:
            capture = True
            continue
        if not capture:
            continue
        match = re.fullmatch(r"「([^」]+)」", raw.strip())
        if match:
            found.append(match.group(1))
            continue
        if found:
            break
    return found


def _quoted_screen_lines(prompt: str, course_title: str) -> list[str]:
    poster = _poster_lines(prompt)
    if poster:
        return poster
    token = "\uE000"
    shielded = prompt.replace(course_title, token) if course_title else prompt
    found: list[str] = []
    for item in QUOTED_COPY.findall(shielded):
        if not item.strip() or item == token:
            continue
        if item not in found:
            found.append(item)
    return found


def _as_quote(item: str, title: str) -> str:
    if title and item == title and ("「" in title or "」" in title):
        return item
    return f"「{item}」"


def _rewrite_prompt_quotes(prompt: str, screen: list[str], num: str, title: str) -> str:
    prompt = prompt.replace("本页立场:", "本页立场：")
    prompt = QUOTED_COPY.sub(r"\1", prompt)
    if num != "01":
        prompt = prompt.replace("标题是画面核心", "主文案是画面核心")
        prompt = prompt.replace("课程标题是", "本页主文案是")
        prompt = prompt.replace("作为课程标题", "作为本页主文案")
    lines = prompt.splitlines()
    out: list[str] = []
    index = 0
    replaced = False
    while index < len(lines):
        line = lines[index]
        out.append(line)
        index += 1
        if "画面仅出现" not in line:
            continue
        replaced = True
        while index < len(lines):
            stripped = lines[index].strip()
            inner = stripped[1:-1] if stripped.startswith("「") and stripped.endswith("」") else stripped
            if stripped == "":
                index += 1
                break
            if inner in screen or (stripped.startswith("「") and stripped.endswith("」")):
                index += 1
                continue
            break
        for item in screen:
            out.append(_as_quote(item, title))
        out.append("")
    prompt = "\n".join(out).strip()
    if not replaced and screen:
        quoted = "\n".join(_as_quote(item, title) for item in screen)
        prompt = prompt.rstrip() + "\n\n画面仅出现以下中文，不增字、不漏字、不改字：\n" + quoted + "\n"
    if num == "01" and title and "课程标题" not in prompt:
        if "「" in title or "」" in title:
            lead = f"课程标题：{title}，必须是画面第一视觉中心，字号最大。"
        else:
            lead = f"课程标题是「{title}」，必须是画面第一视觉中心，字号最大。"
        prompt = lead + "\n" + prompt.lstrip()
    return prompt.strip() + "\n"


def align_outline_text(text: str) -> str:
    """Keep one on-screen list. Lecture notes stay in 正文 and are not matched to quotes."""
    title_hit = _OUTLINE_TITLE.search(text)
    course_title = title_hit.group(1).strip() if title_hit else ""
    hits = list(_OUTLINE_PAGE.finditer(text))
    if not hits:
        return text
    chunks = [text[: hits[0].start()]]
    for index, hit in enumerate(hits):
        end = hits[index + 1].start() if index + 1 < len(hits) else len(text)
        body = text[hit.end() : end]
        num = hit.group(1)
        screen_span = _outline_block_span(body, "上屏字")
        prompt_span = _outline_block_span(body, "提示词")
        screen = _outline_screen_lines(screen_span[2]) if screen_span else []
        prompt = prompt_span[2].strip() if prompt_span else ""
        if not screen:
            screen = _quoted_screen_lines(prompt, course_title)
        if num == "01" and course_title and (not screen or screen[0] != course_title):
            screen = [course_title, *[item for item in screen if item != course_title]]
        quote_errors = image_prompt_errors(f"第{num}页提示词", num, screen, prompt, course_title) if prompt and screen else ["待对齐"]
        quote_errors = [item for item in quote_errors if "本页立场" not in item and "本页意图" not in item]
        screen_block = "### 上屏字\n\n" + "\n".join(f"- {item}" for item in screen) + "\n\n" if screen else ""
        if screen_span and not quote_errors:
            chunks.append(text[hit.start() : end])
            continue
        if not prompt or not screen:
            chunks.append(text[hit.start() : end])
            continue
        if not screen_span and not quote_errors:
            inserted = False
            for anchor in ("正文", "提示词"):
                span = _outline_block_span(body, anchor)
                if span:
                    body = body[: span[0]] + screen_block + body[span[0] :]
                    inserted = True
                    break
            if not inserted:
                body = "\n" + screen_block + body.lstrip("\n")
            chunks.append(hit.group(0) + body)
            continue
        new_prompt = _rewrite_prompt_quotes(prompt, screen, num, course_title)
        if screen_span:
            body = body[: screen_span[0]] + screen_block + body[screen_span[1] :]
            prompt_span = _outline_block_span(body, "提示词")
        else:
            inserted = False
            for anchor in ("正文", "提示词"):
                span = _outline_block_span(body, anchor)
                if span:
                    body = body[: span[0]] + screen_block + body[span[0] :]
                    inserted = True
                    break
            if not inserted:
                body = "\n" + screen_block + body.lstrip("\n")
            prompt_span = _outline_block_span(body, "提示词")
        if prompt_span:
            body = body[: prompt_span[0]] + "### 提示词\n\n" + new_prompt + "\n" + body[prompt_span[1] :]
        chunks.append(hit.group(0) + body)
    return "".join(chunks)


def read_plan_scale(course_dir: Path) -> dict[str, object]:
    """Read 方案「预计成品」规模：页数、时长、停顿。缺文件或缺项则为 None。"""
    plan = Path(course_dir) / "10-内容稿" / "方案.md"
    if not plan.is_file():
        return {}
    text = plan.read_text(encoding="utf-8")
    table = read_section_table(text, "预计成品")
    if not (table.get("PPT页数") or table.get("视频时长")):
        labels = labeled_fields(bullet_span(text, "预计成品") or section_text(text, "预计成品"))
        for key in ("PPT页数", "制作页数", "视频时长", "停顿秒数", "内容稿字数", "口播字数"):
            if not (table.get(key) or "").strip() and labels.get(key):
                table[key] = labels[key]
    pages_raw = table.get("PPT页数") or table.get("制作页数") or ""
    pages_match = NUMBER.search(pages_raw)
    duration_raw = (table.get("视频时长") or "").strip()
    duration_match = DURATION_RANGE.search(duration_raw)
    pause_raw = (table.get("停顿秒数") or "").strip()
    pause_match = NUMBER.search(pause_raw) if pause_raw else None
    return {
        "pages": int(float(pages_match.group(1))) if pages_match else None,
        "duration": duration_raw,
        "duration_range": (float(duration_match.group(1)), float(duration_match.group(2))) if duration_match else None,
        "pause": float(pause_match.group(1)) if pause_match else None,
        "script_chars": (table.get("内容稿字数") or "").strip(),
        "oral_chars": (table.get("口播字数") or "").strip(),
    }


def load_durations(path: Path) -> list[float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [float(item["seconds"]) for item in data["pages"]]


def speech_hash(text: str) -> str:
    """Identity of the exact oral text that was sent to TTS."""
    normalized = text.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _header_pause_seconds(doc: Script) -> float:
    raw = (doc.header.get("停顿") or doc.header.get("停顿秒数") or "").strip()
    hit = re.search(r"(\d+(?:\.\d+)?)", raw)
    return float(hit.group(1)) if hit else 0.0


def _script_matching_voice(vo: Path, pages: list) -> Path | None:
    """The customer-edited 口播稿 is the only script a film may follow.

    口播逐字稿 is only a fallback when 口播稿.md does not exist.
    An older take must not be treated as current just because its hash matches.
    """
    oral = vo / "口播稿.md"
    if oral.is_file():
        return oral
    legacy = vo / "口播逐字稿.md"
    if legacy.is_file():
        return legacy
    return None


def timed_voice_error(course: Path) -> str:
    """Refuse estimated captions and audio that no longer matches the oral script."""
    vo = course / "30-口播字幕"
    dur_path = vo / "每页秒数.json"
    if not dur_path.is_file() or not ((vo / "口播稿.md").is_file() or (vo / "口播逐字稿.md").is_file()):
        return "成音或口播稿还没齐"
    try:
        data = json.loads(dur_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "每页秒数.json 读不了，先重出成音"
    pages = data.get("pages") or []
    script = _script_matching_voice(vo, pages)
    if script is None:
        return "成音或口播稿还没齐"
    if data.get("timing") != "words":
        return "成音没有逐字时间。先按当前口播稿重出成音。"
    doc = parse_script(script)
    if len(pages) != len(doc.pages):
        return f"口播稿 {len(doc.pages)} 页，成音 {len(pages)} 页，先重出成音"
    pause = _header_pause_seconds(doc)
    stored_pause = data.get("pause_seconds")
    if not isinstance(stored_pause, (int, float)) or abs(float(stored_pause) - pause) > 0.01:
        return "文头停顿和成音不一致，先重出成音。"
    for page, item in zip(doc.pages, pages):
        if item.get("speech_hash") != speech_hash(page.speech):
            return f"第{page.num}页口播已改，成音还是旧稿。先重出成音，不能沿用旧字幕。"
        if page.speech.strip() and not item.get("words"):
            return f"第{page.num}页没有逐字时间。先按当前口播稿重出成音。"
    return ""


def cuts_from_durations(durations: list[float]) -> list[float]:
    """Page-cut timestamps (excluding t=0 and the end)."""
    cuts: list[float] = []
    acc = 0.0
    for sec in durations[:-1]:
        acc += sec
        cuts.append(round(acc, 3))
    return cuts


# ---------------------------------------------------------------- secrets

def load_key(name: str, env_path: Path | None = None) -> str:
    """Env var first, then --env file, repo-root .env, then ~/.baoyu-skills/.env."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    candidates = [env_path, env_file(), Path.home() / ".baoyu-skills" / ".env"]
    for candidate in candidates:
        if candidate and candidate.is_file():
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == name and v.strip():
                    return v.strip().strip('"').strip("'")
    raise SystemExit(f"{name} 未配置。写进仓库根目录 .env（照 .env.example），或 ~/.baoyu-skills/.env")
