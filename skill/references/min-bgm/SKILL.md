---
name: min-bgm
description: 国学微课讲课底乐的选曲、收曲、校音和混音原则。Use when the user mentions 背景音乐、底乐、配乐、BGM、曲库、垫乐, when ingesting new tracks, rematching a course, or when Gate-S5 rejects music.
---

# min-bgm　国学讲课底乐

给 `min-video` 用。不改口播、页图、字幕。人只在看片时点头或驳回，Gate 由 `min-video` 写。

黄金案例：《别被煞吓住》用 `茶室箫.mp3`（琴+尺八）。人点头：应景，跟提示词画面相匹配。

混音样片：《奇门取用神，为什么必须一事一物？》成片（2026-09-24 点头）。茶室箫电平 `0.14`，侧链 attack `55` / ratio `6.5` / mix `0.92`。新课按这套，不要把茶室箫调回 `0.23`。

先读 `config/品牌包/<品牌>/配乐.md`、`config/素材库.md`、`assets/素材/背景音乐/来源.md`。对照例子见 [EXAMPLES.md](EXAMPLES.md)。

## 原则

1. **这是讲课垫，不是主题曲。** 要听得出是垫乐，但不能抢口播。一条床铺完全程。
2. **国学课用琴箫。** 古筝/琴 + 洞箫/尺八。清雅、留白，像茶室或书院。
3. **禁二胡、胡琴。** 影视哭腔；音色跟人声同频，字会糊，情绪会往想哭走。
4. **禁这些。** 西洋钢琴、古琴独奏成曲、自制正弦层、锣鼓/Drop、人声唱腔、活动音乐。
5. **跟画面同向。** 对内容稿，也对页图提示词的气场（房间、茶室、清雅），不要只对关键词。
6. **响度一条线。** LRA 大约 5 以内。中间没有句读高潮。循环看不见接缝。
7. **只定场，不煽情。** 情绪不定情节。
8. **跟老师的声线错开。** 混音让出人声频段；讲话压低但仍听得见，不许压没、不许瞬间掐断。

验法：不用开很大声，听 20 秒能感到垫乐在，也能听清老师每一句。过不了关的不进曲库。

## 方法

收曲（曲库缺、或人说重新找）：

1. 按「国学讲课 / 书院 / 茶室 / 古筝洞箫」去找，不搜古风游戏主题曲、不搜二胡抒情。
2. 优先已许可来源：剪映商用库、爱给网商用、もみじば、PeriTune、甘茶。下到 `assets/素材/背景音乐/`，写入 `来源.md`。
3. 跑 `measure_bed.py`。LRA > 5 丢掉。听 20 秒：有完整主旋、有哭腔、有拨弦高潮 → 丢掉。
4. 按口播响度算电平，写入 `配乐.md` 曲库（场景 + 关键词 + 电平）。缺省只作平手回退。

选曲（出片或换曲）：

1. `build_video.py` 对课名、金句、目标、页名、口播、页图提示词打分。体验先导偏向「清冷观察」，正序偏向「温和推进」。
2. 平手用缺省。人指定走 `--bgm 曲目名`。
3. 听成片：垫乐在、字清、不哭、跟画面同向。不对就换曲或改电平，只 `--mix-only`。

混音（已写在 `min-video/scripts/mix_vo_bed.py`，参数在 `配乐.md`）：

- 让出人声：高通 220、压 350 / 1200 / 2500 Hz、低通 6500。
- 侧链：threshold 0.04，ratio 6.5，attack 55，release 420，knee 6，mix 0.92。开口要尽快让路，讲话时少留没压下去的底乐。
- 曲库电平以 `配乐.md` 为准：茶室箫 / 缺省 `0.14`，闲箫垫 `0.15`，其余保持 0.11～0.15。垫乐大约比口播低 10～12 dB。
- 翻页音效不进压低链。
- 短于成片：交叉淡入循环；头 1.6 秒淡入，尾 6 秒淡出。

## 脚本

量曲、算电平（本 Skill）：

```text
python Skills/min-bgm/scripts/measure_bed.py
python Skills/min-bgm/scripts/measure_bed.py "assets/素材/背景音乐/茶室箫.mp3"
python Skills/min-bgm/scripts/measure_bed.py --vo "projects/别被煞吓住/30-口播字幕/口播.wav"
```

出片、换曲、只改混音（`min-video`）：

```text
python Skills/min-video/scripts/build_video.py projects/<课名> --brand 谷子
python Skills/min-video/scripts/build_video.py projects/<课名> --brand 谷子 --mix-only
python Skills/min-video/scripts/build_video.py projects/<课名> --brand 谷子 --mix-only --bgm 清冷观察
```

不要另写下载脚本当曲库。曲库只活在 `配乐.md`。

## 驳回

| 人说 | 做 |
|---|---|
| 听不见 / 太小 | 改该曲电平 → `--mix-only` |
| 抢话 / 糊字 | 先查是不是二胡；是则换琴箫。再查电平。不把垫乐做成无声正弦层 |
| 想哭、煽情 | 换掉弓弦，换琴箫 |
| 不应景 | 按提示词气场换曲目，或改关键词 |
| 中间乱跳 | 该曲出库（LRA 超了或有句读） |

点头：写入该课 `40-成片/质检记录.md` 看片意见，不要默默改曲。
