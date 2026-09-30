# -*- coding: utf-8 -*-
"""在客户电脑上铺好工作目录。装完技能后只跑这一次。

    python scripts/setup_workspace.py              # 铺到 ~/精品微课
    python scripts/setup_workspace.py --dir D:/微课  # 铺到指定位置

工作目录放所有会变的东西：课程产出、知识库、素材、密钥、品牌包。
技能包本身只读，升级技能不会覆盖这里。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

ENV_TEMPLATE = """# 精品微课密钥。填好保存，不要发给别人。
# 三类密钥各管一段：写稿、出图、配音。只填一部分也能用，缺哪段哪段不能跑。

# --- 1. 写稿引擎（三选一即可） ---
# 硅基流动 https://siliconflow.cn
SILICONFLOW_API_KEY=
# 阿里云百炼 / 通义 https://bailian.console.aliyun.com
DASHSCOPE_API_KEY=
# 任意 OpenAI 兼容接口
OPENAI_API_KEY=
MINI_AGENT_BASE_URL=

# --- 2. 出图（做 PPT 页面用）---
# Kie.ai https://kie.ai
KIE_API_KEY=

# --- 3. 配音（生成口播音频用）---
# 火山引擎语音控制台的 API Key，不是 IAM 的 AK/SK
VOLC_TTS_API_KEY=
"""

DIRS = ["projects", "config", "knowledge", "assets/素材/背景音乐", "assets/素材/访谈音效", "tools/ffmpeg/bin"]


def copy_missing(src: Path, dst: Path) -> tuple[int, int]:
    """只补不覆盖：客户改过的文件一律保留。"""
    added = kept = 0
    if not src.is_dir():
        return 0, 0
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        target = dst / item.relative_to(src)
        if target.exists():
            kept += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        added += 1
    return added, kept


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="", help="工作目录位置，默认 ~/精品微课")
    args = parser.parse_args()

    skill = mini.skill_root()
    if not args.dir and (skill / "projects").is_dir():
        print("检测到这是开发仓库，不是安装好的技能包。要铺工作目录请显式传 --dir。")
        return 1

    work = Path(args.dir).expanduser().resolve() if args.dir else (Path.home() / "精品微课")
    print(f"技能包：{skill}")
    print(f"工作目录：{work}")
    print()

    for d in DIRS:
        (work / d).mkdir(parents=True, exist_ok=True)

    tpl = skill / "assets" / "工作目录模板"
    added, kept = copy_missing(tpl / "config", work / "config")
    print(f"config/        新增 {added}，保留已有 {kept}")
    added, kept = copy_missing(tpl / "knowledge", work / "knowledge")
    print(f"knowledge/     新增 {added}，保留已有 {kept}")
    added, kept = copy_missing(skill / "assets" / "品牌包", work / "config" / "品牌包")
    print(f"config/品牌包/  新增 {added}，保留已有 {kept}")
    added, kept = copy_missing(skill / "assets" / "品牌", work / "assets" / "品牌")
    print(f"assets/品牌/    新增 {added}，保留已有 {kept}（换成自己的 Logo，再改 config/品牌包/<品牌>/风格.md）")

    env = work / ".env"
    if env.exists():
        print(".env           已存在，没动")
    else:
        env.write_text(ENV_TEMPLATE, encoding="utf-8", newline="\n")
        print(".env           已生成，待填密钥")

    print()
    print("下一步：")
    print(f"  1. 用记事本打开 {env} 填密钥")
    print(f"  2. 把你的知识库放进 {work / 'knowledge'}，再改 {work / 'config' / '知识库.md'} 指过去")
    print(f"  3. 合成成片要垫乐，把背景音乐放进 {work / 'assets' / '素材' / '背景音乐'}，曲名对上 config/品牌包/<品牌>/配乐.md")
    print(f"  4. 跑自检：python \"{skill / 'scripts' / 'doctor.py'}\"")
    if not os.environ.get("MINI_WORK_DIR") and work != Path.home() / "精品微课":
        print()
        print(f"  注意：工作目录不在默认位置，请设环境变量 MINI_WORK_DIR={work}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
