# -*- coding: utf-8 -*-
"""Environment self-check for a fresh machine. Exit 1 if anything blocking is missing.

    python Skills/精品微课/scripts/doctor.py
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

R = mini.work_root()
S = mini.skill_root()
ok_all = True


def ok(msg: str) -> None:
    print("  [OK]  ", msg)


def bad(msg: str, blocking: bool = True) -> None:
    global ok_all
    if blocking:
        ok_all = False
    print("  [缺]  " if blocking else "  [提示]", msg)


def check_python() -> None:
    v = sys.version_info
    if v >= (3, 10):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        bad(f"Python {v.major}.{v.minor}，需要 3.10 以上")


def check_modules() -> None:
    for mod, pipname in (("PIL", "pillow"), ("pptx", "python-pptx"), ("lxml", "lxml")):
        try:
            importlib.import_module(mod)
            ok(f"python 包 {pipname}")
        except Exception:
            bad(f"python 包 {pipname} 未装：pip install -r requirements.txt")


def check_ffmpeg() -> None:
    for name in ("ffmpeg", "ffprobe"):
        exe = mini.ffmpeg_bin(name)
        found = exe if Path(exe).is_file() else shutil.which(exe)
        if not found:
            bad(f"{name} 找不到。装法：winget install Gyan.FFmpeg；或把 ffmpeg.exe/ffprobe.exe 放到 tools/ffmpeg/bin/")
            continue
        try:
            out = subprocess.run([found, "-version"], capture_output=True, timeout=20).stdout.decode("utf-8", "replace")
            ok(f"{name}: {out.splitlines()[0][:60]}  ({'随包' if 'tools' in found else 'PATH'})")
        except Exception as exc:
            bad(f"{name} 无法运行: {exc}")


def check_env() -> None:
    env = R / ".env"
    home_env = Path.home() / ".baoyu-skills" / ".env"
    configured_env = Path(os.environ["MINI_ENV_PATH"]) if os.environ.get("MINI_ENV_PATH") else None
    if not env.is_file() and not home_env.is_file() and not (configured_env and configured_env.is_file()):
        bad("密钥环境文件不存在。复制 .env.example 为 .env，或设置 MINI_ENV_PATH", blocking=False)
    provider = os.environ.get("MINI_AGENT_PROVIDER", "auto").strip().lower()
    checks = [(("VOLC_TTS_API_KEY", "VOLC_SPEECH_API_KEY"), "豆包出声 min-voice"), (("KIE_API_KEY",), "出图 min-visual")]
    if provider in {"bailian", "dashscope", "auto"}:
        checks.insert(0, (("DASHSCOPE_API_KEY", "OPENAI_API_KEY"), "百炼 / 通义 Agent"))
    if provider in {"siliconflow", "auto"}:
        checks.insert(0, (("SILICONFLOW_API_KEY",), "硅基流动 Agent"))
    for keys, use in checks:
        configured = ""
        for key in keys:
            try:
                mini.load_key(key)
                configured = key
                break
            except SystemExit:
                continue
        if configured:
            ok(f"{configured} 已配置（{use}）")
        else:
            bad(f"{' / '.join(keys)} 未配置 → {use} 不能跑；其它步骤不受影响", blocking=False)


def check_files() -> None:
    must = [
        mini.config_file("素材库.md"),
        mini.brand_dir() / "品牌包.md",
        mini.brand_dir() / "模板" / "清单.md",
        mini.brand_dir() / "模板" / "003-极简品牌杂志.md",
        mini.brand_dir() / "模板" / "008-梦幻水彩编辑.md",
        mini.brand_dir() / "模板" / "038-中式曲线极简.md",
        mini.skill_file("min-script", "口播.md"),
        mini.skill_file("min-script", "红线.md"),
        mini.skill_file("min-plan", "可写主题清单.md"),
        mini.skill_file("min-voice", "口播化.md"),
        mini.skill_file("min-voice", "场景化.md"),
        S / "scripts" / "min-voice" / "qa_voice_script.py",
        S / "scripts" / "kie" / "kie.py",
        mini.config_file("知识库.md"),
        mini.skill_file("min-plan", "templates", "Gate-S1方案.md"),
        mini.skill_file("min-script", "templates", "Gate-S2内容稿.md"),
        mini.skill_file("min-outline", "SKILL.md"),
        mini.skill_file("min-outline", "templates", "Gate-S3-PPT大纲.md"),
        S / "scripts" / "min-outline" / "qa_outline.py",
        mini.skill_file("min-visual", "templates", "Gate-S4-PPT.md"),
        mini.skill_file("min-voice", "templates", "Gate-S4口播稿.md"),
        mini.skill_file("min-video", "templates", "Gate-S5成片.md"),
        S / "SKILL.md",
    ]
    for p in must:
        if p.is_file():
            ok(p.name)
        else:
            bad(f"缺文件 {p}")
    try:
        root = mini.asset_root()
        if root.is_dir():
            ok(f"素材根 {root.relative_to(R) if root.is_relative_to(R) else root}")
        else:
            bad(f"素材根不存在: {root}")
    except SystemExit as exc:
        bad(str(exc))
    style = mini.read_table(mini.brand_dir() / "风格.md")
    logo = mini.resolve_path(style.get("Logo", ""))
    ok(f"Logo {logo.name}") if logo.is_file() else bad(f"Logo 不存在: {logo}")
    music = mini.brand_dir() / "配乐.md"
    for cells in mini.read_table_rows(music):
        if len(cells) < 2:
            continue
        label, file = cells[0], cells[1]
        if label in ("曲目", "用途"):
            continue
        if "/" not in file:
            continue
        if label in ("底乐", "翻页") or file.startswith("背景音乐/"):
            p = mini.asset_root() / file
            ok(f"{label} {file}") if p.is_file() else bad(f"{label} 缺曲 {file} → 放到 {mini.asset_root()} 下；只影响成片垫乐", blocking=False)


def check_kb() -> None:
    bases = mini.knowledge_bases()
    if not bases:
        bad("config/知识库.md 没列出任何库")
        return
    for kb in bases:
        root = mini.resolve_path(kb.path)
        if not root.is_dir():
            bad(f"知识库「{kb.name}」不存在: {kb.path}")
            continue
        index = [n for n in ("README.md", "kb-profile.yaml") if (root / n).is_file()]
        if index:
            ok(f"知识库「{kb.name}」{kb.path}（{'、'.join(index)}）")
        else:
            bad(f"知识库「{kb.name}」缺 README.md 或 kb-profile.yaml: {kb.path}")


def main() -> int:
    print(f"精品微课 环境自检\n  技能包: {S}\n  工作目录: {R}")
    print("-- 运行时")
    check_python()
    check_modules()
    check_ffmpeg()
    print("-- 密钥")
    check_env()
    print("-- 文件")
    check_files()
    print("-- 知识库")
    check_kb()
    print()
    print("结论：可以开工" if ok_all else "结论：先补上面标 [缺] 的项")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
