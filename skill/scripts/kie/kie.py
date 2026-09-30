#!/usr/bin/env python3
"""Kie.ai unified CLI. Reads KIE_API_KEY from env files. Never prints the key."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(next(d for d in Path(__file__).resolve().parents if (d / "_lib" / "mini.py").is_file()) / "_lib"))
import mini as _mini
ROOT = _mini.work_root()
CATALOG_PATH = Path(__file__).resolve().parent / "catalog.yaml"
DEFAULTS_PATH = ROOT / ".env"
ENV_CANDIDATES = [
    ROOT / ".env",
    Path.cwd() / ".env",
    Path.home() / ".baoyu-skills/.env",
]
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_env() -> None:
    for path in ENV_CANDIDATES:
        load_dotenv(path)


def require_key() -> str:
    key = os.environ.get("KIE_API_KEY", "").strip()
    if not key:
        raise SystemExit("KIE_API_KEY 未配置。把它写进仓库根目录 .env（照 .env.example）")
    return key


def base_url() -> str:
    return os.environ.get("KIE_API_BASE_URL", "https://api.kie.ai").rstrip("/")


def upload_base_url() -> str:
    return os.environ.get("KIE_UPLOAD_BASE_URL", "https://kieai.redpandaai.co").rstrip("/")


def mask(text: str) -> str:
    key = os.environ.get("KIE_API_KEY", "")
    if key and key in text:
        return text.replace(key, "***")
    return text


def request_json(
    method: str,
    url: str,
    body: dict | None = None,
    extra_headers: dict | None = None,
    auth: str = "bearer",
    timeout: int = 60,
) -> dict:
    key = require_key()
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": BROWSER_UA}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if auth == "x-api-key":
        headers["X-Api-Key"] = key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {key}"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} {mask(raw)}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(f"请求失败: {exc.reason}") from None


def emit(payload) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def walk_http_urls(obj) -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for value in obj.values():
            found.extend(walk_http_urls(value))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(walk_http_urls(value))
    elif isinstance(obj, str) and obj.startswith("http"):
        found.append(obj)
    return found


def extract_result_urls(payload) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        for key in ("resultUrls", "result_urls", "resultUrl", "fileUrl", "downloadUrl", "url", "urls", "images"):
            value = data.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return [value]
            if isinstance(value, list):
                urls = [item for item in value if isinstance(item, str) and item.startswith("http")]
                if urls:
                    return urls
        raw = data.get("resultJson")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if raw:
            nested = extract_result_urls({"data": raw} if not (isinstance(raw, dict) and "data" in raw) else raw)
            if nested:
                return nested
    return [url for url in walk_http_urls(payload) if "api.kie.ai" not in url]


def upload_local(path: Path, upload_path: str = "agentos") -> str:
    key = require_key()
    boundary = "----KieUploadBoundary7f3a9c"
    filename = path.name
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"uploadPath\"\r\n\r\n{upload_path}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"fileName\"\r\n\r\n{filename}\r\n".encode(),
        f"--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(
        f"{upload_base_url()}/api/file-stream-upload",
        data=b"".join(parts),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": BROWSER_UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code} {mask(exc.read().decode('utf-8', errors='replace'))}") from None
    urls = extract_result_urls(payload)
    if not urls:
        raise SystemExit("上传成功但没有可用 URL")
    return urls[0]


def normalize_refs(refs: list[str]) -> list[str]:
    out: list[str] = []
    for item in refs:
        path = Path(item)
        if path.is_file():
            out.append(upload_local(path))
        else:
            out.append(item)
    return out


def fetch_bytes(url: str, use_auth: bool = False) -> bytes:
    headers = {"User-Agent": BROWSER_UA, "Accept": "*/*"}
    if use_auth:
        headers["Authorization"] = f"Bearer {require_key()}"
    req = urllib.request.Request(str(url), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def save_result(payload: dict, out: str) -> dict:
    urls = extract_result_urls(payload)
    if not urls:
        raise SystemExit("任务成功但没有成品 URL，无法保存")
    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    candidates = [urls[0]]
    try:
        data = request_json("POST", f"{base_url()}/api/v1/common/download-url", {"url": urls[0]})
        download_url = data.get("data") or urls[0]
        if isinstance(download_url, dict):
            download_url = download_url.get("url") or download_url.get("downloadUrl") or urls[0]
        if download_url and str(download_url) not in candidates:
            candidates.insert(0, str(download_url))
    except SystemExit:
        pass
    last_error = None
    for url in candidates:
        for use_auth in (False, True):
            try:
                dest.write_bytes(fetch_bytes(url, use_auth=use_auth))
                payload = dict(payload)
                payload["saved"] = str(dest)
                payload["bytes"] = dest.stat().st_size
                return payload
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code} {mask(exc.read().decode('utf-8', errors='replace'))}"
            except urllib.error.URLError as exc:
                last_error = f"请求失败: {exc.reason}"
    raise SystemExit(f"成品下载失败: {last_error or 'unknown'}；原始地址 {mask(urls[0])}")


def parse_kv(items: list[str] | None) -> dict:
    out: dict = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"参数格式应为 key=value: {item}")
        key, value = item.split("=", 1)
        if value.lower() in {"true", "false"}:
            out[key] = value.lower() == "true"
        else:
            try:
                out[key] = json.loads(value)
            except json.JSONDecodeError:
                out[key] = value
    return out


def cmd_credit(_: argparse.Namespace) -> None:
    data = request_json("GET", f"{base_url()}/api/v1/chat/credit")
    emit({"ok": data.get("code") == 200, "credits": data.get("data"), "raw": data})


def cmd_catalog(_: argparse.Namespace) -> None:
    text = CATALOG_PATH.read_text(encoding="utf-8")
    print(text)


def cmd_tts(_: argparse.Namespace) -> None:
    raise SystemExit(
        "Kie TTS 不是 VideoBot/Remotion 默认旁白。\n"
        f"请用: {sys.executable} {ROOT / 'tools/router/router.py'} tts --text '...' --out out.mp3 --yes\n"
        "studio 用: python3 AgentOS/VideoBot/studio/scripts/tts.py <稿.txt> <out.wav> --yes\n"
        "只有老板点名「用 Kie / ElevenLabs / Gemini TTS」才走市场模型。"
    )


def cmd_create(args: argparse.Namespace) -> None:
    payload = {"model": args.model, "input": {}}
    if args.input_json:
        payload["input"] = json.loads(Path(args.input_json).read_text(encoding="utf-8") if Path(args.input_json).is_file() else args.input_json)
    payload["input"].update(parse_kv(args.input))
    if args.callback:
        payload["callBackUrl"] = args.callback
    data = request_json("POST", f"{base_url()}/api/v1/jobs/createTask", payload)
    emit(data)


def cmd_status(args: argparse.Namespace) -> None:
    family = args.family
    if family == "4o":
        url = f"{base_url()}/api/v1/gpt4o-image/record-info?taskId={urllib.parse.quote(args.task)}"
    elif family == "veo":
        url = f"{base_url()}/api/v1/veo/record-info?taskId={urllib.parse.quote(args.task)}"
    else:
        url = f"{base_url()}/api/v1/jobs/recordInfo?taskId={urllib.parse.quote(args.task)}"
    emit(request_json("GET", url))


def wait_market(task_id: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    delay = 2.0
    last = {}
    while time.time() < deadline:
        last = request_json("GET", f"{base_url()}/api/v1/jobs/recordInfo?taskId={urllib.parse.quote(task_id)}")
        state = str((last.get("data") or {}).get("state") or "").lower()
        if state == "success":
            return last
        if state == "fail":
            data = last.get("data") or {}
            raise SystemExit(
                f"Kie 任务失败 taskId={task_id} code={data.get('failCode') or data.get('errorCode')} "
                f"{data.get('failMsg') or data.get('errorMessage') or ''}".strip()
            )
        time.sleep(delay)
        delay = min(delay * 1.4, 12)
    raise SystemExit(f"等待超时，taskId={task_id}。可用 kie status --task {task_id} 再查")


def wait_4o(task_id: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    delay = 2.0
    last = {}
    while time.time() < deadline:
        last = request_json(
            "GET",
            f"{base_url()}/api/v1/gpt4o-image/record-info?taskId={urllib.parse.quote(task_id)}",
        )
        status = str((last.get("data") or {}).get("status") or "").upper()
        if status in {"SUCCESS", "CREATE_TASK_FAILED", "GENERATE_FAILED"}:
            return last
        time.sleep(delay)
        delay = min(delay * 1.4, 12)
    raise SystemExit(f"等待超时，taskId={task_id}")


def cmd_image(args: argparse.Namespace) -> None:
    model = args.model
    if not str(model).startswith("gpt-image-2"):
        raise SystemExit(f"出图只允许 gpt-image-2，收到: {model}")
    args.ref = normalize_refs(args.ref)
    if args.out and not args.wait:
        args.wait = True

    payload = {"model": model, "input": {"prompt": args.prompt}}
    if args.aspect:
        payload["input"]["aspect_ratio"] = args.aspect
    payload["input"]["resolution"] = args.quality or "2K"
    if args.ref:
        payload["model"] = "gpt-image-2-image-to-image"
        payload["input"]["input_urls"] = args.ref
    data = request_json("POST", f"{base_url()}/api/v1/jobs/createTask", payload)
    if args.wait:
        task_id = (data.get("data") or {}).get("taskId")
        if not task_id:
            emit(data)
            return
        data = wait_market(task_id, args.timeout)
        print(f"taskId={task_id}", file=sys.stderr)
    if args.out:
        data = save_result(data, args.out)
    emit(data)


def cmd_video(args: argparse.Namespace) -> None:
    body = {
        "prompt": args.prompt,
        "model": args.model,
        "aspect_ratio": args.aspect or "16:9",
    }
    if args.ref:
        body["imageUrls"] = args.ref
    data = request_json("POST", f"{base_url()}/api/v1/veo/generate", body)
    emit(data)


def cmd_chat(args: argparse.Namespace) -> None:
    family = args.family
    if family == "grok":
        body = {
            "model": args.model,
            "input": [{"role": "user", "content": args.prompt}],
            "stream": False,
        }
        emit(request_json("POST", f"{base_url()}/grok/v1/responses", body))
        return
    if family == "claude":
        body = {
            "model": args.model,
            "max_tokens": args.max_tokens,
            "messages": [{"role": "user", "content": args.prompt}],
            "stream": False,
        }
        emit(request_json("POST", f"{base_url()}/claude/v1/messages", body, auth="x-api-key"))
        return
    if family == "gemini":
        body = {
            "model": args.model,
            "messages": [{"role": "user", "content": args.prompt}],
            "stream": False,
        }
        emit(request_json("POST", f"{base_url()}/gemini-3-6-flash-openai/v1/chat/completions", body))
        return
    if family == "gpt":
        body = {
            "model": args.model,
            "input": [{"role": "user", "content": args.prompt}],
            "stream": False,
        }
        emit(request_json("POST", f"{base_url()}/codex/v1/responses", body))
        return
    raise SystemExit(f"未知 chat family: {family}")


def cmd_upload(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"文件不存在: {path}")
    key = require_key()
    boundary = "----KieUploadBoundary7f3a9c"
    filename = args.name or path.name
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"uploadPath\"\r\n\r\n{args.path}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"fileName\"\r\n\r\n{filename}\r\n".encode(),
        f"--{boundary}--\r\n".encode(),
    ]
    data = b"".join(parts)
    url = f"{upload_base_url()}/api/file-stream-upload"
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": BROWSER_UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            emit(json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code} {mask(exc.read().decode('utf-8', errors='replace'))}") from None


def cmd_download(args: argparse.Namespace) -> None:
    data = request_json("POST", f"{base_url()}/api/v1/common/download-url", {"url": args.url})
    download_url = data.get("data") or args.url
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        download_url,
        headers={"Authorization": f"Bearer {require_key()}", "User-Agent": BROWSER_UA},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        out.write_bytes(resp.read())
    emit({"saved": str(out), "bytes": out.stat().st_size, "source": mask(str(download_url))})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kie.ai 统一入口")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("credit", help="查积分")
    p.set_defaults(func=cmd_credit)

    p = sub.add_parser("catalog", help="打印能力目录")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("create", help="Market createTask")
    p.add_argument("--model", required=True)
    p.add_argument("--input", action="append", default=[], help="key=value，可重复")
    p.add_argument("--input-json")
    p.add_argument("--callback")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("status", help="查任务")
    p.add_argument("--task", required=True)
    p.add_argument("--family", choices=["market", "4o", "veo"], default="market")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("image", help="出图 / 改图")
    p.add_argument("--prompt", required=True)
    p.add_argument("--model", default="gpt-image-2-text-to-image")
    p.add_argument("--aspect")
    p.add_argument("--size", help="4o 画幅：1:1 / 3:2 / 2:3")
    p.add_argument("--quality", default="2K")
    p.add_argument("--ref", action="append", default=[], help="参考图公网 URL，可重复")
    p.add_argument("--input", action="append", default=[])
    p.add_argument("--variants", type=int, default=1)
    p.add_argument("--enhance", action="store_true")
    p.add_argument("--fallback", action="store_true")
    p.add_argument("--fallback-model", default="FLUX_MAX")
    p.add_argument("--wait", action="store_true")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--out", help="等待完成后下载第一张到本地")
    p.set_defaults(func=cmd_image)

    p = sub.add_parser("tts", help="旁白请走 router.py tts，这里只提示不要用错")
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("video", help="Veo 文生/图生视频")
    p.add_argument("--prompt", required=True)
    p.add_argument("--model", default="veo3")
    p.add_argument("--aspect", default="16:9")
    p.add_argument("--ref", action="append", default=[])
    p.set_defaults(func=cmd_video)

    p = sub.add_parser("chat", help="对话模型")
    p.add_argument("--prompt", required=True)
    p.add_argument("--family", choices=["grok", "claude", "gemini", "gpt"], default="grok")
    p.add_argument("--model", default="grok-4-5")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.set_defaults(func=cmd_chat)

    p = sub.add_parser("upload", help="上传本地文件换公网 URL")
    p.add_argument("--file", required=True)
    p.add_argument("--path", default="agentos")
    p.add_argument("--name")
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("download", help="把 Kie 成品落到本地")
    p.add_argument("--url", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_download)
    return parser


def main() -> None:
    load_env()
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
