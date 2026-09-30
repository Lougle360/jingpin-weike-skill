# -*- coding: utf-8 -*-
"""Per-page TTS from 口播稿.md, lossless WAV concat, real per-page seconds.

    gen_pages_vo.py <course_dir> [--brand 谷子] [--pages 06,07] [--yes] [--env PATH]

Voice/provider settings come from config/品牌包/<brand>/音色.md. API keys come
from environment variables or --env file and are never printed. Paid call:
refuses to render more than one page without --yes.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini  # noqa: E402

NOIZ_TTS_URL = "https://noiz.ai/v1/text-to-speech"
VOLC_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
MAX_CHARS = 5000
STAGE_PAUSE = re.compile(r"（停顿）")
STAGE_NOTE = re.compile(r"（互动）|（讲案例）")
PAUSE_SAY = re.compile(r"^\s*(停\s*([一二三四五六七八九十两零\d]+)\s*秒[。.]?)")
CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def parse_pause_number(raw: str, default: float = 20.0) -> float:
    raw = raw.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return float(raw)
    if raw == "十":
        return 10.0
    if raw.startswith("十"):
        return 10.0 + CN_DIGIT.get(raw[1:], 0)
    if raw.endswith("十") and len(raw) == 2:
        return float(CN_DIGIT.get(raw[0], 0) * 10)
    if "十" in raw:
        left, right = raw.split("十", 1)
        return float(CN_DIGIT.get(left, 1) * 10 + CN_DIGIT.get(right, 0))
    return float(CN_DIGIT.get(raw, default) or default)


def header_pause_seconds(doc) -> float:
    raw = (doc.header.get("停顿") or doc.header.get("停顿秒数") or "").strip()
    hit = re.search(r"(\d+(?:\.\d+)?)", raw)
    return float(hit.group(1)) if hit else 0.0


def tts_segments(text: str, default_pause: float) -> list[tuple[str, object]]:
    """Split oral text into speech / silence. Stage directions are not spoken."""
    text = STAGE_NOTE.sub("", text)
    parts = STAGE_PAUSE.split(text)
    if len(parts) == 1:
        body = text.strip()
        return [("speech", body)] if body else []
    out: list[tuple[str, object]] = []
    first = parts[0].strip()
    if first:
        out.append(("speech", first))
    for piece in parts[1:]:
        hit = PAUSE_SAY.match(piece)
        if hit:
            out.append(("speech", hit.group(1).strip()))
            out.append(("silence", parse_pause_number(hit.group(2), default_pause or 20)))
            rest = piece[hit.end() :].strip()
        else:
            if default_pause:
                out.append(("silence", default_pause))
            rest = piece.strip()
        if rest:
            out.append(("speech", rest))
    return out


def write_silence(dest: Path, seconds: float, sample_rate: int) -> None:
    mini.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r={sample_rate}:cl=mono",
            "-t", f"{seconds:.3f}",
            "-c:a", "pcm_s16le",
            str(dest.resolve()),
        ]
    )


def split_if_needed(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    parts: list[str] = []
    buf = ""
    for piece in text.replace("。", "。\n").replace("？", "？\n").replace("！", "！\n").split("\n"):
        piece = piece.strip()
        if not piece:
            continue
        if len(buf) + len(piece) <= MAX_CHARS:
            buf += piece
        else:
            if buf:
                parts.append(buf)
            buf = piece
    if buf:
        parts.append(buf)
    return parts


def multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----NoizBoundary" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("ascii"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), boundary


def noiz_tts(api_key: str, voice_id: str, text: str) -> bytes:
    body, boundary = multipart(
        {"text": text, "voice_id": voice_id, "output_format": "wav", "target_lang": "zh"}
    )
    req = Request(
        NOIZ_TTS_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "audio/wav, application/json",
        },
    )
    try:
        with urlopen(req, timeout=180) as resp:
            status = resp.status
            data = resp.read()
    except HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: {exc.read()[:600]!r}") from exc
    except URLError as exc:
        raise SystemExit(f"network error: {exc}") from exc
    if status != 200 or not data.startswith(b"RIFF") or b"WAVE" not in data[:16]:
        raise SystemExit(f"not wav: status={status} head={data[:120]!r}")
    return data


def _sentence_words(sentence: object) -> list[dict]:
    if isinstance(sentence, list):
        words: list[dict] = []
        for item in sentence:
            words.extend(_sentence_words(item))
        return words
    if not isinstance(sentence, dict):
        return []
    words = []
    for word in sentence.get("words") or []:
        if not isinstance(word, dict) or not str(word.get("word") or "").strip():
            continue
        try:
            start = float(word["startTime"])
            end = float(word["endTime"])
        except (KeyError, TypeError, ValueError):
            continue
        if end < start:
            end = start
        words.append({"word": str(word["word"]), "start": start, "end": end})
    return words


def decode_volc_stream(lines) -> tuple[bytes, list[dict]]:
    """Decode audio plus word timestamps from JSONL or SSE response lines."""
    audio = bytearray()
    words: list[dict] = []
    events = 0
    for raw in lines:
        line = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit("豆包 TTS 返回了无法解析的流式 JSON") from exc
        events += 1
        chunk = event.get("data")
        if chunk:
            try:
                audio.extend(base64.b64decode(chunk))
            except (ValueError, binascii.Error) as exc:
                raise SystemExit("豆包 TTS 返回了无效的 Base64 音频片段") from exc
        incoming = _sentence_words(event.get("sentence"))
        if incoming:
            words.extend(incoming)
        sequence = event.get("sequence")
        if isinstance(sequence, int) and sequence < 0:
            break
    if not audio:
        raise SystemExit(f"豆包 TTS 未返回音频数据（events={events}）")
    words.sort(key=lambda item: (item["start"], item["end"]))
    return bytes(audio), words


def parse_int_field(raw: str, default: int | None = None) -> int | None:
    hit = re.search(r"-?\d+", raw or "")
    return int(hit.group(0)) if hit else default


def volc_additions(voice: dict[str, str]) -> str:
    extra: dict[str, object] = {}
    model_type = parse_int_field(voice.get("model_type", ""))
    if model_type is not None:
        extra["model_type"] = model_type
    instruction = (voice.get("合成指令") or "").strip()
    if instruction:
        extra["context_texts"] = [instruction]
    return json.dumps(extra, ensure_ascii=False) if extra else ""


def volc_req_params(voice: dict[str, str], text: str) -> dict[str, object]:
    audio_params: dict[str, object] = {
        "format": voice.get("音频格式", "mp3"),
        "sample_rate": int(voice.get("采样率", "32000")),
        "bit_rate": int(voice.get("比特率", "128000")),
        "enable_subtitle": True,
    }
    speech_rate = parse_int_field(voice.get("speech_rate", ""))
    loudness_rate = parse_int_field(voice.get("loudness_rate", ""))
    if speech_rate is not None:
        audio_params["speech_rate"] = speech_rate
    if loudness_rate is not None:
        audio_params["loudness_rate"] = loudness_rate
    params: dict[str, object] = {
        "text": text,
        "speaker": voice["voice_id"],
        "model": voice.get("model", "seed-tts-2.0-standard"),
        "audio_params": audio_params,
    }
    additions = volc_additions(voice)
    if additions:
        params["additions"] = additions
    return params


def shift_words(words: list[dict], offset: float, limit: float) -> list[dict]:
    """Move one TTS session's timestamps onto the page timeline."""
    shifted = []
    for word in words:
        start = float(word["start"]) + offset
        end = min(float(word["end"]) + offset, offset + limit)
        if end < start:
            end = start
        shifted.append({"word": str(word["word"]), "start": round(start, 3), "end": round(end, 3)})
    return shifted


def volc_tts(api_key: str, voice: dict[str, str], text: str) -> tuple[bytes, list[dict]]:
    request_id = str(uuid.uuid4())
    payload = {
        "user": {"uid": voice.get("uid", "guzi-podcast")},
        "req_params": volc_req_params(voice, text),
    }
    req = Request(
        voice.get("接口", VOLC_TTS_URL),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": voice.get("resource_id", "seed-icl-2.0"),
            "X-Api-Request-Id": request_id,
        },
    )
    try:
        with urlopen(req, timeout=180) as resp:
            return decode_volc_stream(resp)
    except HTTPError as exc:
        raise SystemExit(f"豆包 TTS HTTP {exc.code}（request_id={request_id}）") from exc
    except URLError as exc:
        raise SystemExit(f"豆包 TTS 网络错误: {exc.reason}") from exc


def mp3_to_wav(source: Path, dest: Path, sample_rate: int = 32000) -> None:
    mini.run(
        [
            "ffmpeg", "-y", "-i", str(source.resolve()), "-vn", "-ac", "1",
            "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dest.resolve()),
        ]
    )


def concat_copy(parts: list[Path], dest: Path) -> None:
    """ffmpeg concat demuxer; run inside the wav dir so the list only holds ASCII names."""
    work = parts[0].parent
    listing = work / "_concat.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="ascii")
    dest.parent.mkdir(parents=True, exist_ok=True)
    mini.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing.name, "-c", "copy", str(dest.resolve())],
        cwd=work,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_dir", type=Path)
    parser.add_argument("--brand", default="谷子")
    parser.add_argument("--pages", default="", help="只出这些页，逗号分隔，如 06,07")
    parser.add_argument("--yes", action="store_true", help="确认付费出整课")
    parser.add_argument("--env", type=Path, default=None, help=".env 文件路径")
    parser.add_argument("--skip-existing", action="store_true", help="已有页 wav 不重出")
    args = parser.parse_args()

    voice = mini.read_table(mini.brand_dir(args.brand) / "音色.md")
    if voice.get("状态") != "已登记":
        raise SystemExit("音色未登记，停。")
    voice_id = voice.get("voice_id", "")
    if not voice_id:
        raise SystemExit("音色.md 缺 voice_id")

    oral_script = args.course_dir / "30-口播字幕" / "口播稿.md"
    legacy_script = args.course_dir / "30-口播字幕" / "口播逐字稿.md"
    if not oral_script.is_file() and legacy_script.is_file():
        oral_script = legacy_script
    if not oral_script.is_file():
        raise SystemExit("缺 30-口播字幕/口播稿.md；先完成口播稿审核。")
    doc = mini.parse_script(oral_script)
    if not doc.pages:
        raise SystemExit("口播稿无分页")
    wanted = {p.strip().zfill(2) for p in args.pages.split(",") if p.strip()}
    targets = [p for p in doc.pages if not wanted or p.num in wanted]
    if not targets:
        raise SystemExit(f"--pages {args.pages} 没匹配到页")

    out_dir = args.course_dir / "30-口播字幕"
    wav_dir = out_dir / "_pages_wav"
    wav_dir.mkdir(parents=True, exist_ok=True)

    provider = voice.get("供应商", "Noiz").lower()
    is_volc = "豆包" in provider or "火山" in provider or "volc" in provider
    if is_volc:
        try:
            api_key = mini.load_key("VOLC_TTS_API_KEY", args.env)
        except SystemExit:
            api_key = mini.load_key("VOLC_SPEECH_API_KEY", args.env)
    else:
        api_key = mini.load_key("NOIZ_API_KEY", args.env)

    sample_rate = int(voice.get("采样率", "32000"))
    default_pause = header_pause_seconds(doc)

    def timing_current(page) -> bool:
        wav = wav_dir / f"{page.num}.wav"
        path = wav_dir / f"{page.num}.timing.json"
        if not wav.is_file() or not path.is_file():
            return False
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        same_text = saved.get("speech_hash") == mini.speech_hash(page.speech)
        same_pause = abs(float(saved.get("pause_seconds", -1)) - default_pause) <= 0.01
        has_words = bool(saved.get("words")) or not page.speech.strip()
        if not (same_text and same_pause and has_words):
            return False
        spoken = "".join(
            ch for ch in STAGE_NOTE.sub("", page.speech) if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", ch)
        )
        heard = "".join(
            ch for item in (saved.get("words") or []) for ch in str(item.get("word") or "") if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", ch)
        )
        return spoken == heard

    to_render = [p for p in targets if not (args.skip_existing and timing_current(p))]
    if len(to_render) > 1 and not args.yes:
        raise SystemExit(f"将付费出声 {len(to_render)} 页。确认后加 --yes；试听单页用 --pages NN。")
    for p in to_render:
        if not is_volc:
            raise SystemExit("当前音色没有逐字时间，停止。不能按字数估字幕。")
        segments = tts_segments(p.speech, default_pause)
        chunk_files: list[Path] = []
        page_words: list[dict] = []
        holds: list[dict] = []
        offset = 0.0
        print(f"page {p.num} chars={len(p.speech)} segs={len(segments)}", flush=True)
        piece_i = 0
        for kind, payload in segments:
            if kind == "silence":
                piece_i += 1
                cp = wav_dir / f"{p.num}-{piece_i:02d}.wav"
                write_silence(cp, float(payload), sample_rate)
                chunk_files.append(cp)
                duration = mini.probe_seconds(cp)
                holds.append({"start": round(offset, 3), "end": round(offset + duration, 3)})
                offset += duration
                continue
            for chunk in split_if_needed(str(payload)):
                piece_i += 1
                cp = wav_dir / f"{p.num}-{piece_i:02d}.wav"
                mp3 = cp.with_suffix(".mp3")
                audio, chunk_words = volc_tts(api_key, voice, chunk)
                if not chunk_words:
                    raise SystemExit(f"第{p.num}页豆包没有返回逐字时间，停止。不能按字数估字幕。")
                mp3.write_bytes(audio)
                mp3_to_wav(mp3, cp, sample_rate)
                chunk_files.append(cp)
                duration = mini.probe_seconds(cp)
                page_words.extend(shift_words(chunk_words, offset, duration))
                offset += duration
        page_wav = wav_dir / f"{p.num}.wav"
        if len(chunk_files) == 1:
            page_wav.write_bytes(chunk_files[0].read_bytes())
        elif chunk_files:
            concat_copy(chunk_files, page_wav)
        else:
            raise SystemExit(f"第{p.num}页没有可配的口播")
        timing = {
            "speech_hash": mini.speech_hash(p.speech),
            "pause_seconds": default_pause,
            "words": page_words,
            "holds": holds,
        }
        (wav_dir / f"{p.num}.timing.json").write_text(
            json.dumps(timing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"page {p.num} seconds={mini.probe_seconds(page_wav):.3f} words={len(page_words)}", flush=True)

    # Only assemble the full track when every page exists.
    all_wavs = [wav_dir / f"{p.num}.wav" for p in doc.pages]
    missing = [w.name for w in all_wavs if not w.is_file()]
    if missing:
        print(f"未拼接：还缺 {missing}")
        return 0

    final = out_dir / "口播.wav"
    concat_copy(all_wavs, final)
    page_rows = []
    for page, wav in zip(doc.pages, all_wavs):
        timing_path = wav_dir / f"{page.num}.timing.json"
        if not timing_path.is_file():
            raise SystemExit(f"第{page.num}页没有逐字时间，不能按字数估字幕。请重出该页。")
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
        if timing.get("speech_hash") != mini.speech_hash(page.speech):
            raise SystemExit(f"第{page.num}页口播已改，这一页成音还是旧稿。请重出该页。")
        if abs(float(timing.get("pause_seconds", -1)) - default_pause) > 0.01:
            raise SystemExit(f"第{page.num}页成音的停顿是旧的。请重出该页。")
        page_rows.append(
            {
                "page": page.num,
                "title": page.title,
                "chars": len(page.speech),
                "seconds": round(mini.probe_seconds(wav), 3),
                "path": wav.name,
                "speech_hash": timing["speech_hash"],
                "words": timing.get("words") or [],
                "holds": timing.get("holds") or [],
            }
        )
    report = {
        "voice_id": voice_id,
        "timing": "words",
        "pause_seconds": default_pause,
        "pages": page_rows,
        "total_seconds": round(mini.probe_seconds(final), 3),
    }
    (out_dir / "每页秒数.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total_seconds": report["total_seconds"], "pages": len(report["pages"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
