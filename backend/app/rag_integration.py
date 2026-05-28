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

STAGE_USAGE_TAGS: dict[str, set[str]] = {
    "model_on_body": {"competitor_fit_reference"},
    "scene_model": {"scene_reference", "color_reference"},
    "outfit": {"pose_reference", "color_reference"},
    "white_main": {"white_main_reference", "composition_reference"},
    "white_back": {"white_main_reference", "composition_reference"},
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

USAGE_TAG_STAGE_MAP: dict[str, list[str]] = {
    "competitor_fit_reference": ["model_on_body"],
    "scene_reference": ["scene_model"],
    "color_reference": ["scene_model", "outfit"],
    "pose_reference": ["angle_3", "angle_4", "angle_5", "angle_6", "outfit"],
    "composition_reference": ["white_main", "white_back"],
    "white_main_reference": ["white_main", "white_back"],
}

USAGE_TAG_ALLOWED_ASPECTS: dict[str, list[str]] = {
    "scene_reference": ["背景环境", "场景氛围", "空间关系"],
    "pose_reference": ["人物姿势", "身体朝向", "动作节奏"],
    "composition_reference": ["构图方式", "画面裁切", "主体位置"],
    "color_reference": ["色调", "光影", "整体氛围"],
    "white_main_reference": ["白底构图", "商品占比", "商业主图呈现方式"],
    "competitor_fit_reference": ["上身松紧度", "穿着方式", "衣长和版型参考"],
}

RAG_FORBIDDEN_ASPECTS: list[str] = [
    "人物身份", "人物长相", "服装款式", "品牌", "文字", "水印", "无关道具", "无关背景元素",
]

RAG_CONTEXT_BLOCK_START = "【知识库参考图说明】"
RAG_CONTEXT_BLOCK_LEGACY = "【知识库参考摘要】"


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


def predicted_steps_for_usage_tags(usage_tags: list[str]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for tag in usage_tags:
        for stage_id in USAGE_TAG_STAGE_MAP.get(tag, []):
            if stage_id not in seen:
                label = STAGE_LABELS.get(stage_id, {})
                seen[stage_id] = {
                    "stage_id": stage_id,
                    "image_no": label.get("image_no", 0),
                    "title": label.get("title", stage_id),
                    "reason": RAG_USAGE_TAGS.get(tag, tag),
                }
            else:
                reason = RAG_USAGE_TAGS.get(tag, tag)
                if reason and reason not in seen[stage_id]["reason"]:
                    seen[stage_id]["reason"] += f" / {reason}"
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


def allowed_aspects_for_usage_tags(usage_tags: list[str]) -> list[str]:
    seen: list[str] = []
    for tag in usage_tags:
        for aspect in USAGE_TAG_ALLOWED_ASPECTS.get(tag, []):
            if aspect not in seen:
                seen.append(aspect)
    return seen


def compose_rag_context_block(input_refs: list[dict[str, str]], rag_refs_by_id: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, ref in enumerate(input_refs):
        if ref.get("type") != "rag":
            continue
        rag_ref = rag_refs_by_id.get(ref["id"])
        if not rag_ref:
            continue
        image_no = index + 1
        filename = rag_ref.get("filename") or rag_ref.get("rag_image_id") or "未知"
        usage_labels = rag_ref.get("usage_labels") or []
        usage_tags = rag_ref.get("usage_tags") or []
        model_desc = build_default_model_description(rag_ref)
        allowed = allowed_aspects_for_usage_tags(usage_tags)
        lines.append(f"图{image_no}：知识库参考图，文件名 {filename}")
        if usage_labels:
            lines.append(f"用途：{'、'.join(usage_labels)}")
        lines.append(f"这张图是什么：{model_desc}")
        if allowed:
            lines.append(f"本图只参考：{'、'.join(allowed)}。")
        lines.append(f"不要参考：{'、'.join(RAG_FORBIDDEN_ASPECTS)}。")
        lines.append("")
    if not lines:
        return ""
    header = f"{RAG_CONTEXT_BLOCK_START}\n除基础参考图外，本次额外提供以下知识库参考图：\n"
    return header + "\n".join(lines)


def strip_rag_context_block(prompt: str) -> str:
    for marker in [RAG_CONTEXT_BLOCK_START, RAG_CONTEXT_BLOCK_LEGACY]:
        idx = prompt.find(marker)
        if idx >= 0:
            return prompt[:idx].rstrip()
    return prompt


def apply_rag_context_to_prompt(prompt: str, input_refs: list[dict[str, str]], rag_refs_by_id: dict[str, dict[str, Any]]) -> str:
    clean_prompt = strip_rag_context_block(prompt)
    context_block = compose_rag_context_block(input_refs, rag_refs_by_id)
    if not context_block:
        return clean_prompt
    return f"{clean_prompt.rstrip()}\n\n{context_block}"


def stage_usage_tags(stage_id: str) -> set[str]:
    if stage_id.startswith("angle_"):
        return {"pose_reference"}
    return STAGE_USAGE_TAGS.get(stage_id, set())


def select_stage_references(stage_id: str, references: list[dict[str, Any]], max_items: int = 3) -> list[dict[str, Any]]:
    desired_tags = stage_usage_tags(stage_id)
    if not desired_tags:
        return []
    if stage_id.startswith("angle_"):
        max_items = 1

    def has_desired_tag(item: dict[str, Any]) -> bool:
        tags = item.get("usage_tags") or item.get("usage_tags_json") or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = []
        return bool(desired_tags.intersection(set(str(tag) for tag in tags)))

    matched = [item for item in references if has_desired_tag(item)]
    return sorted(
        matched,
        key=lambda item: (int(item.get("sort_order") or 0), -float(item.get("score") or 0.0), str(item.get("selected_at") or "")),
    )[:max_items]


def enrich_docx_steps_with_rag(steps: list[dict[str, Any]], references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for step in steps:
        updated = dict(step)
        stage_id = str(updated.get("stage_id") or "")
        refs = [dict(item) for item in (updated.get("input_refs") or [])]
        has_uploaded_angle_pose = stage_id.startswith("angle_") and any(ref.get("type") == "asset" for ref in refs)
        selected = [] if has_uploaded_angle_pose else select_stage_references(stage_id, references)
        if selected:
            existing = {(item.get("type"), item.get("id")) for item in refs}
            for item in selected:
                ref = {"type": "rag", "id": str(item["id"])}
                if (ref["type"], ref["id"]) not in existing:
                    refs.append(ref)
            updated["input_refs"] = refs
        rag_refs_by_id = {str(item["id"]): item for item in references}
        updated["prompt"] = apply_rag_context_to_prompt(updated.get("prompt") or "", refs, rag_refs_by_id)
        enriched.append(updated)
    return enriched


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


def rag_search(payload: dict[str, Any]) -> dict[str, Any]:
    response = rag_request("POST", "/search", json=payload)
    data = response.json()
    data["results"] = [compact_rag_record(item) for item in data.get("results") or []]
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
