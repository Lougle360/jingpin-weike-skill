# -*- coding: utf-8 -*-
"""Put word times on an existing take. Does not re-voice.

Subtitle characters come from the script that matches the recording.
ASR spans only supply time. A page below 0.82 similarity is refused
and nothing is written.

    python Skills/min-voice/scripts/align_existing_vo.py projects/<课名>
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import sys
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

_ASS_PATH = Path(__file__).with_name("build_ass.py")
_ASS_SPEC = importlib.util.spec_from_file_location("build_ass", _ASS_PATH)
assert _ASS_SPEC and _ASS_SPEC.loader
ass = importlib.util.module_from_spec(_ASS_SPEC)
_ASS_SPEC.loader.exec_module(ass)

URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
MIN_RATIO = 0.82


class AlignError(RuntimeError):
    """The heard text cannot be placed on the script."""


def expected_chars(speech: str, pause: float, max_line: int) -> str:
    chars: list[str] = []
    for kind, payload in ass._vo.tts_segments(speech, pause):
        if kind != "speech":
            continue
        for breath in ass.split_breaths(str(payload), max_line):
            chars.extend(ass.HAN.findall(breath))
    return "".join(chars)


def align(expected: str, spans: list[tuple[str, float, float]], duration: float) -> tuple[list[dict], float]:
    """Map heard spans onto script characters.

    Equal characters take the heard start and end. A short mismatch keeps
    the script character and shares that heard span. Extra heard characters
    are dropped. Script characters the recognizer missed are placed between
    the nearest matched neighbors.
    """
    heard = "".join(char for char, _, _ in spans)
    ratio = SequenceMatcher(None, expected, heard).ratio() if expected else 1.0
    if not expected:
        return [], ratio
    if ratio < MIN_RATIO:
        raise AlignError(
            f"整页对不上，相似度 {ratio:.3f}，低于 {MIN_RATIO:.2f}。"
            f"期望「{expected[:12]}」听到「{heard[:12]}」。不写时间，不烧成片。"
        )
    slots: list[tuple[float, float] | None] = [None] * len(expected)
    matcher = SequenceMatcher(None, expected, heard)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                _, start, end = spans[j1 + offset]
                slots[i1 + offset] = (start, end)
        elif tag == "replace" and j2 > j1 and i2 > i1:
            start = spans[j1][1]
            end = spans[j2 - 1][2]
            count = i2 - i1
            step = max(end - start, 0.04 * count) / count
            for offset in range(count):
                slots[i1 + offset] = (start + offset * step, start + (offset + 1) * step)
    anchors = [(index, slot) for index, slot in enumerate(slots) if slot]
    if not anchors:
        raise AlignError("没有对上任何字。不写时间，不烧成片。")
    for index, slot in enumerate(slots):
        if slot:
            continue
        prev = next((item for item in reversed(anchors) if item[0] < index), None)
        nxt = next((item for item in anchors if item[0] > index), None)
        if prev and nxt:
            gap = index - prev[0]
            span = nxt[0] - prev[0]
            start = prev[1][1] + (nxt[1][0] - prev[1][1]) * (gap - 1) / span
            end = prev[1][1] + (nxt[1][0] - prev[1][1]) * gap / span
        elif prev:
            start = prev[1][1] + 0.08 * (index - prev[0] - 1)
            end = start + 0.08
        else:
            assert nxt
            end = nxt[1][0] - 0.08 * (nxt[0] - index - 1)
            start = end - 0.08
        slots[index] = (max(start, 0.0), max(end, start + 0.04))
    words: list[dict] = []
    cursor = 0.0
    for char, slot in zip(expected, slots):
        assert slot
        start, end = slot
        start = min(max(start, cursor), max(duration - 0.05, 0.0))
        end = min(max(end, start + 0.04), duration)
        words.append({"word": char, "start": round(start, 3), "end": round(end, 3)})
        cursor = end
    return words, ratio


def holds_for(speech: str, pause: float, max_line: int, words: list[dict], duration: float) -> list[dict]:
    """Silence between speech blocks uses the gap already in the take."""
    holds: list[dict] = []
    index = 0
    for kind, payload in ass._vo.tts_segments(speech, pause):
        if kind == "speech":
            count = 0
            for breath in ass.split_breaths(str(payload), max_line):
                count += len(ass.HAN.findall(breath))
            index += count
            continue
        prev_end = float(words[index - 1]["end"]) if index else 0.0
        next_start = float(words[index]["start"]) if index < len(words) else duration
        if next_start < prev_end:
            next_start = prev_end
        holds.append({"start": round(prev_end, 3), "end": round(next_start, 3)})
    if index != len(words):
        raise AlignError("停顿切分和逐字对不齐。不写时间，不烧成片。")
    return holds


def asr_spans(data: dict) -> list[tuple[str, float, float]]:
    result = data.get("result") or data.get("data") or data
    utterances = result.get("utterances") or []
    spans: list[tuple[str, float, float]] = []
    for utt in utterances:
        words = utt.get("words") or []
        if not words and utt.get("text"):
            words = [{"text": utt["text"], "start_time": utt.get("start_time"), "end_time": utt.get("end_time")}]
        for word in words:
            text = str(word.get("text") or word.get("word") or "")
            try:
                start = float(word.get("start_time", word.get("start", 0))) / 1000.0
                end = float(word.get("end_time", word.get("end", 0))) / 1000.0
            except (TypeError, ValueError):
                continue
            chars = ass.HAN.findall(text)
            if not chars:
                continue
            if end < start:
                end = start
            step = max(end - start, 0.001 * len(chars)) / len(chars)
            for index, char in enumerate(chars):
                spans.append((char, start + index * step, start + (index + 1) * step))
    return spans


def recognize(path: Path, key: str) -> dict:
    payload = {
        "user": {"uid": "tanzi-caption-align"},
        "audio": {"data": base64.b64encode(path.read_bytes()).decode("ascii"), "format": "wav"},
        "request": {
            "model_name": "bigmodel",
            "enable_itn": False,
            "enable_punc": False,
            "enable_ddc": False,
            "show_utterances": True,
        },
    }
    req = Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": key,
            "X-Api-Resource-Id": "volc.bigasr.auc_turbo",
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
        },
    )
    try:
        with urlopen(req, timeout=180) as resp:
            body = resp.read()
            status = resp.status
    except HTTPError as exc:
        exc.read()
        raise AlignError(f"识别接口失败 HTTP {exc.code}") from exc
    data = json.loads(body.decode("utf-8"))
    if status != 200:
        raise AlignError(f"识别接口失败 status {status}")
    return data


def api_key() -> str:
    for name in ("VOLC_SPEECH_API_KEY", "VOLC_TTS_API_KEY"):
        try:
            value = mini.load_key(name)
        except SystemExit:
            continue
        if value:
            return value
    raise AlignError("没有语音识别密钥")


def voiced_scripts(vo: Path, pages: list) -> list[tuple[Path, object]]:
    """Every oral file whose page titles are the ones on this recording."""
    titles = [str(item.get("title", "")).strip() for item in pages]
    found: list[tuple[Path, object]] = []
    for name in ("口播稿.md", "口播逐字稿.md"):
        path = vo / name
        if not path.is_file():
            continue
        doc = mini.parse_script(path)
        got = [page.title.strip() for page in doc.pages]
        if titles and got == titles:
            found.append((path, doc))
    return found


def script_ratios(doc, spans_by_page: list[list[tuple[str, float, float]]], max_line: int) -> list[float]:
    pause = ass.header_pause(doc)
    ratios: list[float] = []
    for page, spans in zip(doc.pages, spans_by_page):
        expected = expected_chars(page.speech, pause, max_line)
        heard = "".join(char for char, _, _ in spans)
        if not expected:
            ratios.append(1.0 if not heard else 0.0)
        else:
            ratios.append(SequenceMatcher(None, expected, heard).ratio())
    return ratios


def align_course(course: Path) -> dict:
    vo = course / "30-口播字幕"
    report_path = vo / "每页秒数.json"
    if not report_path.is_file():
        raise AlignError("缺 每页秒数.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    pages = report.get("pages") or []
    oral = vo / "口播稿.md"
    if oral.is_file():
        oral_doc = mini.parse_script(oral)
        oral_titles = [page.title.strip() for page in oral_doc.pages]
        audio_titles = [str(item.get("title", "")).strip() for item in pages]
        if oral_titles != audio_titles:
            raise AlignError("口播稿已改，页和成音对不上。先按口播稿重出成音。")
    scripts = voiced_scripts(vo, pages)
    if not oral.is_file() and not scripts:
        raise AlignError("没有和成音页名一致的口播")
    max_line = ass.max_line_for(course)
    key = api_key()
    cache_dir = vo / "_asr"
    cache_dir.mkdir(exist_ok=True)
    spans_by_page: list[list[tuple[str, float, float]]] = []
    for item in pages:
        num = str(item.get("page") or "")
        wav = vo / "_pages_wav" / f"{num}.wav"
        if not wav.is_file():
            raise AlignError(f"第{num}页缺 {wav.name}")
        cache = cache_dir / f"{num}.json"
        if cache.is_file():
            print(f"ASR {num} cache", flush=True)
            data = json.loads(cache.read_text(encoding="utf-8"))
        else:
            print(f"ASR {num} {wav.name}", flush=True)
            data = recognize(wav, key)
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        spans_by_page.append(asr_spans(data))
    if oral.is_file():
        ratios = script_ratios(oral_doc, spans_by_page, max_line)
        best_min = min(ratios) if ratios else 0.0
        if best_min < MIN_RATIO:
            raise AlignError(
                f"口播稿已改，和成音相似度 {best_min:.3f}。先重出成音，不要贴旧录音。"
            )
        script, doc = oral, oral_doc
    else:
        scored = []
        for path, doc in scripts:
            ratios = script_ratios(doc, spans_by_page, max_line)
            scored.append((min(ratios) if ratios else 0.0, path, doc, ratios))
        scored.sort(key=lambda row: row[0], reverse=True)
        best_min, script, doc, ratios = scored[0]
        if best_min < MIN_RATIO:
            detail = "；".join(f"{path.name} {score:.3f}" for score, path, _, _ in scored)
            raise AlignError(f"口播和成音对不上（{detail}）。不写时间，不烧成片。")
    pause = ass.header_pause(doc)
    print(f"script={script.name} pause={pause:g} pages={len(doc.pages)} min_ratio={best_min:.3f}", flush=True)
    updated = []
    for page, item, spans, ratio in zip(doc.pages, pages, spans_by_page, ratios):
        expected = expected_chars(page.speech, pause, max_line)
        duration = float(item["seconds"])
        words, _ = align(expected, spans, duration)
        holds = holds_for(page.speech, pause, max_line, words, duration)
        row = dict(item)
        row["speech_hash"] = mini.speech_hash(page.speech)
        row["words"] = words
        row["holds"] = holds
        row["align_ratio"] = round(ratio, 3)
        updated.append(row)
        print(f"  page={page.num} chars={len(expected)} asr={len(spans)} ratio={ratio:.3f}", flush=True)
    report["timing"] = "words"
    report["pause_seconds"] = pause
    report["pages"] = updated
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="用现成口播对齐逐字时间，不重配音")
    parser.add_argument("course_dir")
    args = parser.parse_args()
    course = Path(args.course_dir)
    if not course.is_dir():
        raise SystemExit(f"找不到课程目录 {course}")
    try:
        report = align_course(course)
    except AlignError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"pages": len(report["pages"]), "timing": report["timing"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
