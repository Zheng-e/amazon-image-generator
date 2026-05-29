from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import requests

try:
    from fastapi import HTTPException
except Exception:  # pragma: no cover - lets pure helper tests run without FastAPI installed.
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(f"{status_code}: {detail}")
            self.status_code = status_code
            self.detail = detail


RAG_USAGE_TAGS: dict[str, str] = {
    "scene_reference": "场景参考",
    "pose_reference": "姿势参考",
    "composition_reference": "构图参考",
    "color_reference": "色调参考",
    "white_main_reference": "白底主图参考",
    "competitor_fit_reference": "竞品上身参考",
}

STAGE_LABELS: dict[str, dict[str, Any]] = {
    "model_on_body": {"image_no": 1, "title": "模特上身图"},
    "scene_model": {"image_no": 2, "title": "场景模特图"},
    "angle_3": {"image_no": 3, "title": "角度图 1"},
    "angle_4": {"image_no": 4, "title": "角度图 2"},
    "angle_5": {"image_no": 5, "title": "角度图 3"},
    "angle_6": {"image_no": 6, "title": "角度图 4"},
    "outfit": {"image_no": 7, "title": "穿搭图"},
    "white_main": {"image_no": 8, "title": "白底主图"},
    "white_back": {"image_no": 9, "title": "背面白底图"},
}

RAG_FORBIDDEN_ASPECTS: list[str] = [
    "人物身份", "人物长相", "服装款式", "品牌", "文字", "水印", "无关道具", "无关背景元素",
]

# rag_role → 自动注入的工作流步骤
RAG_ROLE_TO_STAGES: dict[str, list[str]] = {
    "model": ["model_on_body"],
    "scene_style": ["scene_model"],
    "pose": ["angle_3", "angle_4", "angle_5", "angle_6", "white_main", "white_back"],
    "accessory": ["outfit"],
}

# rag_role → 对应的 allowed aspects（用于提示词注入）
RAG_ROLE_ALLOWED_ASPECTS: dict[str, list[str]] = {
    "model": ["人物面部特征", "发型", "身材比例", "肤色"],
    "scene_style": ["背景环境", "场景氛围", "色调", "光影", "整体风格"],
    "pose": ["人物姿势", "身体朝向", "表情", "动作节奏"],
    "accessory": ["配饰款式", "穿搭搭配", "道具"],
}

RAG_ROLE_LABELS: dict[str, str] = {
    "model": "模特参考",
    "scene_style": "场景风格参考",
    "pose": "姿势参考",
    "accessory": "配饰参考",
}

def rag_base_url() -> str:
    return os.getenv("RAG_BASE_URL", "http://127.0.0.1:8010").rstrip("/")


def rag_timeout() -> float:
    raw = os.getenv("RAG_TIMEOUT_SECONDS", "30")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 30.0


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def compact_rag_record(record: dict[str, Any]) -> dict[str, Any]:
    compact = dict(record)
    compact.pop("embedding_vector", None)
    compact.pop("embedding_text", None)
    compact.pop("storage_key", None)
    compact["metadata"] = _json_object(compact.get("metadata") or compact.get("metadata_json"))
    compact.pop("metadata_json", None)
    return compact


def build_rag_summary(reference: dict[str, Any]) -> str:
    metadata = _json_object(reference.get("metadata") or reference.get("metadata_json"))
    scene = metadata.get("scene_description") or reference.get("scene") or ""
    style = metadata.get("visual_style") or ""
    tone = metadata.get("color_tone") or ""
    composition = metadata.get("composition") or reference.get("image_type") or ""
    lighting = metadata.get("lighting") or ""
    season = metadata.get("season") or ""
    caption = reference.get("caption") or ""
    parts = [part for part in [scene, style, tone, composition, lighting, season, caption] if str(part).strip()]
    return "，".join(dict.fromkeys(str(part).strip() for part in parts))


def predicted_steps_for_usage_tags(usage_tags: list[str], asset_type: str = "", rag_role: str = "") -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    role = rag_role or asset_type
    if role and role in RAG_ROLE_TO_STAGES:
        role_label = RAG_ROLE_LABELS.get(role, role)
        for stage_id in RAG_ROLE_TO_STAGES.get(role, []):
            if stage_id not in seen:
                label = STAGE_LABELS.get(stage_id, {})
                seen[stage_id] = {
                    "stage_id": stage_id,
                    "image_no": label.get("image_no", 0),
                    "title": label.get("title", stage_id),
                    "reason": role_label,
                }
    return sorted(seen.values(), key=lambda item: item["image_no"])


def build_default_model_description(reference: dict[str, Any]) -> str:
    existing = str(reference.get("model_description") or "").strip()
    if existing:
        return existing
    metadata = _json_object(reference.get("metadata") or reference.get("metadata_json"))
    parts: list[str] = []
    scene = metadata.get("scene_description") or reference.get("scene") or ""
    if scene:
        parts.append(f"这是一张{scene}场景参考图")
    image_type = reference.get("image_type") or ""
    if image_type:
        parts.append(f"画面为{image_type}构图")
    style = metadata.get("visual_style") or ""
    if style:
        parts.append(f"整体是{style}")
    tone = metadata.get("color_tone") or ""
    if tone:
        parts.append(f"{tone}色系")
    lighting = metadata.get("lighting") or ""
    if lighting:
        parts.append(lighting)
    if parts:
        return "，".join(parts) + "。"
    caption = reference.get("caption") or ""
    if caption:
        return caption
    filename = reference.get("filename") or ""
    if filename:
        return f"这是一张知识库参考图（{filename}），请只参考其已标注用途相关的视觉特征。"
    return "这是一张知识库参考图，请只参考其已标注用途相关的视觉特征。"


def allowed_aspects_for_usage_tags(usage_tags: list[str], asset_type: str = "", rag_role: str = "") -> list[str]:
    seen: list[str] = []
    role = rag_role or asset_type
    if role and role in RAG_ROLE_ALLOWED_ASPECTS:
        for aspect in RAG_ROLE_ALLOWED_ASPECTS.get(role, []):
            if aspect not in seen:
                seen.append(aspect)
    return seen


def reference_ids_by_type(refs: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "reference_refs": refs,
        "reference_asset_ids": [ref["id"] for ref in refs if ref.get("type") == "asset"],
        "reference_stage_ids": [ref["id"] for ref in refs if ref.get("type") == "step"],
        "reference_rag_ids": [ref["id"] for ref in refs if ref.get("type") == "rag"],
    }


def rag_request(method: str, path: str, **kwargs: Any) -> requests.Response:
    url = f"{rag_base_url()}{path}"
    try:
        response = requests.request(method, url, timeout=rag_timeout(), **kwargs)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"RAG 服务不可用: {exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text[:1000])
    return response


def rag_health() -> dict[str, Any]:
    return rag_request("GET", "/health").json()


def rag_search(payload: dict[str, Any], offset: int = 0, limit: int | None = None) -> dict[str, Any]:
    response = rag_request("POST", "/search", json=payload)
    data = response.json()
    results = [compact_rag_record(item) for item in data.get("results") or []]
    if limit is not None:
        safe_offset = max(0, int(offset))
        safe_limit = max(0, int(limit))
        data["results"] = results[safe_offset:safe_offset + safe_limit]
        data["offset"] = safe_offset
        data["limit"] = safe_limit
        data["has_more"] = len(results) > safe_offset + safe_limit
    else:
        data["results"] = results
    return data


def rag_image_response(image_id: str) -> tuple[bytes, str]:
    response = rag_request("GET", f"/images/{image_id}")
    content_type = response.headers.get("content-type") or "image/jpeg"
    return response.content, content_type


def download_rag_reference_to_cache(project_id: str, reference: dict[str, Any], upload_root: Path) -> Path:
    rag_image_id = str(reference.get("rag_image_id") or "").strip()
    if not rag_image_id:
        raise HTTPException(status_code=400, detail="RAG 参考图缺少 rag_image_id")
    cache_dir = upload_root / project_id / "rag_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(str(reference.get("filename") or "")).suffix
    if not suffix:
        suffix = mimetypes.guess_extension(str(reference.get("content_type") or "image/jpeg")) or ".jpg"
    target = cache_dir / f"{rag_image_id}{suffix}"
    if target.is_file():
        return target
    content, _content_type = rag_image_response(rag_image_id)
    target.write_bytes(content)
    return target
