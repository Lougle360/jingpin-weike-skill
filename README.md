# 精品微课 Skill

把一个课程目标做成一条 16:9 口播微课成片。适用于 WorkBuddy、豆包工作等支持 Agent Skills 的 AI 客户端。

```text
课程目标 → 方案 → 完整内容稿 → PPT大纲 ─┬─ 页图 + PPT
                                        └─ 口播稿 → 配音 + 字幕 → 成片
```

全流程六道人工审核。方案没过不写内容稿；PPT 大纲没过不出图；口播稿没过不配音。花钱的两个环节都卡在人点头之后。

## 下载安装

去 [Releases](../../releases) 下载 `精品微课skill-<日期>.zip`，解压后得到 `精品微课/` 文件夹，在 AI 客户端里「上传技能」导入。

完整步骤看 **[安装使用手册](安装使用手册.md)**，从装 Python 开始一步步写到做出第一门课，面向不懂技术的使用者。

## 装完之后

```text
python scripts/setup_workspace.py     # 铺工作目录，只跑一次
python scripts/doctor.py              # 环境自检
```

然后在对话框里说人话即可，例如「用精品微课做一门讲孩子写作业拖拉的课」。

## 两个根

| 根 | 放什么 | 谁维护 |
|---|---|---|
| 技能包 | `SKILL.md`、`scripts/`、`references/`、`assets/` | 随版本更新，只读 |
| 工作目录 | `projects/`、`knowledge/`、`config/`、`.env`、`assets/素材/` | 使用者自己的，升级不覆盖 |

工作目录默认 `~/精品微课`，可用环境变量 `MINI_WORK_DIR` 指到别处。

## 目录

```text
SKILL.md          总控：状态机、六道关、驳回回路
scripts/          可执行脚本，不进模型上下文
  _lib/           共享库，双根定位
  min-*/          各环节的质检与生成脚本
  kie/            出图命令行
references/       按需查阅的完整规则
  min-plan/       选题与方案
  min-script/     内容稿与内容红线
  min-review/     知识库校准规则全文
  min-outline/    PPT 分页
  min-visual/     出图与版式
  min-voice/      口播化与配音
  min-video/      合成与混音
  min-bgm/        配乐选曲
  讲师风格/        口播人格档案，可替换
assets/
  品牌包/          风格、音色、字幕、配乐锁定表
  工作目录模板/     首次安装铺到工作目录的默认配置和示例知识库
```

## 外部依赖

| 依赖 | 用途 | 必需 |
|---|---|---|
| Python 3.10+、`pillow` `python-pptx` `lxml` | 全部脚本 | 是 |
| ffmpeg / ffprobe | 合成成片 | 出成片时必需 |
| 写稿 API（硅基流动 / 百炼 / OpenAI 兼容任一） | 方案、内容稿、大纲、口播稿 | 是 |
| `KIE_API_KEY` | 页图出图 | 出图时必需 |
| `VOLC_TTS_API_KEY` | 口播配音 | 配音时必需 |

背景音乐曲库不随包分发，需自备并放进工作目录的 `assets/素材/背景音乐/`，曲名对上品牌包 `配乐.md`。

## 换成自己的领域

技能包不绑定具体学科。换领域改三处：

1. 把自己的知识库放进工作目录 `knowledge/`，格式参照 `assets/工作目录模板/knowledge/示例知识库/`
2. 改工作目录 `config/知识库.md` 的第一张表，指到你的库
3. 视觉和音色改工作目录 `config/品牌包/<品牌>/` 下的风格、音色、配乐、字幕四张表

`references/` 里的选题清单、内容红线和讲师风格档案仍带有原领域（国学课程）的痕迹，按自己的领域改写即可。
