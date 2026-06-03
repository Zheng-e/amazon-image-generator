from __future__ import annotations

import base64
import io
import json
import mimetypes
import re
import shutil
import sqlite3
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for deps_dir in (ROOT / ".webdeps", ROOT / ".deps"):
    if deps_dir.exists():
        sys.path.insert(0, str(deps_dir))

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai_clients import available_analysis_models, available_image_models, call_image_model
from .db import (
    DATA_DIR,
    UPLOAD_DIR,
    from_json,
    get_db,
    init_db,
    new_id,
    now_iso,
    row_to_dict,
    to_json,
)
from .docx_workflow import STYLE_OPTIONS, build_workflow_steps, style_options_payload
from .rag_integration import (
    RAG_FORBIDDEN_ASPECTS,
    RAG_USAGE_TAGS,
    allowed_aspects_for_usage_tags,
    build_default_model_description,
    build_rag_summary,
    compact_rag_record,
    download_rag_reference_to_cache,
    predicted_steps_for_usage_tags,
    rag_health,
    rag_image_response,
    rag_search,
    reference_ids_by_type,
)


app = FastAPI(title="设计部主图生成字段实验台", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_active_tasks: dict[str, threading.Thread] = {}
_active_tasks_lock = threading.Lock()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)


app.mount("/files", StaticFiles(directory=str(DATA_DIR)), name="files")
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/workbench", StaticFiles(directory=str(STATIC_DIR), html=True), name="workbench")


class UserIn(BaseModel):
    name: str


class ProjectIn(BaseModel):
    user_id: str = "default"
    sku: str
    category: str = ""
    name: str = ""
    notes: str = ""


class DocxWorkflowRunIn(BaseModel):
    project_id: str = ""
    product_name: str
    material: str
    style_key: str = "natural_fashion"
    product_asset_id: str
    model_asset_id: str = ""
    fit_front_asset_id: str = ""
    fit_side_asset_id: str = ""
    fit_back_asset_id: str = ""
    fit_asset_id: str = ""  # deprecated, kept for backward compat
    scene_asset_id: str = ""
    accessory_asset_id: str
    image_model: str | None = None
    size: str = "1024x1024"
    quality: str = "high"


class DocxWorkflowGenerateIn(BaseModel):
    image_model: str | None = None
    size: str | None = None
    quality: str | None = None


class DocxWorkflowStepUpdateIn(BaseModel):
    prompt: str | None = None
    input_refs: list[dict[str, str]] | None = None


class RagSearchIn(BaseModel):
    query: str
    top_k: int = 8
    offset: int = 0
    filters: dict[str, Any] = Field(default_factory=dict)


class RagReferenceIn(BaseModel):
    rag_image_id: str
    filename: str = ""
    category: str = ""
    scene: str = ""
    image_type: str = ""
    caption: str = ""
    score: float | None = None
    usage_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_description: str = ""
    asset_type: str = ""
    rag_role: str = ""
    notes: str = ""


class RagReferenceUpdateIn(BaseModel):
    usage_tags: list[str] | None = None
    notes: str | None = None
    sort_order: int | None = None
    model_description: str | None = None
    rag_role: str | None = None


class KnowledgeCandidateIn(BaseModel):
    rating: int | None = None
    review_notes: str = ""
    suggested_category: str = ""
    suggested_scene: str = ""
    suggested_image_type: str = ""
    suggested_metadata: dict[str, Any] = Field(default_factory=dict)


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def file_url(file_path: str) -> str:
    if not file_path:
        return ""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return ""
    try:
        rel = path.relative_to(DATA_DIR).as_posix()
    except ValueError:
        rel = path.as_posix()
    return f"/files/{rel}"


def hydrate_asset(asset: dict | None) -> dict | None:
    if not asset:
        return None
    asset["url"] = file_url(asset["file_path"])
    return asset


def hydrate_result(result: dict | None) -> dict | None:
    if not result:
        return None
    result["url"] = file_url(result.get("image_path", ""))
    return result


_POSE_SLOT_STAGES = {"angle_3", "angle_4", "angle_5", "angle_6", "white_main", "white_back"}


def hydrate_docx_step(step: dict | None) -> dict | None:
    if not step:
        return None
    step["url"] = file_url(step.get("image_path", ""))
    step["input_refs"] = normalized_docx_refs(step)
    params = step.get("params") or {}
    if isinstance(params, dict) and params.get("pose_slot"):
        step["pose_slot"] = True
    elif step.get("stage_id") in _POSE_SLOT_STAGES:
        step["pose_slot"] = True
    return step


def normalized_docx_refs(step: dict) -> list[dict[str, str]]:
    raw_refs = step.get("input_refs")
    refs: list[dict[str, str]] = []
    if isinstance(raw_refs, list) and raw_refs:
        for item in raw_refs:
            if not isinstance(item, dict):
                continue
            ref_type = str(item.get("type") or "").strip()
            ref_id = str(item.get("id") or "").strip()
            if ref_type in {"asset", "step"} and ref_id:
                refs.append({"type": ref_type, "id": ref_id})
        if refs:
            return refs
    for asset_id in step.get("input_asset_ids") or []:
        refs.append({"type": "asset", "id": str(asset_id)})
    for stage_id in step.get("input_step_ids") or []:
        refs.append({"type": "step", "id": str(stage_id)})
    return refs


def split_docx_refs(refs: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    asset_ids: list[str] = []
    step_ids: list[str] = []
    for ref in refs:
        if ref.get("type") == "asset":
            asset_ids.append(ref["id"])
        elif ref.get("type") == "step":
            step_ids.append(ref["id"])
    return asset_ids, step_ids


def project_image_response_to_bytes(result: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    b64_json = result.get("b64_json")
    if not b64_json:
        raise RuntimeError(f"Image model returned no b64_json: {str(result)[:500]}")
    params = {key: value for key, value in result.items() if key != "b64_json"}
    return base64.b64decode(str(b64_json)), params


def fetch_one(conn, query: str, params: tuple = ()) -> dict:
    row = conn.execute(query, params).fetchone()
    data = row_to_dict(row)
    if not data:
        raise HTTPException(404, "记录不存在")
    return data


def get_assets_by_ids(conn, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(f"SELECT * FROM assets WHERE id IN ({placeholders}) AND deleted_at IS NULL", tuple(ids)).fetchall()
    assets = [hydrate_asset(row_to_dict(row)) for row in rows]
    order = {asset_id: i for i, asset_id in enumerate(ids)}
    return sorted([a for a in assets if a], key=lambda item: order.get(item["id"], 9999))


def missing_asset_file_names(assets: list[dict]) -> list[str]:
    return [
        f"{asset.get('original_name') or asset.get('id')} ({asset.get('slot') or asset.get('asset_type')})"
        for asset in assets
        if not Path(asset.get("file_path") or "").is_file()
    ]


def fetch_project_workflow_steps(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM project_workflow_steps WHERE project_id = ? ORDER BY generation_order ASC",
        (project_id,),
    ).fetchall()
    return [hydrate_docx_step(row_to_dict(row)) for row in rows]


def fetch_project_workflow_package(conn: sqlite3.Connection, project_id: str) -> dict:
    project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
    steps = fetch_project_workflow_steps(conn, project_id)
    pseudo_run = {
        "id": project_id,
        "project_id": project_id,
        "product_name": project.get("product_name", ""),
        "material": project.get("material", ""),
        "style_key": project.get("style_key", ""),
        "product_asset_id": project.get("product_asset_id", ""),
        "model_asset_id": project.get("model_asset_id", ""),
        "fit_front_asset_id": project.get("fit_front_asset_id", ""),
        "fit_side_asset_id": project.get("fit_side_asset_id", ""),
        "fit_back_asset_id": project.get("fit_back_asset_id", ""),
        "scene_asset_id": project.get("scene_asset_id", ""),
        "accessory_asset_id": project.get("accessory_asset_id", ""),
    }
    steps = attach_docx_reference_items(conn, pseudo_run, steps)
    return {
        "project_id": project_id,
        "product_name": project.get("product_name", ""),
        "material": project.get("material", ""),
        "style_key": project.get("style_key", ""),
        "product_asset_id": project.get("product_asset_id", ""),
        "fit_front_asset_id": project.get("fit_front_asset_id", ""),
        "fit_side_asset_id": project.get("fit_side_asset_id", ""),
        "fit_back_asset_id": project.get("fit_back_asset_id", ""),
        "accessory_asset_id": project.get("accessory_asset_id", ""),
        "image_model": project.get("image_model", ""),
        "size": project.get("size", "1024x1024"),
        "quality": project.get("quality", "high"),
        "workflow_status": project.get("workflow_status", "idle"),
        "workflow_error": project.get("workflow_error", ""),
        "downloaded_at": project.get("downloaded_at", ""),
        "steps": steps,
    }


def attach_docx_reference_items(conn, run: dict, steps: list[dict]) -> list[dict]:
    asset_ids: list[str] = []
    for step in steps:
        for ref in normalized_docx_refs(step):
            if ref["type"] == "asset":
                asset_ids.append(ref["id"])
    assets = get_assets_by_ids(conn, list(dict.fromkeys(asset_ids)))
    asset_by_id = {asset["id"]: asset for asset in assets}
    step_by_stage = {step["stage_id"]: step for step in steps}
    for step in steps:
        items: list[dict[str, Any]] = []
        refs = normalized_docx_refs(step)
        for index, ref in enumerate(refs, start=1):
            if ref["type"] == "asset":
                asset = asset_by_id.get(ref["id"])
                items.append(
                    {
                        "type": "asset",
                        "id": ref["id"],
                        "order": index,
                        "label": asset.get("original_name") if asset else "参考图已删除",
                        "asset_type": asset.get("asset_type") if asset else "",
                        "slot": asset.get("slot") if asset else "",
                        "url": asset.get("url") if asset else "",
                        "missing": not asset or not Path(asset.get("file_path") or "").is_file(),
                    }
                )
            else:
                source_step = step_by_stage.get(ref["id"])
                items.append(
                    {
                        "type": "step",
                        "id": ref["id"],
                        "order": index,
                        "label": source_step.get("title") if source_step else ref["id"],
                        "image_no": source_step.get("image_no") if source_step else None,
                        "status": source_step.get("status") if source_step else "",
                        "url": source_step.get("url") if source_step else "",
                        "missing": not source_step,
                    }
                )
        step["input_refs"] = refs
        step["reference_items"] = items
    return steps


def validate_docx_workflow_input(conn, payload: DocxWorkflowRunIn) -> list[dict]:
    if not payload.product_name.strip():
        raise HTTPException(400, "产品名称为必填项")
    if not payload.material.strip():
        raise HTTPException(400, "材质为必填项")
    if payload.style_key not in STYLE_OPTIONS:
        raise HTTPException(400, "请选择有效的输出规格风格")
    fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (payload.project_id,))
    fit_front = payload.fit_front_asset_id or payload.fit_asset_id
    fit_side = payload.fit_side_asset_id or payload.fit_asset_id
    fit_back = payload.fit_back_asset_id or payload.fit_asset_id
    asset_ids = [
        payload.product_asset_id,
    ]
    if payload.model_asset_id:
        asset_ids.append(payload.model_asset_id)
    asset_ids.extend([fit_front, fit_side, fit_back])
    if payload.scene_asset_id:
        asset_ids.append(payload.scene_asset_id)
    asset_ids.append(payload.accessory_asset_id)
    asset_ids = list(dict.fromkeys(asset_ids))
    assets = get_assets_by_ids(conn, asset_ids)
    found = {asset["id"]: asset for asset in assets}
    missing = [asset_id for asset_id in asset_ids if asset_id not in found]
    if missing:
        raise HTTPException(400, "缺少必填参考图")
    wrong_project = [asset["original_name"] for asset in assets if asset["project_id"] != payload.project_id]
    if wrong_project:
        raise HTTPException(400, "只能选择当前项目下的参考图")
    missing_files = missing_asset_file_names(assets)
    if missing_files:
        raise HTTPException(400, "参考图文件不存在，请重新上传：" + "、".join(missing_files))
    return assets


def insert_docx_workflow_steps(conn, run_id: str, payload: DocxWorkflowRunIn) -> None:
    fit_front = payload.fit_front_asset_id or payload.fit_asset_id
    fit_side = payload.fit_side_asset_id or payload.fit_asset_id
    fit_back = payload.fit_back_asset_id or payload.fit_asset_id
    steps = build_workflow_steps(
        product_name=payload.product_name.strip(),
        material=payload.material.strip(),
        style_key=payload.style_key,
        product_asset_id=payload.product_asset_id,
        model_asset_id=payload.model_asset_id,
        fit_front_asset_id=fit_front,
        fit_side_asset_id=fit_side,
        fit_back_asset_id=fit_back,
        scene_asset_id=payload.scene_asset_id,
        accessory_asset_id=payload.accessory_asset_id,
    )
    ts = now_iso()
    for step in steps:
        conn.execute(
            """
            INSERT INTO docx_workflow_steps
            (id, run_id, stage_id, image_no, generation_order, title, prompt,
             input_asset_ids_json, input_step_ids_json, input_refs_json, params_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                run_id,
                step["stage_id"],
                step["image_no"],
                step["generation_order"],
                step["title"],
                step["prompt"],
                to_json(step["input_asset_ids"]),
                to_json(step["input_step_ids"]),
                to_json(step.get("input_refs") or []),
                to_json({"pose_slot": bool(step.get("pose_slot"))}),
                "pending",
                ts,
                ts,
            ),
        )


def insert_project_workflow_steps(conn: sqlite3.Connection, project_id: str, payload) -> None:
    from backend.app.docx_workflow import build_workflow_steps

    ts = now_iso()
    fit_front = payload.fit_front_asset_id or payload.fit_asset_id
    fit_side = payload.fit_side_asset_id or payload.fit_asset_id
    fit_back = payload.fit_back_asset_id or payload.fit_asset_id
    steps = build_workflow_steps(
        product_name=payload.product_name.strip(),
        material=payload.material.strip(),
        style_key=payload.style_key,
        product_asset_id=payload.product_asset_id,
        model_asset_id=payload.model_asset_id,
        fit_front_asset_id=fit_front,
        fit_side_asset_id=fit_side,
        fit_back_asset_id=fit_back,
        scene_asset_id=payload.scene_asset_id,
        accessory_asset_id=payload.accessory_asset_id,
    )
    for step_def in steps:
        step_id = new_id()
        refs = step_def.get("input_refs") or []
        conn.execute(
            """INSERT INTO project_workflow_steps
               (id, project_id, stage_id, image_no, generation_order, title, prompt,
                input_asset_ids_json, input_step_ids_json, input_refs_json,
                image_path, params_json, status, error, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, 'pending', '', ?, ?)""",
            (
                step_id, project_id, step_def["stage_id"], step_def["image_no"],
                step_def["generation_order"], step_def["title"], step_def["prompt"],
                to_json(step_def.get("input_asset_ids") or []),
                to_json(step_def.get("input_step_ids") or []),
                to_json(refs),
                to_json({"pose_slot": bool(step_def.get("pose_slot"))}),
                ts, ts,
            ),
        )


def normalize_usage_tags(tags: list[str]) -> list[str]:
    clean: list[str] = []
    for tag in tags:
        value = str(tag or "").strip()
        if value in RAG_USAGE_TAGS and value not in clean:
            clean.append(value)
    return clean


def hydrate_rag_reference(row: dict | None) -> dict | None:
    if not row:
        return None
    row["usage_tags"] = row.pop("usage_tags", row.get("usage_tags_json", []))
    row["metadata"] = row.pop("metadata", row.get("metadata_json", {}))
    row["image_url"] = f"/api/rag/images/{row['rag_image_id']}"
    usage_tags = row.get("usage_tags") or []
    asset_type = row.get("asset_type") or ""
    row["usage_labels"] = [RAG_USAGE_TAGS.get(tag, tag) for tag in usage_tags]
    row["model_description"] = build_default_model_description(row)
    row["rag_summary"] = build_rag_summary(row)
    rag_role = row.get("rag_role") or ""
    row["applied_steps"] = predicted_steps_for_usage_tags(usage_tags, asset_type, rag_role)
    return row


def get_rag_references_for_project(conn, project_id: str) -> list[dict]:
    fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
    rows = conn.execute(
        """
        SELECT * FROM rag_reference_selections
        WHERE project_id = ?
        ORDER BY sort_order ASC, selected_at DESC
        """,
        (project_id,),
    ).fetchall()
    return [hydrate_rag_reference(row_to_dict(row)) for row in rows]


def get_rag_references_by_ids(conn, project_id: str, reference_ids: list[str]) -> list[dict]:
    if not reference_ids:
        return []
    placeholders = ",".join("?" for _ in reference_ids)
    rows = conn.execute(
        f"""
        SELECT * FROM rag_reference_selections
        WHERE project_id = ? AND id IN ({placeholders})
        """,
        (project_id, *reference_ids),
    ).fetchall()
    references = [hydrate_rag_reference(row_to_dict(row)) for row in rows]
    order = {reference_id: index for index, reference_id in enumerate(reference_ids)}
    return sorted([item for item in references if item], key=lambda item: order.get(item["id"], 9999))


def fetch_rag_reference(conn, project_id: str, reference_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM rag_reference_selections WHERE id = ? AND project_id = ?",
        (reference_id, project_id),
    ).fetchone()
    data = hydrate_rag_reference(row_to_dict(row))
    if not data:
        raise HTTPException(404, "知识库参考图不存在")
    return data


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "time": now_iso()}


@app.get("/api/rag/health")
def api_rag_health() -> dict[str, Any]:
    return rag_health()


@app.post("/api/rag/search")
def api_rag_search(payload: RagSearchIn) -> dict[str, Any]:
    query = payload.query.strip()
    if not query:
        raise HTTPException(400, "检索词不能为空")
    limit = max(1, min(int(payload.top_k), 200))
    offset = max(0, int(payload.offset))
    return rag_search(
        {
            "query": query,
            "top_k": offset + limit + 1,
            "filters": payload.filters if isinstance(payload.filters, dict) else {},
        },
        offset=offset,
        limit=limit,
    )


@app.api_route("/api/rag/images/{image_id}", methods=["GET", "HEAD"])
def api_rag_image(image_id: str) -> Response:
    content, content_type = rag_image_response(image_id)
    return Response(content=content, media_type=content_type)


class RagToAssetIn(BaseModel):
    rag_image_id: str
    filename: str = ""
    slot: str = ""
    rag_role: str = ""
    model_description: str = ""


RAG_ROLE_TO_SLOT: dict[str, str] = {
    "model": "model_reference",
    "scene_style": "scene_reference",
    "pose": "pose_reference",
    "accessory": "accessory_reference",
}


@app.post("/api/projects/{project_id}/rag-to-asset")
def rag_to_asset(project_id: str, payload: RagToAssetIn) -> dict:
    with get_db() as conn:
        fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))

    rag_image_id = payload.rag_image_id.strip()
    if not rag_image_id:
        raise HTTPException(400, "rag_image_id 不能为空")

    slot = payload.slot or RAG_ROLE_TO_SLOT.get(payload.rag_role, "pose_reference")
    filename = payload.filename or f"{rag_image_id}.jpg"

    cache_dir = UPLOAD_DIR / project_id / "rag_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / filename

    if not cache_path.is_file():
        content, _content_type = rag_image_response(rag_image_id)
        cache_path.write_bytes(content)

    asset_type = "model" if slot == "model_reference" else "other"
    asset_id = new_id()
    ts = now_iso()
    file_path = str(cache_path)
    mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"

    with get_db() as conn:
        conn.execute(
            """INSERT INTO assets
               (id, project_id, original_name, file_path, asset_type, mime_type, slot, deleted_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)""",
            (asset_id, project_id, filename, file_path, asset_type, mime_type, slot, ts),
        )
        asset = fetch_one(conn, "SELECT * FROM assets WHERE id = ?", (asset_id,))

    return hydrate_asset(asset)


@app.get("/api/models/analysis")
def list_analysis_models() -> list[dict[str, Any]]:
    return available_analysis_models()


@app.get("/api/models/image")
def list_image_models() -> list[dict[str, Any]]:
    return available_image_models()


@app.get("/api/docx-workflow/styles")
def list_docx_workflow_styles() -> list[dict[str, str]]:
    return style_options_payload()


# DEPRECATED — use POST /api/projects/{project_id}/workflow instead
@app.post("/api/docx-workflow/runs")
def create_docx_workflow_run(payload: DocxWorkflowRunIn) -> dict:
    with get_db() as conn:
        validate_docx_workflow_input(conn, payload)
        run_id = new_id()
        ts = now_iso()
        fit_front = payload.fit_front_asset_id or payload.fit_asset_id
        fit_side = payload.fit_side_asset_id or payload.fit_asset_id
        fit_back = payload.fit_back_asset_id or payload.fit_asset_id
        conn.execute(
            """
            INSERT INTO docx_workflow_runs
            (id, project_id, product_name, material, style_key, product_asset_id, model_asset_id,
             fit_asset_id, fit_front_asset_id, fit_side_asset_id, fit_back_asset_id,
             accessory_asset_id, scene_asset_id, pose_asset_id, image_model, size, quality, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                payload.project_id,
                payload.product_name.strip(),
                payload.material.strip(),
                payload.style_key,
                payload.product_asset_id,
                payload.model_asset_id,
                payload.fit_asset_id,
                fit_front,
                fit_side,
                fit_back,
                payload.accessory_asset_id,
                payload.scene_asset_id,
                "",  # pose_asset_id
                payload.image_model or "",
                payload.size,
                payload.quality,
                "draft",
                ts,
                ts,
            ),
        )
        insert_docx_workflow_steps(conn, run_id, payload)
        return fetch_docx_run_package(conn, run_id)


# DEPRECATED — use POST /api/projects/{project_id}/workflow/preview instead
@app.post("/api/docx-workflow/runs/{run_id}/preview")
def preview_docx_workflow_run(run_id: str) -> dict:
    with get_db() as conn:
        return fetch_docx_run_package(conn, run_id)


# DEPRECATED — use GET /api/projects/{project_id}/workflow instead
@app.get("/api/docx-workflow/runs/{run_id}")
def get_docx_workflow_run(run_id: str) -> dict:
    with get_db() as conn:
        return fetch_docx_run_package(conn, run_id)


# DEPRECATED — use GET /api/projects/{project_id}/workflow/download instead
@app.get("/api/docx-workflow/runs/{run_id}/download")
def download_docx_workflow_run(run_id: str) -> Response:
    with get_db() as conn:
        package = fetch_docx_run_package(conn, run_id)
    steps = sorted(package.get("steps") or [], key=lambda item: item.get("generation_order") or item.get("image_no") or 0)
    ready_steps = [step for step in steps if step.get("image_path") and Path(step["image_path"]).is_file()]
    if len(ready_steps) < 9:
        raise HTTPException(400, "还没有生成完整 9 张图，无法下载")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for step in ready_steps:
            src = Path(step["image_path"])
            stage_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(step.get("stage_id") or "image")).strip("_")
            filename = f"{int(step.get('image_no') or 0):02d}_{stage_id}{src.suffix or '.png'}"
            zf.write(src, filename)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(package.get("product_name") or "docx_workflow")).strip("_") or "docx_workflow"
    with get_db() as conn:
        conn.execute("UPDATE docx_workflow_runs SET downloaded_at = ? WHERE id = ?", (now_iso(), run_id))
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_{run_id[:8]}_images.zip"'},
    )


# DEPRECATED — use PATCH /api/projects/workflow/steps/{step_id} instead
@app.patch("/api/docx-workflow/steps/{step_id}")
def update_docx_workflow_step(step_id: str, payload: DocxWorkflowStepUpdateIn) -> dict:
    with get_db() as conn:
        step = fetch_one(conn, "SELECT * FROM docx_workflow_steps WHERE id = ?", (step_id,))
        assignments = ["status = ?", "error = ?", "updated_at = ?"]
        values: list[Any] = ["pending", "", now_iso()]
        if payload.prompt is not None:
            prompt = payload.prompt.strip()
            if not prompt:
                raise HTTPException(400, "提示词不能为空")
            assignments.insert(0, "prompt = ?")
            values.insert(0, prompt)
        if payload.input_refs is not None:
            refs: list[dict[str, str]] = []
            for item in payload.input_refs:
                ref_type = str(item.get("type") or "").strip()
                ref_id = str(item.get("id") or "").strip()
                if ref_type not in {"asset", "step"} or not ref_id:
                    raise HTTPException(400, "参考图格式不正确")
                refs.append({"type": ref_type, "id": ref_id})
            asset_ids, step_ids = split_docx_refs(refs)
            if asset_ids:
                assets = get_assets_by_ids(conn, list(dict.fromkeys(asset_ids)))
                found_assets = {asset["id"]: asset for asset in assets}
                missing_assets = [asset_id for asset_id in asset_ids if asset_id not in found_assets]
                if missing_assets:
                    raise HTTPException(400, "参考图素材不存在或已删除")
                run = fetch_one(conn, "SELECT * FROM docx_workflow_runs WHERE id = ?", (step["run_id"],))
                wrong_project = [asset["original_name"] for asset in assets if asset["project_id"] != run["project_id"]]
                if wrong_project:
                    raise HTTPException(400, "只能选择当前项目下的参考图")
                missing_files = missing_asset_file_names(assets)
                if missing_files:
                    raise HTTPException(400, "参考图文件不存在，请重新上传：" + "、".join(missing_files))
            if step_ids:
                stage_rows = conn.execute(
                    "SELECT stage_id FROM docx_workflow_steps WHERE run_id = ?",
                    (step["run_id"],),
                ).fetchall()
                valid_stage_ids = {row["stage_id"] for row in stage_rows}
                missing_steps = [stage_id for stage_id in step_ids if stage_id not in valid_stage_ids]
                if missing_steps:
                    raise HTTPException(400, "前置步骤不存在：" + "、".join(missing_steps))
            assignments.extend(["input_refs_json = ?", "input_asset_ids_json = ?", "input_step_ids_json = ?"])
            values.extend([to_json(refs), to_json(asset_ids), to_json(step_ids)])
        if payload.prompt is None and payload.input_refs is None:
            raise HTTPException(400, "没有可更新内容")
        values.append(step_id)
        conn.execute(
            f"UPDATE docx_workflow_steps SET {', '.join(assignments)} WHERE id = ?",
            tuple(values),
        )
        updated = fetch_one(conn, "SELECT * FROM docx_workflow_steps WHERE id = ?", (step_id,))
        package = fetch_docx_run_package(conn, updated["run_id"])
        return next(step for step in package["steps"] if step["id"] == step_id)


def update_docx_run_status_after_step(conn, run_id: str, image_model: str, size: str, quality: str) -> None:
    steps = fetch_docx_steps(conn, run_id)
    failed_steps = [step for step in steps if step.get("status") == "failed"]
    all_success = len(steps) == 9 and all(step.get("status") == "success" for step in steps)
    if failed_steps:
        status = "failed"
        error = "；".join(f"{step['title']}: {step.get('error') or ''}" for step in failed_steps[:3])
    elif all_success:
        status = "success"
        error = ""
    else:
        status = "partial"
        error = ""
    conn.execute(
        """
        UPDATE docx_workflow_runs
        SET status = ?, error = ?, image_model = ?, size = ?, quality = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, error, image_model or "", size, quality, now_iso(), run_id),
    )


def update_project_workflow_status(conn: sqlite3.Connection, project_id: str) -> None:
    rows = conn.execute(
        "SELECT status FROM project_workflow_steps WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    statuses = [r["status"] for r in rows]
    if not statuses:
        return
    if all(s == "success" for s in statuses):
        new_status = "success"
    elif any(s == "failed" for s in statuses):
        new_status = "failed"
    elif any(s == "running" for s in statuses):
        new_status = "running"
    elif any(s == "success" for s in statuses):
        new_status = "partial"
    else:
        new_status = "idle"
    conn.execute(
        "UPDATE projects SET workflow_status = ?, updated_at = ? WHERE id = ?",
        (new_status, now_iso(), project_id),
    )


# DEPRECATED — use POST /api/projects/workflow/steps/{step_id}/generate instead
@app.post("/api/docx-workflow/steps/{step_id}/generate")
def regenerate_docx_workflow_step(step_id: str, payload: DocxWorkflowGenerateIn | None = None) -> dict:
    payload = payload or DocxWorkflowGenerateIn()
    with get_db() as conn:
        step = fetch_one(conn, "SELECT * FROM docx_workflow_steps WHERE id = ?", (step_id,))
        run = fetch_one(conn, "SELECT * FROM docx_workflow_runs WHERE id = ?", (step["run_id"],))
        steps = fetch_docx_steps(conn, run["id"])
        step_by_stage = {item["stage_id"]: item for item in steps}
        refs = normalized_docx_refs(step)
        asset_ids = [ref["id"] for ref in refs if ref["type"] == "asset"]
        assets = get_assets_by_ids(conn, list(dict.fromkeys(asset_ids)))
        asset_by_id = {asset["id"]: asset for asset in assets}
        missing_assets = [asset_id for asset_id in dict.fromkeys(asset_ids) if asset_id not in asset_by_id]
        if missing_assets:
            raise HTTPException(400, "流程参考图缺失或已删除")
        wrong_project = [asset["original_name"] for asset in assets if asset["project_id"] != run["project_id"]]
        if wrong_project:
            raise HTTPException(400, "只能选择当前项目下的参考图")
        missing_files = missing_asset_file_names(assets)
        if missing_files:
            raise HTTPException(400, "参考图文件不存在，请重新上传：" + "、".join(missing_files))
        conn.execute(
            """
            UPDATE docx_workflow_steps
            SET status = ?, error = ?, image_path = '', params_json = ?, updated_at = ?
            WHERE id = ?
            """,
            ("running", "", to_json({}), now_iso(), step_id),
        )
        conn.execute(
            "UPDATE docx_workflow_runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            ("running", "", now_iso(), run["id"]),
        )

    size = payload.size or run.get("size") or "1024x1024"
    quality = payload.quality or run.get("quality") or "high"
    image_model = payload.image_model or run.get("image_model") or None
    image_response: dict[str, Any] = {}
    try:
        input_paths: list[Path] = []
        for ref in refs:
            if ref["type"] == "asset":
                input_paths.append(Path(asset_by_id[ref["id"]]["file_path"]))
            elif ref["type"] == "step":
                source_step = step_by_stage.get(ref["id"])
                source_path = Path(source_step.get("image_path") or "") if source_step else Path("")
                if not source_step or not source_path.is_file():
                    raise HTTPException(400, f"缺少前置步骤结果，请先生成：{ref['id']}")
                input_paths.append(source_path)
        image_response = call_image_model(step["prompt"], input_paths, size=size, quality=quality, model=image_model)
        out_dir = UPLOAD_DIR / run["project_id"] / "docx_workflow" / run["id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        image_path = out_dir / f"{step['generation_order']:02d}_{step['stage_id']}_{new_id()}.png"
        image_path.write_bytes(base64.b64decode(image_response["b64_json"]))
        params = {
            "size": size,
            "quality": quality,
            "image_model": image_response.get("model") or image_model or "",
            "image_api_type": image_response.get("api_type") or "",
            **reference_ids_by_type(refs),
            **(image_response.get("params") or {}),
        }
        with get_db() as conn:
            conn.execute(
                """
                UPDATE docx_workflow_steps
                SET image_path = ?, params_json = ?, status = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(image_path), to_json(params), "success", "", now_iso(), step_id),
            )
            update_docx_run_status_after_step(conn, run["id"], image_response.get("model") or image_model or "", size, quality)
            return fetch_docx_run_package(conn, run["id"])
    except Exception as exc:
        error = str(exc)
        with get_db() as conn:
            conn.execute(
                """
                UPDATE docx_workflow_steps
                SET params_json = ?, status = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    to_json(
                        {
                            "size": size,
                            "quality": quality,
                            "image_model": image_response.get("model") or image_model or "",
                            **reference_ids_by_type(refs),
                        }
                    ),
                    "failed",
                    error,
                    now_iso(),
                    step_id,
                ),
            )
            update_docx_run_status_after_step(conn, run["id"], image_response.get("model") or image_model or "", size, quality)
            return fetch_docx_run_package(conn, run["id"])


# DEPRECATED — use POST /api/projects/workflow/steps/{step_id}/knowledge-candidate instead
@app.post("/api/docx-workflow/steps/{step_id}/knowledge-candidate")
def create_docx_knowledge_candidate(step_id: str, payload: KnowledgeCandidateIn) -> dict:
    with get_db() as conn:
        step = fetch_one(conn, "SELECT * FROM docx_workflow_steps WHERE id = ?", (step_id,))
        run = fetch_one(conn, "SELECT * FROM docx_workflow_runs WHERE id = ?", (step["run_id"],))
        image_path = Path(step.get("image_path") or "")
        if step.get("status") != "success" or not image_path.is_file():
            raise HTTPException(400, "只有已成功生成的图片可以标记为知识库候选")
        candidate_id = new_id()
        conn.execute(
            """
            INSERT INTO docx_knowledge_candidates
            (id, project_id, run_id, step_id, image_path, rating, review_notes,
             suggested_category, suggested_scene, suggested_image_type, suggested_metadata_json,
             status, created_at, ingested_rag_image_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                run["project_id"],
                run["id"],
                step_id,
                str(image_path),
                payload.rating,
                payload.review_notes,
                payload.suggested_category,
                payload.suggested_scene,
                payload.suggested_image_type,
                to_json(payload.suggested_metadata),
                "pending",
                now_iso(),
                "",
            ),
        )
        return row_to_dict(conn.execute("SELECT * FROM docx_knowledge_candidates WHERE id = ?", (candidate_id,)).fetchone())


def _cleanup_task(run_id: str) -> None:
    with _active_tasks_lock:
        _active_tasks.pop(run_id, None)


def _run_generation_in_background(
    run_id: str,
    image_model: str | None,
    size: str,
    quality: str,
) -> None:
    try:
        with get_db() as conn:
            run = fetch_one(conn, "SELECT * FROM docx_workflow_runs WHERE id = ?", (run_id,))
            steps = fetch_docx_steps(conn, run_id)
            asset_ids = []
            for step in steps:
                for ref in normalized_docx_refs(step):
                    if ref["type"] == "asset":
                        asset_ids.append(ref["id"])
            assets = get_assets_by_ids(conn, list(dict.fromkeys(asset_ids)))
            asset_by_id = {asset["id"]: asset for asset in assets}

        project_id = run["project_id"]
        stage_output_paths: dict[str, Path] = {}
        errors: list[str] = []

        def run_step(step: dict) -> tuple[bool, str, str, Path | None]:
            refs = normalized_docx_refs(step)
            image_response: dict[str, Any] = {}
            try:
                input_paths: list[Path] = []
                for ref in refs:
                    if ref["type"] == "asset":
                        input_paths.append(Path(asset_by_id[ref["id"]]["file_path"]))
                    elif ref["type"] == "step":
                        stage_path = stage_output_paths.get(ref["id"])
                        if not stage_path:
                            raise RuntimeError(f"缺少前置步骤结果: {ref['id']}")
                        input_paths.append(stage_path)

                image_response = call_image_model(step["prompt"], input_paths, size=size, quality=quality, model=image_model)
                out_dir = UPLOAD_DIR / project_id / "docx_workflow" / run_id
                out_dir.mkdir(parents=True, exist_ok=True)
                image_path = out_dir / f"{step['generation_order']:02d}_{step['stage_id']}_{new_id()}.png"
                image_path.write_bytes(base64.b64decode(image_response["b64_json"]))
                params = {
                    "size": size,
                    "quality": quality,
                    "image_model": image_response.get("model") or image_model or "",
                    "image_api_type": image_response.get("api_type") or "",
                    **reference_ids_by_type(refs),
                    **(image_response.get("params") or {}),
                }
                with get_db() as conn:
                    conn.execute(
                        """
                        UPDATE docx_workflow_steps
                        SET image_path = ?, params_json = ?, status = ?, error = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (str(image_path), to_json(params), "success", "", now_iso(), step["id"]),
                    )
                return True, step["stage_id"], "", image_path
            except Exception as exc:
                error = str(exc)
                with get_db() as conn:
                    conn.execute(
                        """
                        UPDATE docx_workflow_steps
                        SET params_json = ?, status = ?, error = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            to_json(
                                {
                                    "size": size,
                                    "quality": quality,
                                    "image_model": image_response.get("model") or image_model or "",
                                    **reference_ids_by_type(refs),
                                }
                            ),
                            "failed",
                            error,
                            now_iso(),
                            step["id"],
                        ),
                    )
                return False, step["stage_id"], error, None

        first_step = steps[0]
        ok, stage_id, error, image_path = run_step(first_step)
        if ok and image_path:
            stage_output_paths[stage_id] = image_path
        else:
            errors.append(f"{first_step['title']}: {error}")

        if not errors:
            second_step = steps[1]
            ok, stage_id, error, image_path = run_step(second_step)
            if ok and image_path:
                stage_output_paths[stage_id] = image_path
            else:
                errors.append(f"{second_step['title']}: {error}")

        if not errors:
            parallel_steps = steps[2:]
            with ThreadPoolExecutor(max_workers=min(len(parallel_steps), 7)) as pool:
                futures = {pool.submit(run_step, step): step for step in parallel_steps}
                for future in as_completed(futures):
                    step = futures[future]
                    ok, stage_id, error, image_path = future.result()
                    if ok and image_path:
                        stage_output_paths[stage_id] = image_path
                    else:
                        errors.append(f"{step['title']}: {error}")

        with get_db() as conn:
            first_error = "；".join(errors[:3])
            conn.execute(
                """
                UPDATE docx_workflow_runs
                SET status = ?, error = ?, image_model = ?, size = ?, quality = ?, updated_at = ?
                WHERE id = ?
                """,
                ("success" if not errors else "failed", first_error, image_model or "", size, quality, now_iso(), run_id),
            )
    except Exception as exc:
        try:
            with get_db() as conn:
                conn.execute(
                    "UPDATE docx_workflow_runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                    ("failed", f"后台任务异常: {exc}", now_iso(), run_id),
                )
        except Exception:
            pass
    finally:
        _cleanup_task(run_id)


def _run_project_workflow_in_background(project_id: str, image_model: str | None, size: str, quality: str) -> None:
    def run_step(step_id: str) -> bool:
        with get_db() as conn:
            step = row_to_dict(conn.execute("SELECT * FROM project_workflow_steps WHERE id = ?", (step_id,)).fetchone())
            project = row_to_dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())
        if not step:
            return False

        prompt = step.get("prompt") or ""
        if not prompt.strip():
            with get_db() as conn:
                conn.execute("UPDATE project_workflow_steps SET status = 'failed', error = '提示词为空', updated_at = ? WHERE id = ?", (now_iso(), step_id))
            return False

        input_paths: list[str] = []
        refs = step.get("input_refs") or []
        for ref in refs:
            if ref.get("type") == "asset":
                with get_db() as conn:
                    asset = conn.execute("SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL", (ref["id"],)).fetchone()
                if asset:
                    asset = row_to_dict(asset)
                    if asset.get("file_path") and Path(asset["file_path"]).is_file():
                        input_paths.append(asset["file_path"])
            elif ref.get("type") == "step":
                src_path = stage_output_paths.get(ref["id"])
                if src_path and Path(src_path).is_file():
                    input_paths.append(src_path)

        with get_db() as conn:
            conn.execute("UPDATE project_workflow_steps SET status = 'running', error = '', updated_at = ? WHERE id = ?", (now_iso(), step_id))

        retries = 3
        last_error = ""
        for attempt in range(retries):
            try:
                result = call_image_model(prompt=prompt, image_paths=[Path(p) for p in input_paths], model=image_model, size=size, quality=quality)
                step_dir = Path(DATA_DIR) / "projects" / project_id / "docx_workflow" / "_project_steps"
                step_dir.mkdir(parents=True, exist_ok=True)
                stage_id = re.sub(r"[^A-Za-z0-9_-]+", "_", step.get("stage_id") or "image").strip("_")
                filename = f"{int(step.get('image_no') or 0):02d}_{stage_id}.png"
                out_path = step_dir / filename
                image_bytes, response_params = project_image_response_to_bytes(result)
                with open(out_path, "wb") as f:
                    f.write(image_bytes)
                params = {
                    "size": size,
                    "quality": quality,
                    "image_model": response_params.get("model") or image_model or "",
                    "image_api_type": response_params.get("api_type") or "",
                    **reference_ids_by_type(refs),
                    **(response_params.get("params") or {}),
                }
                with get_db() as conn:
                    conn.execute(
                        "UPDATE project_workflow_steps SET status = 'success', image_path = ?, params_json = ?, error = '', updated_at = ? WHERE id = ?",
                        (str(out_path), to_json(params), now_iso(), step_id),
                    )
                stage_output_paths[step["stage_id"]] = str(out_path)
                return True
            except Exception as exc:
                last_error = str(exc)[:500]
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        with get_db() as conn:
            conn.execute("UPDATE project_workflow_steps SET status = 'failed', error = ?, updated_at = ? WHERE id = ?", (last_error, now_iso(), step_id))
        return False

    stage_output_paths: dict[str, str] = {}

    with get_db() as conn:
        step_rows = conn.execute(
            "SELECT id, stage_id, generation_order FROM project_workflow_steps WHERE project_id = ? ORDER BY generation_order ASC",
            (project_id,),
        ).fetchall()

    steps_info = [{"id": r["id"], "stage_id": r["stage_id"], "order": r["generation_order"]} for r in step_rows]

    for i in range(min(2, len(steps_info))):
        success = run_step(steps_info[i]["id"])
        if not success:
            with get_db() as conn:
                conn.execute("UPDATE projects SET workflow_status = 'failed', workflow_error = '步骤失败', updated_at = ? WHERE id = ?", (now_iso(), project_id))
            return

    parallel_steps = steps_info[2:]
    if parallel_steps:
        with ThreadPoolExecutor(max_workers=min(len(parallel_steps), 7)) as executor:
            futures = {executor.submit(run_step, s["id"]): s for s in parallel_steps}
            for future in as_completed(futures):
                future.result()

    with get_db() as conn:
        update_project_workflow_status(conn, project_id)


def _cleanup_project_task(project_id: str) -> None:
    with _active_tasks_lock:
        _active_tasks.pop(project_id, None)


@app.post("/api/projects/{project_id}/workflow")
def init_project_workflow(project_id: str, payload: DocxWorkflowRunIn) -> dict:
    payload.project_id = project_id
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        validated = validate_docx_workflow_input(conn, payload)
        fit_front = payload.fit_front_asset_id or payload.fit_asset_id
        fit_side = payload.fit_side_asset_id or payload.fit_asset_id
        fit_back = payload.fit_back_asset_id or payload.fit_asset_id
        conn.execute(
            """UPDATE projects SET
               product_name = ?, material = ?, style_key = ?,
               product_asset_id = ?, model_asset_id = ?,
               fit_front_asset_id = ?, fit_side_asset_id = ?, fit_back_asset_id = ?,
               scene_asset_id = ?, accessory_asset_id = ?,
               image_model = ?, size = ?, quality = ?,
               workflow_status = 'idle', workflow_error = '', updated_at = ?
               WHERE id = ?""",
            (
                payload.product_name, payload.material, payload.style_key,
                payload.product_asset_id, payload.model_asset_id,
                fit_front, fit_side, fit_back,
                payload.scene_asset_id, payload.accessory_asset_id,
                payload.image_model or "", payload.size, payload.quality,
                now_iso(), project_id,
            ),
        )
        conn.execute("DELETE FROM project_workflow_steps WHERE project_id = ?", (project_id,))
        insert_project_workflow_steps(conn, project_id, payload)
        return fetch_project_workflow_package(conn, project_id)


@app.get("/api/projects/{project_id}/workflow")
def get_project_workflow(project_id: str) -> dict:
    with get_db() as conn:
        return fetch_project_workflow_package(conn, project_id)


@app.post("/api/projects/{project_id}/workflow/preview")
def preview_project_workflow(project_id: str) -> dict:
    with get_db() as conn:
        return fetch_project_workflow_package(conn, project_id)


@app.post("/api/projects/{project_id}/workflow/generate")
def generate_project_workflow(project_id: str, payload: DocxWorkflowGenerateIn) -> dict:
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        steps = fetch_project_workflow_steps(conn, project_id)
        if len(steps) != 9:
            raise HTTPException(400, "工作流步骤不完整，需要 9 步")
        if payload.image_model or payload.size or payload.quality:
            conn.execute(
                "UPDATE projects SET image_model = COALESCE(?, image_model), size = COALESCE(?, size), quality = COALESCE(?, quality), updated_at = ? WHERE id = ?",
                (payload.image_model, payload.size, payload.quality, now_iso(), project_id),
            )
        conn.execute(
            "UPDATE projects SET workflow_status = 'running', workflow_error = '', updated_at = ? WHERE id = ?",
            (now_iso(), project_id),
        )
        conn.execute(
            "UPDATE project_workflow_steps SET status = 'pending', error = '', image_path = '', params_json = '{}', updated_at = ? WHERE project_id = ?",
            (now_iso(), project_id),
        )

    size = payload.size or project.get("size") or "1024x1024"
    quality = payload.quality or project.get("quality") or "high"
    image_model = payload.image_model or project.get("image_model") or None

    thread = threading.Thread(
        target=_run_project_workflow_in_background,
        args=(project_id, image_model, size, quality),
        daemon=True,
    )
    with _active_tasks_lock:
        _active_tasks[project_id] = thread
    thread.start()

    with get_db() as conn:
        return fetch_project_workflow_package(conn, project_id)


@app.get("/api/projects/{project_id}/workflow/download")
def download_project_workflow(project_id: str) -> Response:
    with get_db() as conn:
        package = fetch_project_workflow_package(conn, project_id)
    steps = sorted(package.get("steps") or [], key=lambda item: item.get("generation_order") or item.get("image_no") or 0)
    ready_steps = [step for step in steps if step.get("image_path") and Path(step["image_path"]).is_file()]
    if len(ready_steps) < 9:
        raise HTTPException(400, "还没有生成完整 9 张图，无法下载")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for step in ready_steps:
            src = Path(step["image_path"])
            stage_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(step.get("stage_id") or "image")).strip("_")
            filename = f"{int(step.get('image_no') or 0):02d}_{stage_id}{src.suffix or '.png'}"
            zf.write(src, filename)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(package.get("product_name") or "docx_workflow")).strip("_") or "docx_workflow"
    with get_db() as conn:
        conn.execute("UPDATE projects SET downloaded_at = ? WHERE id = ?", (now_iso(), project_id))
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_{project_id[:8]}_images.zip"'},
    )


@app.patch("/api/projects/workflow/steps/{step_id}")
def update_project_workflow_step(step_id: str, payload: DocxWorkflowStepUpdateIn) -> dict:
    with get_db() as conn:
        step = fetch_one(conn, "SELECT * FROM project_workflow_steps WHERE id = ?", (step_id,))
        assignments = ["status = ?", "error = ?", "updated_at = ?"]
        values: list[Any] = ["pending", "", now_iso()]
        if payload.prompt is not None:
            prompt = payload.prompt.strip()
            if not prompt:
                raise HTTPException(400, "提示词不能为空")
            assignments.insert(0, "prompt = ?")
            values.insert(0, prompt)
        if payload.input_refs is not None:
            refs: list[dict[str, str]] = []
            for item in payload.input_refs:
                ref_type = (item.get("type") or "").strip()
                ref_id = (item.get("id") or "").strip()
                if ref_type not in ("asset", "step"):
                    raise HTTPException(400, f"无效的引用类型: {ref_type}")
                if not ref_id:
                    raise HTTPException(400, "引用 ID 不能为空")
                if ref_type == "asset":
                    asset = fetch_one(conn, "SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL", (ref_id,))
                    if asset["project_id"] != step["project_id"]:
                        raise HTTPException(400, f"素材 {ref_id} 不属于当前项目")
                elif ref_type == "step":
                    src_step = conn.execute(
                        "SELECT * FROM project_workflow_steps WHERE id = ? OR (stage_id = ? AND project_id = ?)",
                        (ref_id, ref_id, step["project_id"]),
                    ).fetchone()
                    if not src_step:
                        raise HTTPException(404, f"步骤 {ref_id} 不存在")
                    src_step = row_to_dict(src_step)
                    if src_step["project_id"] != step["project_id"]:
                        raise HTTPException(400, f"步骤 {ref_id} 不属于当前项目")
                refs.append({"type": ref_type, "id": ref_id})
            assignments.insert(0, "input_refs_json = ?")
            values.insert(0, to_json(refs))
        values.append(step_id)
        conn.execute(
            f"UPDATE project_workflow_steps SET {', '.join(assignments)} WHERE id = ?",
            tuple(values),
        )
        project_id = step["project_id"]
        return fetch_project_workflow_package(conn, project_id)


class PoseRefUpdateIn(BaseModel):
    pose_asset_id: str = ""


@app.patch("/api/projects/workflow/steps/{step_id}/pose-ref")
def update_step_pose_ref(step_id: str, payload: PoseRefUpdateIn) -> dict:
    with get_db() as conn:
        step = fetch_one(conn, "SELECT * FROM project_workflow_steps WHERE id = ?", (step_id,))
        refs = normalized_docx_refs(step)
        non_pose_refs = [r for r in refs if not (r.get("type") == "asset" and _is_pose_asset(conn, r.get("id", "")))]
        if payload.pose_asset_id.strip():
            non_pose_refs.append({"type": "asset", "id": payload.pose_asset_id.strip()})
        conn.execute(
            "UPDATE project_workflow_steps SET input_refs_json = ?, updated_at = ? WHERE id = ?",
            (to_json(non_pose_refs), now_iso(), step_id),
        )
        project_id = step["project_id"]
        return fetch_project_workflow_package(conn, project_id)


def _is_pose_asset(conn, asset_id: str) -> bool:
    if not asset_id:
        return False
    row = conn.execute("SELECT slot FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return bool(row and row[0] == "pose_reference")


@app.post("/api/projects/workflow/steps/{step_id}/generate")
def generate_project_workflow_step(step_id: str, payload: DocxWorkflowGenerateIn) -> dict:
    with get_db() as conn:
        step = fetch_one(conn, "SELECT * FROM project_workflow_steps WHERE id = ?", (step_id,))
        project_id = step["project_id"]
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))

    input_paths: list[str] = []
    refs = step.get("input_refs") or []
    with get_db() as conn:
        all_steps = [row_to_dict(r) for r in conn.execute(
            "SELECT * FROM project_workflow_steps WHERE project_id = ?", (project_id,)
        ).fetchall()]
    step_by_stage = {s["stage_id"]: s for s in all_steps}
    for ref in refs:
        if ref.get("type") == "asset":
            with get_db() as conn:
                asset = conn.execute("SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL", (ref["id"],)).fetchone()
            if asset:
                asset = row_to_dict(asset)
                if asset.get("file_path") and Path(asset["file_path"]).is_file():
                    input_paths.append(asset["file_path"])
        elif ref.get("type") == "step":
            src = step_by_stage.get(ref["id"])
            if src and src.get("image_path") and Path(src["image_path"]).is_file():
                input_paths.append(src["image_path"])

    prompt = step.get("prompt") or ""
    if not prompt.strip():
        raise HTTPException(400, "提示词为空，无法生成")

    with get_db() as conn:
        conn.execute("UPDATE project_workflow_steps SET status = 'running', error = '', updated_at = ? WHERE id = ?", (now_iso(), step_id))

    size = payload.size or project.get("size") or "1024x1024"
    quality = payload.quality or project.get("quality") or "high"
    image_model = payload.image_model or project.get("image_model") or None

    try:
        result = call_image_model(prompt=prompt, image_paths=[Path(p) for p in input_paths], model=image_model, size=size, quality=quality)
        step_dir = Path(DATA_DIR) / "projects" / project_id / "docx_workflow" / "_project_steps"
        step_dir.mkdir(parents=True, exist_ok=True)
        stage_id = re.sub(r"[^A-Za-z0-9_-]+", "_", step.get("stage_id") or "image").strip("_")
        filename = f"{int(step.get('image_no') or 0):02d}_{stage_id}.png"
        out_path = step_dir / filename
        image_bytes, response_params = project_image_response_to_bytes(result)
        with open(out_path, "wb") as f:
            f.write(image_bytes)
        params = {
            "size": size,
            "quality": quality,
            "image_model": response_params.get("model") or image_model or "",
            "image_api_type": response_params.get("api_type") or "",
            **reference_ids_by_type(refs),
            **(response_params.get("params") or {}),
        }
        with get_db() as conn:
            conn.execute(
                "UPDATE project_workflow_steps SET status = 'success', image_path = ?, params_json = ?, error = '', updated_at = ? WHERE id = ?",
                (str(out_path), to_json(params), now_iso(), step_id),
            )
            update_project_workflow_status(conn, project_id)
    except Exception as exc:
        with get_db() as conn:
            conn.execute(
                "UPDATE project_workflow_steps SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                (str(exc)[:500], now_iso(), step_id),
            )
            update_project_workflow_status(conn, project_id)
        raise HTTPException(500, f"图片生成失败: {exc}")

    with get_db() as conn:
        return fetch_project_workflow_package(conn, project_id)


@app.post("/api/projects/workflow/steps/{step_id}/knowledge-candidate")
def mark_project_step_knowledge_candidate(step_id: str, payload: KnowledgeCandidateIn) -> dict:
    with get_db() as conn:
        step = fetch_one(conn, "SELECT * FROM project_workflow_steps WHERE id = ?", (step_id,))
        if step["status"] != "success" or not step.get("image_path"):
            raise HTTPException(400, "只能标记已成功生成的步骤")
        project_id = step["project_id"]
        candidate_id = new_id()
        conn.execute(
            """INSERT INTO docx_knowledge_candidates
               (id, project_id, step_id, image_path, rating, review_notes,
                suggested_category, suggested_scene, suggested_image_type,
                suggested_metadata_json, status, created_at, ingested_rag_image_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, '')""",
            (
                candidate_id, project_id, step_id, step["image_path"],
                payload.rating, payload.review_notes,
                payload.suggested_category, payload.suggested_scene, payload.suggested_image_type,
                to_json(payload.suggested_metadata), now_iso(),
            ),
        )
        return {"id": candidate_id, "status": "pending"}


@app.get("/api/users")
def list_users() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]


@app.post("/api/users")
def create_user(payload: UserIn) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "用户名不能为空")
    with get_db() as conn:
        user_id = new_id()
        ts = now_iso()
        conn.execute(
            "INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)",
            (user_id, name, ts),
        )
        return dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


@app.delete("/api/users/{user_id}")
def delete_user(user_id: str) -> dict:
    if user_id == "default":
        raise HTTPException(400, "不能删除默认用户")
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "用户不存在")
        conn.execute("UPDATE projects SET user_id = 'default' WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return {"ok": True}


@app.get("/api/projects")
def list_projects(
    sku: str = Query("", description="SKU fuzzy search"),
    user_id: str = Query("", description="Filter by user"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    with get_db() as conn:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id.strip():
            conditions.append("user_id = ?")
            params.append(user_id.strip())
        if sku.strip():
            conditions.append("sku LIKE ?")
            params.append(f"%{sku.strip()}%")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        rows = conn.execute(
            f"SELECT * FROM projects {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            tuple(params),
        ).fetchall()
        results = []
        for row in rows:
            project = row_to_dict(row)
            step_rows = conn.execute(
                "SELECT status FROM project_workflow_steps WHERE project_id = ?",
                (project["id"],),
            ).fetchall()
            statuses = [s["status"] for s in step_rows]
            project["step_summary"] = {
                "total": len(statuses),
                "success": statuses.count("success"),
                "failed": statuses.count("failed"),
                "running": statuses.count("running"),
                "pending": statuses.count("pending"),
            }
            project["has_downloads"] = bool(project.get("downloaded_at"))
            results.append(project)
        return results


@app.post("/api/projects")
def create_project(payload: ProjectIn) -> dict:
    sku = payload.sku.strip()
    if not sku:
        raise HTTPException(400, "SKU 为必填项")
    with get_db() as conn:
        ts = now_iso()
        project_id = new_id()
        name = payload.name.strip() or sku
        conn.execute(
            "INSERT INTO projects (id, user_id, sku, category, name, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, payload.user_id or "default", sku, payload.category.strip(), name, payload.notes, ts, ts),
        )
        return fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        assets = conn.execute(
            "SELECT * FROM assets WHERE project_id = ? AND deleted_at IS NULL ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        project["assets"] = [hydrate_asset(row_to_dict(row)) for row in assets]
        workflow_steps = conn.execute(
            "SELECT * FROM project_workflow_steps WHERE project_id = ? ORDER BY generation_order ASC",
            (project_id,),
        ).fetchall()
        project["workflow_steps"] = [hydrate_docx_step(row_to_dict(row)) for row in workflow_steps]
        return project


@app.get("/api/projects/{project_id}/rag-references")
def list_project_rag_references(project_id: str) -> list[dict]:
    with get_db() as conn:
        return get_rag_references_for_project(conn, project_id)


@app.post("/api/projects/{project_id}/rag-references")
def add_project_rag_reference(project_id: str, payload: RagReferenceIn) -> dict:
    rag_image_id = payload.rag_image_id.strip()
    if not rag_image_id:
        raise HTTPException(400, "rag_image_id 不能为空")
    usage_tags = normalize_usage_tags(payload.usage_tags)
    with get_db() as conn:
        fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        existing = conn.execute(
            "SELECT * FROM rag_reference_selections WHERE project_id = ? AND rag_image_id = ?",
            (project_id, rag_image_id),
        ).fetchone()
        ts = now_iso()
        if existing:
            reference_id = existing["id"]
            conn.execute(
                """
                UPDATE rag_reference_selections
                SET filename = ?, category = ?, scene = ?, image_type = ?, caption = ?, score = ?,
                    usage_tags_json = ?, metadata_json = ?, notes = ?, model_description = ?, asset_type = ?,
                    rag_role = ?
                WHERE id = ?
                """,
                (
                    payload.filename,
                    payload.category,
                    payload.scene,
                    payload.image_type,
                    payload.caption,
                    payload.score,
                    to_json(usage_tags),
                    to_json(payload.metadata),
                    payload.notes,
                    payload.model_description,
                    payload.asset_type,
                    payload.rag_role,
                    reference_id,
                ),
            )
        else:
            reference_id = new_id()
            max_sort = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) FROM rag_reference_selections WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO rag_reference_selections
                (id, project_id, rag_image_id, filename, category, scene, image_type, caption, score,
                 usage_tags_json, metadata_json, sort_order, selected_at, notes, model_description, asset_type, rag_role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference_id,
                    project_id,
                    rag_image_id,
                    payload.filename,
                    payload.category,
                    payload.scene,
                    payload.image_type,
                    payload.caption,
                    payload.score,
                    to_json(usage_tags),
                    to_json(payload.metadata),
                    int(max_sort) + 1,
                    ts,
                    payload.notes,
                    payload.model_description,
                    payload.asset_type,
                    payload.rag_role,
                ),
            )
        return fetch_rag_reference(conn, project_id, reference_id)


@app.patch("/api/projects/{project_id}/rag-references/{reference_id}")
def update_project_rag_reference(project_id: str, reference_id: str, payload: RagReferenceUpdateIn) -> dict:
    assignments: list[str] = []
    values: list[Any] = []
    if payload.usage_tags is not None:
        assignments.append("usage_tags_json = ?")
        values.append(to_json(normalize_usage_tags(payload.usage_tags)))
    if payload.notes is not None:
        assignments.append("notes = ?")
        values.append(payload.notes)
    if payload.model_description is not None:
        assignments.append("model_description = ?")
        values.append(payload.model_description)
    if payload.sort_order is not None:
        assignments.append("sort_order = ?")
        values.append(int(payload.sort_order))
    if payload.rag_role is not None:
        assignments.append("rag_role = ?")
        values.append(payload.rag_role)
    if not assignments:
        raise HTTPException(400, "没有可更新字段")
    with get_db() as conn:
        fetch_rag_reference(conn, project_id, reference_id)
        values.extend([reference_id, project_id])
        conn.execute(
            f"UPDATE rag_reference_selections SET {', '.join(assignments)} WHERE id = ? AND project_id = ?",
            tuple(values),
        )
        return fetch_rag_reference(conn, project_id, reference_id)


@app.delete("/api/projects/{project_id}/rag-references/{reference_id}")
def delete_project_rag_reference(project_id: str, reference_id: str) -> dict:
    with get_db() as conn:
        fetch_rag_reference(conn, project_id, reference_id)
        conn.execute(
            "DELETE FROM rag_reference_selections WHERE id = ? AND project_id = ?",
            (reference_id, project_id),
        )
        return {"ok": True}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    with get_db() as conn:
        fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return {"ok": True}


@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: str) -> dict:
    with get_db() as conn:
        asset = fetch_one(conn, "SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL", (asset_id,))
        disk_path = Path(asset["file_path"])
        if disk_path.exists():
            disk_path.unlink()
        conn.execute("UPDATE assets SET deleted_at = ? WHERE id = ?", (now_iso(), asset_id))
    return {"ok": True}


@app.post("/api/assets")
def upload_assets(
    project_id: str = Form(...),
    asset_type: str = Form(...),
    source_url: str = Form(""),
    asin: str = Form(""),
    keyword: str = Form(""),
    slot: str = Form(""),
    notes: str = Form(""),
    files: list[UploadFile] = File(...),
) -> list[dict]:
    if asset_type not in {"product", "model", "competitor"}:
        raise HTTPException(400, "asset_type 必须是 product/model/competitor")
    with get_db() as conn:
        fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        saved = []
        target_dir = UPLOAD_DIR / project_id / asset_type
        target_dir.mkdir(parents=True, exist_ok=True)
        for upload in files:
            asset_id = new_id()
            suffix = Path(upload.filename or "image.png").suffix or ".png"
            disk_path = target_dir / f"{asset_id}{suffix}"
            with disk_path.open("wb") as fh:
                shutil.copyfileobj(upload.file, fh)
            ts = now_iso()
            conn.execute(
                """
                INSERT INTO assets
                (id, project_id, asset_type, original_name, file_path, mime_type, source_url, asin, keyword, slot, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    project_id,
                    asset_type,
                    upload.filename or disk_path.name,
                    str(disk_path),
                    upload.content_type or "application/octet-stream",
                    source_url,
                    asin,
                    keyword,
                    slot,
                    notes,
                    ts,
                ),
            )
            saved.append(hydrate_asset(fetch_one(conn, "SELECT * FROM assets WHERE id = ?", (asset_id,))))
        return saved


@app.patch("/api/assets/{asset_id}")
def update_asset(asset_id: str, payload: dict[str, Any]) -> dict:
    allowed = {"source_url", "asin", "keyword", "slot", "notes"}
    fields = {k: str(v) for k, v in payload.items() if k in allowed}
    if not fields:
        raise HTTPException(400, "没有可更新字段")
    with get_db() as conn:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(f"UPDATE assets SET {assignments} WHERE id = ?", (*fields.values(), asset_id))
        return hydrate_asset(fetch_one(conn, "SELECT * FROM assets WHERE id = ?", (asset_id,)))
