---
name: min-visual
description: 已通过的 PPT大纲.md → 封面候选、页图、PPT。封面选择是 PPT 关内部前置动作，不单独占一道主关。
---

# min-visual　PPT 大纲 → 完整 PPT

一页一张整页图。页数、页名、正文和 Image2 中文自然语言提示词全部来自 `PPT大纲.md`，**不改字**。出图前核大纲页数等于方案「预计成品 · PPT页数」；对不上，停，回大纲关，不准出图。

稿关已过：一次出齐，叠 Logo，打 PPT。不要先出代表页再问批量。封面未选先停在四张封面。

## 边界

- 只写 `20-页图/` 和 `Gate-S4-PPT.md`
- 不改 `内容稿.md`，不写口播、配音、成片
- 不读 `min-voice`、`min-video`
- 封面关、视觉关的模板都在本目录 `templates/`

## 先读

1. `config/品牌包/<品牌>/风格.md`
2. `config/品牌包/<品牌>/模板/清单.md`（超云 003 / 008 / 038）
3. 本课 `20-页图/选定模板.json` 与 `选定封面.png`（冲突以这两项和品牌包为准，不用国潮 vendor 当风格源）
4. `projects/<课名>/10-内容稿/方案.md`（只读「预计成品 · PPT页数」）
5. `projects/<课名>/20-页图/PPT大纲.md`（只读）
6. `templates/页表.md`、`templates/Gate-S4-PPT.md`

出图接口：`tools/kie/kie.py`（gpt-image-2）。封装：`scripts/gen_page.py`。密钥见 `mini.load_key`。

## 入 / 出

- 入：已过 PPT 大纲关的 `PPT大纲.md`
- 出：`20-页图/`
  - `封面候选-1.png` … `封面候选-4.png`（003浅 / 003深 / 008 / 038）
  - `四种封面.md`、`选定封面.png`、`选定模板.json`（封面关过了才有）
  - `页表.md`
  - `_prompts/NN.txt`
  - `pages-raw/NN-<页名>.png`
  - `pages/NN-<页名>.png`（已叠 Logo，1920×1080）
  - `代表页.png`：第 02 页（叠过 Logo；只有一页时用第 01 页）
  - `PPT.pptx`

## 流程

0. 封面未定时：先跑 `gen_covers.py`，停在四张封面，不拆内页、不把 PPT 关标为通过。人选定后工作台写入 `选定模板.json`，同一关继续生成完整 PPT。
1. `页表.md`：从 PPT 大纲逐页抄页号、页名和正文。有选定模板时，版式/字体列留空，不填国潮 layout-bank 名。
2. 把 PPT 大纲每页「提示词」原样写入 `_prompts/NN.txt`，不改上屏字、本页意图和本页立场。风格锁由 `gen_page.py` 按 `选定模板.json` 补上；四种风格的大标题一律毛笔行楷。内页走 gpt-image-2 文生图，不附 `选定封面.png`，否则会变成改图。不画 Logo、不画人。
3. **逐页审核 `_prompts/NN.txt`**，不是只审内容稿：
   - 主题立场：不能把待反驳的误区、案例台词或错误断言包装成课程标题、老师结论或页面主张。
   - 角色准确：只有第 01 页课程标题能称为“标题”；其余页只能称“本页主文案/关键词”。
   - 语义一致：本页意图、文字层级和场景意象都服务于页任务，不能让画面表达相反结论。
   - 文案准确：仅出现本页上屏字，不增字、不漏字、不改字。
   - 品牌专业：不靠耸动、宿命、恐吓和错误结论抢视觉中心。
4. 跑 `qa_prompts.py`；`errors=0` 才准付费出图。机器检查不能代替上一步的逐页语义审核。
5. 稿关已过：`gen_page.py … --all --yes`。不要再问付费。
6. `stamp_pages.py` 统一到 1920×1080、叠 Logo、打 PPTX。第 02 页拷成 `代表页.png`。
7. 查硬错误：错字、缺字、多字、严重裁切、多人物、多 Logo、尺寸不对。只重出失败页，最多两次。
8. `check_pages.py`。按本目录 `templates/Gate-S4-PPT.md` 写关，请人逐页查看完整 PPT。

```text
python Skills/min-visual/scripts/qa_prompts.py projects/<课名>
python Skills/min-visual/scripts/gen_page.py projects/<课名> --all --yes
python Skills/min-visual/scripts/stamp_pages.py projects/<课名>/20-页图/pages-raw projects/<课名>/20-页图 --brand 谷子
python Skills/min-visual/scripts/check_pages.py projects/<课名>
```

出图不附参考图。不要附 `选定封面.png`、国潮 `style-reference.png`、`layout-bank/` 或 `typography-reference/`。

## 硬检查

- 每个文生图提示词已过主题立场、角色准确、语义一致、文案准确、品牌专业五项审核
- `qa_prompts.py` 为 `errors=0`
- `pages/` 张数 = PPT 大纲页数 = 方案 PPT页数；文件名以两位页号开头
- 每张 1920×1080（或 16:9 且宽 ≥ 1600）
- 上屏字与 PPT 大纲一致（核代表页 + 抽两页）

## 驳回

- 某页不对：只重出那一页，再跑 `stamp_pages.py`。
- 上屏字或分页要改：回 PPT 大纲关；知识观点要改：回内容稿关。
- 页图张数对不上大纲或方案页数：不准过 PPT 关，按新大纲重出。

## 禁止

- 改上屏字、加新句、把参考图上的字画进去
- 未逐页审核提示词就调用付费出图
- 把每一页的主文案都称为“标题”
- 把反方误区做成最大视觉结论，却没有明确标示它是待反驳观点
- 出甲乙丙风格样张、换风格目录
- 把国潮 style-reference、layout-bank 或选定封面接到内页上做改图
- 把内页写成扁平图标、线框流程或软件界面
- 画人物、数字人留白、页内 Logo
- 写口播逐字稿；在聊天里交图
