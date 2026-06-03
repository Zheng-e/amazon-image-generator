from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import random as _random
import threading as _threading
import time as _time

import requests


ROOT_DIR = Path(__file__).resolve().parents[2]
API_FILE = ROOT_DIR / "api.txt"
ANALYSIS_API_FILE = ROOT_DIR / "api key.txt"
DATA_DIR = ROOT_DIR / "output" / "workbench"


@dataclass
class ApiSettings:
    text_api_url: str
    text_model: str
    text_keys: list[str]
    image_api_url: str
    image_model: str
    image_keys: list[str]
    analysis_models: dict[str, list[str]]


class KeyRotator:
    def __init__(self, keys: list[str]):
        self.keys = [key.strip() for key in keys if key.strip()]
        self.index = 0
        self._lock = _threading.Lock()

    def next(self) -> str:
        if not self.keys:
            raise RuntimeError("No API keys configured. Set TEXT_API_KEYS/IMAGE_API_KEYS or provide api.txt.")
        with self._lock:
            key = self.keys[self.index % len(self.keys)]
            self.index += 1
        return key


def _split_env_keys(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def _read_api_file(path: Path = API_FILE) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    if not path.exists():
        return groups
    current = ""
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("sk-"):
            if current:
                groups.setdefault(current, []).append(line)
            continue
        current = line
        groups.setdefault(current, [])
    return groups


def load_settings() -> ApiSettings:
    groups = _read_api_file(API_FILE)
    analysis_groups = _read_api_file(ANALYSIS_API_FILE)
    image_model = os.getenv("IMAGE_MODEL", "gpt-image-2")
    text_model = os.getenv("TEXT_MODEL", "gemini-3.1-flash-image-preview")
    return ApiSettings(
        text_api_url=os.getenv("TEXT_API_URL", "https://aifast.site/v1/chat/completions"),
        text_model=text_model,
        text_keys=_split_env_keys(os.getenv("TEXT_API_KEYS")) or groups.get(text_model, []) or groups.get("gemini-3.1-flash-image-preview", []),
        image_api_url=os.getenv("IMAGE_API_URL", "https://aifast.site/v1/images/edits"),
        image_model=image_model,
        image_keys=_split_env_keys(os.getenv("IMAGE_KEYS")) or _split_env_keys(os.getenv("IMAGE_API_KEYS")) or groups.get(image_model, []),
        analysis_models=analysis_groups,
    )


_session = requests.Session()
_text_rotators: dict[str, KeyRotator] = {}
_text_rotators_lock = _threading.Lock()
_image_rotators: dict[str, KeyRotator] = {}
_image_rotators_lock = _threading.Lock()


def _get_text_rotator(model: str, keys: list[str]) -> KeyRotator:
    clean_keys = [key.strip() for key in keys if key.strip()]
    with _text_rotators_lock:
        if model not in _text_rotators or _text_rotators[model].keys != clean_keys:
            _text_rotators[model] = KeyRotator(clean_keys)
        return _text_rotators[model]


def _keys_for_image_model(settings: ApiSettings, model: str) -> list[str]:
    groups = _read_api_file(API_FILE)
    analysis_groups = settings.analysis_models
    if model == settings.image_model:
        return settings.image_keys or groups.get(model, []) or analysis_groups.get(model, [])
    return groups.get(model, []) or analysis_groups.get(model, []) or (settings.image_keys if model == settings.image_model else [])


def _get_image_rotator(model: str, keys: list[str]) -> KeyRotator:
    clean_keys = [key.strip() for key in keys if key.strip()]
    with _image_rotators_lock:
        if model not in _image_rotators or _image_rotators[model].keys != clean_keys:
            _image_rotators[model] = KeyRotator(clean_keys)
        return _image_rotators[model]


_MAX_IMAGE_DIM = 1024
_IMAGE_QUALITY = 85


def image_to_data_url(path: Path) -> str:
    from PIL import Image as _PILImage

    img = _PILImage.open(path)
    w, h = img.size
    if max(w, h) > _MAX_IMAGE_DIM:
        scale = _MAX_IMAGE_DIM / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), _PILImage.LANCZOS)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_IMAGE_QUALITY)
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{data}"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def ensure_blank_canvas(size: int = 1024) -> Path:
    seed_dir = DATA_DIR / "_seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    path = seed_dir / f"blank_{size}.png"
    if path.exists() and path.stat().st_size > 0:
        return path
    raw = b"".join(b"\x00" + (b"\xff\xff\xff" * size) for _ in range(size))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 6))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    return path


def available_analysis_models() -> list[dict[str, Any]]:
    settings = load_settings()
    models = []
    for model, keys in settings.analysis_models.items():
        if keys:
            models.append({"model": model, "key_count": len(keys)})
    return models


def available_image_models() -> list[dict[str, Any]]:
    settings = load_settings()
    groups = _read_api_file(API_FILE)
    all_groups: dict[str, list[str]] = {**settings.analysis_models, **groups}
    preferred = ["gpt-image-2", "gemini-3.1-flash-image-preview"]
    models: list[dict[str, Any]] = []
    for model in preferred:
        keys = _keys_for_image_model(settings, model)
        if keys:
            api_type = "chat_completions_image" if "gemini" in model else "openai_images_edits"
            models.append({"model": model, "key_count": len(keys), "api_type": api_type})
    for model, keys in all_groups.items():
        if model in preferred or not keys:
            continue
        if "image" in model:
            api_type = "chat_completions_image" if "gemini" in model else "openai_images_edits"
            models.append({"model": model, "key_count": len(keys), "api_type": api_type})
    return models


def call_text_model(
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
    model: str | None = None,
    max_tokens: int = 4096,
) -> str:
    settings = load_settings()
    selected_model = model or settings.text_model
    keys = settings.analysis_models.get(selected_model) or (settings.text_keys if selected_model == settings.text_model else [])
    rotator = _get_text_rotator(selected_model, keys)
    body = {
        "model": selected_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    img_count = sum(1 for m in messages for c in (m.get("content") or []) if isinstance(c, dict) and c.get("type") == "image_url")
    print(f"[call_text_model] model={selected_model} images={img_count} payload={len(body_bytes) / 1024:.0f}KB")
    last_exc: Exception | None = None
    for attempt in range(4):
        key = rotator.next()
        try:
            resp = _session.post(
                settings.text_api_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                },
                json=body,
                timeout=180,
            )
            resp.raise_for_status()
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            print(f"[call_text_model] attempt {attempt + 1} failed: {exc}")
            if attempt < 3:
                _time.sleep(5 * (attempt + 1) + _random.uniform(0, 3))
                continue
            raise
    else:
        raise last_exc  # type: ignore[misc]
    result = resp.json()
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError(f"Text model returned no choices: {str(result)[:300]}")
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    if not content:
        raise RuntimeError(f"Text model response has no content: {str(result)[:300]}")
    return str(content).strip()


def _extract_b64_from_image_response(result: dict[str, Any]) -> str:
    data = result.get("data") or []
    if data and isinstance(data, list):
        first = data[0] or {}
        if first.get("b64_json"):
            return str(first["b64_json"])
        url = ((first.get("image_url") or {}).get("url") or first.get("url") or "")
        if isinstance(url, str) and url.startswith("data:image"):
            return url.split(",", 1)[1]

    choices = result.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        for item in message.get("images") or []:
            url = ((item.get("image_url") or {}).get("url") or item.get("url") or "")
            if isinstance(url, str) and url.startswith("data:image"):
                return url.split(",", 1)[1]
        content = message.get("content")
        if isinstance(content, str):
            match = __import__("re").search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", content)
            if match:
                return match.group(1)
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                url = ((part.get("image_url") or {}).get("url") or part.get("url") or "")
                if isinstance(url, str) and url.startswith("data:image"):
                    return url.split(",", 1)[1]
                text = part.get("text")
                if isinstance(text, str) and "data:image" in text:
                    match = __import__("re").search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", text)
                    if match:
                        return match.group(1)
    raise RuntimeError(f"Image model returned no image data: {str(result)[:500]}")


def _call_openai_image_edits(
    prompt: str,
    image_paths: list[Path],
    size: str,
    quality: str,
    model: str,
    keys: list[str],
) -> dict[str, Any]:
    settings = load_settings()
    rotator = _get_image_rotator(model, keys)
    paths = list(image_paths) or [ensure_blank_canvas()]
    last_exc: Exception | None = None
    for attempt in range(3):
        key = rotator.next()
        files: list[tuple[str, tuple[str, Any, str]]] = []
        try:
            for img_path in paths:
                mime = mimetypes.guess_type(img_path.name)[0] or "image/png"
                files.append(("image", (img_path.name, img_path.open("rb"), mime)))
            resp = requests.post(
                settings.image_api_url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {key}",
                },
                files=files,
                data={
                    "model": model,
                    "prompt": prompt,
                    "size": size,
                    "n": "1",
                },
                timeout=360,
            )
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as exc:
                detail = resp.text[:1000] if resp.text else ""
                raise requests.exceptions.HTTPError(
                    f"{exc}; response={detail}",
                    response=resp,
                ) from exc
            result = resp.json()
            return {
                "b64_json": _extract_b64_from_image_response(result),
                "model": model,
                "api_type": "openai_images_edits",
                "params": {"size": size},
            }
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            print(f"[_call_openai_image_edits] attempt {attempt + 1} failed: {exc}")
            if attempt < 2:
                _time.sleep(5 * (attempt + 1) + _random.uniform(0, 3))
                continue
            raise
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            body = ""
            try:
                body = exc.response.text[:500] if exc.response is not None else ""
            except Exception:
                pass
            is_transient = status == 500 and ("unexpected end of JSON" in body or "bad_response_body" in body)
            if is_transient and attempt < 2:
                last_exc = exc
                print(f"[_call_openai_image_edits] attempt {attempt + 1} transient 500: {body[:200]}")
                _time.sleep(5 * (attempt + 1) + _random.uniform(0, 3))
                continue
            raise
        finally:
            for _, file_tuple in files:
                file_tuple[1].close()
    raise last_exc  # type: ignore[misc]


def _call_chat_image_model(
    prompt: str,
    image_paths: list[Path],
    model: str,
    keys: list[str],
) -> dict[str, Any]:
    settings = load_settings()
    rotator = _get_image_rotator(model, keys)
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for img_path in image_paths[:6]:
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(img_path)}})
    body = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": content}],
        "extra_body": {
            "google": {
                "image_config": {
                    "aspect_ratio": "1:1",
                    "image_size": "1K",
                }
            }
        },
    }
    last_exc: Exception | None = None
    for attempt in range(3):
        key = rotator.next()
        resp = _session.post(
            settings.text_api_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": key,
            },
            json=body,
            timeout=360,
        )
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            detail = resp.text[:1000] if resp.text else ""
            status = exc.response.status_code if exc.response is not None else 0
            is_transient = status == 500 and ("unexpected end of JSON" in detail or "bad_response_body" in detail)
            if is_transient and attempt < 2:
                last_exc = exc
                print(f"[_call_chat_image_model] attempt {attempt + 1} transient 500: {detail[:200]}")
                _time.sleep(5 * (attempt + 1) + _random.uniform(0, 3))
                continue
            raise requests.exceptions.HTTPError(f"{exc}; response={detail}", response=resp) from exc
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            print(f"[_call_chat_image_model] attempt {attempt + 1} failed: {exc}")
            if attempt < 2:
                _time.sleep(5 * (attempt + 1) + _random.uniform(0, 3))
                continue
            raise
        result = resp.json()
        return {
            "b64_json": _extract_b64_from_image_response(result),
            "model": model,
            "api_type": "chat_completions_image",
            "params": {"aspect_ratio": "1:1", "image_size": "1K"},
        }
    raise last_exc  # type: ignore[misc]


def call_image_model(
    prompt: str,
    image_paths: list[Path],
    size: str = "1024x1024",
    quality: str = "high",
    model: str | None = None,
) -> dict[str, Any]:
    settings = load_settings()
    selected_model = model or settings.image_model
    keys = _keys_for_image_model(settings, selected_model)
    if "gemini" in selected_model:
        return _call_chat_image_model(prompt, image_paths, selected_model, keys)
    return _call_openai_image_edits(prompt, image_paths, size, quality, selected_model, keys)
