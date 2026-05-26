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


def stage_usage_tags(stage_id: str) -> set[str]:
    if stage_id.startswith("angle_"):
        return {"pose_reference", "composition_reference"}
    return STAGE_USAGE_TAGS.get(stage_id, set())


def select_stage_references(stage_id: str, references: list[dict[str, Any]], max_items: int = 3) -> list[dict[str, Any]]:
    desired_tags = stage_usage_tags(stage_id)
    if not desired_tags:
        return []

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
        refs = [dict(item) for item in (updated.get("input_refs") or [])]
        selected = select_stage_references(str(updated.get("stage_id") or ""), references)
        summaries = [build_rag_summary(item) for item in selected]
        summaries = [summary for summary in summaries if summary]
        if summaries:
            summary_lines = "\n".join(f"{index}. {summary}" for index, summary in enumerate(summaries, start=1))
            updated["prompt"] = (
                f"{updated.get('prompt') or ''}\n\n"
                "【知识库参考摘要】\n"
                f"{summary_lines}\n"
                "请吸收上述参考中的场景、构图、色调、光影、产品展示方式；不得复制品牌、水印、文字或无关人物。"
            )
            existing = {(item.get("type"), item.get("id")) for item in refs}
            for item in selected:
                ref = {"type": "rag", "id": str(item["id"])}
                if (ref["type"], ref["id"]) not in existing:
                    refs.append(ref)
            updated["input_refs"] = refs
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
