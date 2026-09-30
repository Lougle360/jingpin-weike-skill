# -*- coding: utf-8 -*-
"""专名必须来自知识库、谷子逐字稿或本课课程目标。不维护禁用词表。"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import mini as _mini
_TRANSCRIPT_NAME = "《五福系统课》-D3新-逐字稿.md"


def find_transcript() -> Path | None:
    """本机在仓库上两级的资料区；服务器目录更浅，找不到就不用，不能在导入时崩。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "资料区" / _TRANSCRIPT_NAME
        if candidate.is_file():
            return candidate
    return None


TRANSCRIPT = find_transcript()

# 专名里夹了这些字，就是句子碎片，不是被立起来的名字。
_SKIP = set("的了是不在把被和与或这那就要会能给做没又很最该从对向里个")
_CJK = r"[一-龥]"
_NAMED = re.compile(
    rf"(?:这就叫|叫做|(?<!不能)称为|(?<!不能)称作|所谓)「?({_CJK}{{2,4}})」?(?!{_CJK})"
)
_DEFINED = re.compile(rf"(?:一种是|另一种是)({_CJK}{{2,4}})[：:]")
_HEADING = re.compile(r"^(#{1,3}\s+.+)$", re.M)
_PAGE = re.compile(r"第\d{2}页｜(.+?)\s*$")
_BEFORE_NOT = re.compile(rf"(?<!{_CJK})({_CJK}{{2,3}})(?=不是)")
_AFTER_NOT = re.compile(rf"(?<=不是)({_CJK}{{2,3}})(?!{_CJK})")
_AFTER_BUT = re.compile(rf"(?<=而是)({_CJK}{{2,3}})(?!{_CJK})")


def course_dir_of(path: Path) -> Path:
    """projects/<课名>/... → 课目录。"""
    resolved = path.resolve()
    for parent in resolved.parents:
        if (parent / "_state.md").is_file():
            return parent
    raise FileNotFoundError(f"找不到 _state.md：{resolved}")


def coined_terms(text: str) -> list[str]:
    """抽出被当成名字的 2～4 字。普通长句不抽。"""
    found: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        if term in seen or not _keep(term):
            return
        seen.add(term)
        found.append(term)

    for pattern in (_NAMED, _DEFINED):
        for term in pattern.findall(text):
            add(term)
    for line in _HEADING.findall(text):
        _add_contrast(line, add)
    for title in _PAGE.findall(text):
        _add_contrast(title, add)
    return found


def unknown_terms(text: str, corpus: str) -> list[str]:
    return [term for term in coined_terms(text) if term not in corpus]


def source_errors(text: str, course_dir: Path) -> list[str]:
    try:
        corpus = allowed_corpus(str(course_dir.resolve()))
    except FileNotFoundError as exc:
        return [f"专名来源缺失：{exc}"]
    missing = unknown_terms(text, corpus)
    if not missing:
        return []
    shown = "、".join(f"「{term}」" for term in missing)
    return [
        "专名"
        + shown
        + "没有来源。只能用知识库、谷子逐字稿或本课课程目标里已有的叫法；没有的写成整句，不要新造"
    ]


@lru_cache(maxsize=16)
def allowed_corpus(course_dir: str) -> str:
    root = Path(course_dir)
    state = root / "_state.md"
    if not state.is_file():
        raise FileNotFoundError(f"缺 _state.md：{root}")
    fields = _state_fields(state.read_text(encoding="utf-8"))
    kb_root = fields.get("kb_root", "").strip()
    if not kb_root:
        raise FileNotFoundError(f"{state} 缺 kb_root")
    kb = _mini.work_root() / kb_root
    if not kb.is_dir():
        raise FileNotFoundError(f"知识库不存在：{kb}")
    parts = [
        fields.get("course", ""),
        fields.get("course_goal", ""),
        fields.get("folk_saying", ""),
    ]
    if TRANSCRIPT is not None and TRANSCRIPT.is_file():
        parts.append(TRANSCRIPT.read_text(encoding="utf-8"))
    parts.extend(path.read_text(encoding="utf-8") for path in kb.rglob("*") if path.suffix.lower() in {".md", ".txt", ".yaml", ".yml"})
    return "\n".join(parts)


def _keep(term: str) -> bool:
    return 2 <= len(term) <= 4 and not any(char in _SKIP for char in term)


def _add_contrast(line: str, add) -> None:
    for pattern in (_BEFORE_NOT, _AFTER_NOT, _AFTER_BUT):
        for term in pattern.findall(line):
            add(term)


def _state_fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        parts = [cell.strip().strip("`") for cell in raw.strip().strip("|").split("|")]
        if len(parts) >= 2 and parts[0] not in {"字段", ""} and set(parts[0]) - set("-: "):
            out[parts[0]] = parts[1]
    return out
