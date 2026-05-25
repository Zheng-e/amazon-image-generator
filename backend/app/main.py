from __future__ import annotations

import base64
import io
import json
import re
import shutil
import sys
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

from .ai_clients import available_analysis_models, available_image_models, call_image_model, call_text_model, image_to_data_url
from .db import (
    DATA_DIR,
    UPLOAD_DIR,
    create_schema_snapshot,
    from_json,
    get_db,
    init_db,
    new_id,
    now_iso,
    row_to_dict,
    to_json,
)
from .defaults import FIELD_TYPES, OUTPUT_LABELS
from .docx_workflow import STYLE_OPTIONS, build_workflow_steps, style_options_payload


app = FastAPI(title="设计部主图生成字段实验台", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)


app.mount("/files", StaticFiles(directory=str(DATA_DIR)), name="files")
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/workbench", StaticFiles(directory=str(STATIC_DIR), html=True), name="workbench")


class ProjectIn(BaseModel):
    sku: str
    category: str = ""
    name: str = ""
    notes: str = ""


class SchemaIn(BaseModel):
    name: str
    fields: list[dict[str, Any]]


class ProductFactsIn(BaseModel):
    project_id: str
    values: dict[str, Any]
    notes: str = ""


class CompetitorAnalysisIn(BaseModel):
    project_id: str
    asset_id: str
    model_name: str | None = None


class CompetitorBatchIn(BaseModel):
    project_id: str
    asset_ids: list[str]
    model_name: str | None = None


class CategoryStandardIn(BaseModel):
    project_id: str
    competitor_output_ids: list[str]


class CategoryStandardFromImagesIn(BaseModel):
    project_id: str
    asset_ids: list[str]
    competitor_output_ids: list[str] = Field(default_factory=list)
    model_name: str | None = None


class CompareModelsIn(BaseModel):
    project_id: str
    output_type: str
    asset_ids: list[str] = Field(default_factory=list)
    competitor_output_ids: list[str] = Field(default_factory=list)
    model_names: list[str]


class ConfirmAnalysisResultIn(BaseModel):
    status: str = "confirmed"
    review_notes: str = ""
    rating: int | None = None


class OutputUpdateIn(BaseModel):
    values: dict[str, Any]
    status: str = "confirmed"
    notes: str = ""


class GenerationRunIn(BaseModel):
    project_id: str
    title: str
    image_goal: str
    supplemental_info: str = ""
    product_asset_ids: list[str] = Field(default_factory=list)
    model_asset_ids: list[str] = Field(default_factory=list)
    competitor_asset_ids: list[str] = Field(default_factory=list)
    competitor_output_ids: list[str] = Field(default_factory=list)
    category_output_id: str | None = None


class GenerateIn(BaseModel):
    size: str = "1024x1024"
    quality: str = "high"
    image_model: str | None = None


class WorkflowPreviewIn(BaseModel):
    project_id: str
    asset_ids: list[str] = Field(default_factory=list)
    product_asset_ids: list[str] = Field(default_factory=list)
    model_asset_ids: list[str] = Field(default_factory=list)
    model_name: str | None = None
    image_goals: list[str] = Field(default_factory=list)
    supplemental_info: str = ""


class WorkflowGenerateAllIn(BaseModel):
    project_id: str
    output_c_ids: list[str]
    output_d_id: str
    image_goals: list[str] = Field(default_factory=list)
    supplemental_info: str = ""
    product_asset_ids: list[str] = Field(default_factory=list)
    model_asset_ids: list[str] = Field(default_factory=list)
    competitor_asset_ids: list[str] = Field(default_factory=list)
    size: str = "1024x1024"
    quality: str = "high"
    image_model: str | None = None


class DynamicAnalysisPreviewIn(BaseModel):
    project_id: str
    asset_ids: list[str] = Field(default_factory=list)
    model_name: str | None = None
    supplemental_info: str = ""


class AnalysisDocumentUpdateIn(BaseModel):
    document: dict[str, Any]
    status: str = "draft"
    notes: str = ""


class AnalysisDocumentImportIn(BaseModel):
    project_id: str
    package: dict[str, Any]
    status: str = "confirmed"


class GenerateFromDocumentsIn(BaseModel):
    project_id: str
    competitor_document_ids: list[str] = Field(default_factory=list)
    category_document_id: str | None = None
    supplemental_info: str = ""
    product_asset_ids: list[str] = Field(default_factory=list)
    model_asset_ids: list[str] = Field(default_factory=list)
    competitor_asset_ids: list[str] = Field(default_factory=list)
    image_model: str | None = None
    size: str = "1024x1024"
    quality: str = "high"


class DocxWorkflowRunIn(BaseModel):
    project_id: str
    product_name: str
    material: str
    style_key: str = "natural_fashion"
    product_asset_id: str
    model_asset_id: str
    fit_asset_id: str
    scene_asset_id: str
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


class ReviewIn(BaseModel):
    rating: int | None = None
    review_notes: str = ""
    is_knowledge_candidate: bool = False


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


def hydrate_docx_step(step: dict | None) -> dict | None:
    if not step:
        return None
    step["url"] = file_url(step.get("image_path", ""))
    step["input_refs"] = normalized_docx_refs(step)
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


def validate_fields(fields: list[dict[str, Any]]) -> None:
    seen = set()
    for item in fields:
        key = str(item.get("key", "")).strip()
        if not key:
            raise HTTPException(400, "字段 key 不能为空")
        if key in seen:
            raise HTTPException(400, f"字段 key 重复: {key}")
        seen.add(key)
        if item.get("type") not in FIELD_TYPES:
            raise HTTPException(400, f"不支持的字段类型: {item.get('type')}")


def fetch_one(conn, query: str, params: tuple = ()) -> dict:
    row = conn.execute(query, params).fetchone()
    data = row_to_dict(row)
    if not data:
        raise HTTPException(404, "记录不存在")
    return data


def output_to_ai_instruction(output_type: str, fields: list[dict[str, Any]]) -> str:
    lines = []
    for field in fields:
        lines.append(
            f"- {field.get('key')}: {field.get('label')} | type={field.get('type')} | help={field.get('help_text', '')}"
        )
    return (
        f"Return JSON only. The JSON keys must exactly follow this {OUTPUT_LABELS.get(output_type, output_type)} schema:\n"
        + "\n".join(lines)
        + "\nIMPORTANT: All JSON string values (labels, descriptions, notes, reasons, summaries, etc.) MUST be written in Chinese (简体中文). Only \"key\" and \"type\" fields remain in English."
    )


def latest_confirmed_output(conn, project_id: str, output_type: str) -> dict:
    row = conn.execute(
        """
        SELECT * FROM structured_outputs
        WHERE project_id = ? AND output_type = ? AND status = 'confirmed'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (project_id, output_type),
    ).fetchone()
    data = row_to_dict(row)
    if not data:
        raise HTTPException(400, f"缺少已确认的 {OUTPUT_LABELS.get(output_type, output_type)}")
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


def fetch_docx_steps(conn, run_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM docx_workflow_steps
        WHERE run_id = ?
        ORDER BY generation_order ASC
        """,
        (run_id,),
    ).fetchall()
    return [hydrate_docx_step(row_to_dict(row)) for row in rows]


def fetch_docx_run_package(conn, run_id: str) -> dict:
    run = fetch_one(conn, "SELECT * FROM docx_workflow_runs WHERE id = ?", (run_id,))
    run["steps"] = attach_docx_reference_items(conn, run, fetch_docx_steps(conn, run_id))
    return run


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
    asset_ids = [
        payload.product_asset_id,
        payload.model_asset_id,
        payload.fit_asset_id,
        payload.scene_asset_id,
    ]
    assets = get_assets_by_ids(conn, list(dict.fromkeys(asset_ids)))
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
    steps = build_workflow_steps(
        product_name=payload.product_name.strip(),
        material=payload.material.strip(),
        style_key=payload.style_key,
        product_asset_id=payload.product_asset_id,
        model_asset_id=payload.model_asset_id,
        fit_asset_id=payload.fit_asset_id,
        scene_asset_id=payload.scene_asset_id,
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
                to_json({}),
                "pending",
                ts,
                ts,
            ),
        )


def create_structured_output(
    conn,
    project_id: str,
    output_type: str,
    values: dict[str, Any],
    status: str,
    notes: str = "",
    asset_id: str | None = None,
    schema_snapshot_id: str | None = None,
) -> dict:
    snapshot = {"id": schema_snapshot_id} if schema_snapshot_id else create_schema_snapshot(conn, output_type)
    output_id = new_id()
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO structured_outputs
        (id, project_id, output_type, asset_id, schema_snapshot_id, values_json, status, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (output_id, project_id, output_type, asset_id, snapshot["id"], to_json(values), status, notes, ts, ts),
    )
    return fetch_one(conn, "SELECT * FROM structured_outputs WHERE id = ?", (output_id,))


def get_schema_with_snapshot(conn, output_type: str) -> tuple[dict, dict]:
    schema = fetch_one(conn, "SELECT * FROM schema_definitions WHERE output_type = ?", (output_type,))
    snapshot = create_schema_snapshot(conn, output_type)
    return schema, snapshot


def build_single_competitor_content(asset: dict, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": (
                "You are analyzing one Amazon apparel competitor image for abstract structure only. "
                "Do not suggest copying the exact image, model, brand, layout, or text. "
                + output_to_ai_instruction("output_c", fields)
            ),
        },
        {"type": "image_url", "image_url": {"url": image_to_data_url(Path(asset["file_path"]))}},
    ]


MAX_OUTPUT_D_IMAGES = 12


def build_category_from_images_content(
    project: dict,
    assets: list[dict],
    fields: list[dict[str, Any]],
    competitor_outputs: list[dict] | None = None,
) -> list[dict[str, Any]]:
    condensed = []
    for o in (competitor_outputs or []):
        v = o.get("values", {})
        condensed.append({
            "image_role": v.get("image_role"),
            "subject_type": v.get("subject_type"),
            "background_type": v.get("background_type"),
            "composition": (v.get("composition") or "")[:120],
            "style_tags": v.get("style_tags", []),
            "quality_notes": v.get("quality_notes", []),
            "risk_notes": v.get("risk_notes", []),
        })
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Analyze these uploaded Amazon apparel competitor images as a group. "
                "Extract category-level visual standards and recurring patterns only. "
                "Do not copy any competitor image, model, brand, exact layout, text, or scene. "
                f"Project category: {project.get('category', '')}\n\n"
                f"Per-image OUTPUT-C summaries:\n"
                f"{json.dumps(condensed, ensure_ascii=False)}\n\n"
                + output_to_ai_instruction("output_d", fields)
            ),
        }
    ]
    for asset in assets[:MAX_OUTPUT_D_IMAGES]:
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(Path(asset["file_path"]))}})
    return content


def insert_analysis_run(
    conn,
    project_id: str,
    output_type: str,
    mode: str,
    asset_ids: list[str],
    model_names: list[str],
    schema_snapshot_id: str,
    input_payload: dict[str, Any],
) -> dict:
    run_id = new_id()
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO analysis_runs
        (id, project_id, output_type, mode, asset_ids_json, model_names_json, schema_snapshot_id, input_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, project_id, output_type, mode, to_json(asset_ids), to_json(model_names), schema_snapshot_id, to_json(input_payload), "running", ts, ts),
    )
    return fetch_one(conn, "SELECT * FROM analysis_runs WHERE id = ?", (run_id,))


def insert_analysis_result(
    conn,
    run_id: str,
    project_id: str,
    output_type: str,
    model_name: str,
    status: str,
    raw_response: Any,
    parsed: Any,
    error: str,
    duration_ms: int,
) -> dict:
    result_id = new_id()
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO analysis_results
        (id, analysis_run_id, project_id, output_type, model_name, status, raw_response_json, parsed_json, error, duration_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (result_id, run_id, project_id, output_type, model_name, status, to_json(raw_response), to_json(parsed), error, duration_ms, ts),
    )
    return fetch_one(conn, "SELECT * FROM analysis_results WHERE id = ?", (result_id,))


def confirmed_outputs_by_ids(conn, project_id: str, output_type: str, ids: list[str], allow_draft: bool = False) -> list[dict]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    status_sql = "" if allow_draft else "AND status = 'confirmed'"
    rows = conn.execute(
        f"""
        SELECT * FROM structured_outputs
        WHERE id IN ({placeholders}) AND project_id = ? AND output_type = ? {status_sql}
        """,
        (*ids, project_id, output_type),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


VALID_DYNAMIC_FIELD_TYPES = {"text", "textarea", "number", "boolean", "list", "single_select", "multi_select"}


def normalize_dynamic_document(document: dict[str, Any], document_type: str) -> dict[str, Any]:
    groups = document.get("groups") if isinstance(document, dict) else []
    normalized_groups = []
    if not isinstance(groups, list):
        groups = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        fields = group.get("fields") or []
        normalized_fields = []
        if not isinstance(fields, list):
            fields = []
        for field_index, field in enumerate(fields):
            if not isinstance(field, dict):
                continue
            field_type = str(field.get("type") or "text")
            if field_type not in VALID_DYNAMIC_FIELD_TYPES:
                field_type = "textarea" if isinstance(field.get("value"), (dict, list)) else "text"
            key = str(field.get("key") or f"field_{field_index + 1}").strip().replace(" ", "_")
            normalized_fields.append(
                {
                    "key": key,
                    "label": str(field.get("label") or key),
                    "type": field_type,
                    "value": field.get("value", ""),
                    "reason": str(field.get("reason") or field.get("notes") or ""),
                }
            )
        key = str(group.get("key") or f"group_{group_index + 1}").strip().replace(" ", "_")
        normalized_groups.append(
            {
                "key": key,
                "label": str(group.get("label") or key),
                "fields": normalized_fields,
            }
        )
    return {
        "document_type": document_type,
        "summary": str(document.get("summary") or ""),
        "groups": normalized_groups,
    }


def dynamic_document_instruction(document_type: str) -> str:
    if document_type == "competitor_image":
        return (
            "Return JSON only. Analyze this single Amazon apparel competitor image. "
            "You must decide the useful fields yourself based on what is visible and relevant for generating Amazon-style product images. "
            "Do not use a predefined schema. Do not copy brand, exact model identity, exact layout, or copyrighted text. "
            "Return 4-7 groups and 8-18 total fields. "
            "IMPORTANT: All \"label\", \"value\", \"reason\", and \"summary\" text MUST be written in Chinese (简体中文). Only \"key\" and \"type\" remain in English. "
            "JSON shape: {\"document_type\":\"competitor_image\",\"summary\":\"...\",\"groups\":[{\"key\":\"composition\",\"label\":\"构图与画面结构\",\"fields\":[{\"key\":\"background_type\",\"label\":\"背景类型\",\"type\":\"text|textarea|number|boolean|list|single_select|multi_select\",\"value\":\"...\",\"reason\":\"为什么重要\"}]}]}."
        )
    return (
        "Return JSON only. Summarize category-level Amazon apparel visual standards from the uploaded competitor images and per-image JSON documents. "
        "You must decide the useful fields yourself. Focus on reusable visual rules, listing image structure, risks, and opportunities. "
        "Do not copy any exact competitor image, brand, model identity, scene, or text. "
        "Return 5-8 groups and 10-24 total fields. "
        "IMPORTANT: All \"label\", \"value\", \"reason\", and \"summary\" text MUST be written in Chinese (简体中文). Only \"key\" and \"type\" remain in English. "
        "JSON shape: {\"document_type\":\"category_standard\",\"summary\":\"...\",\"groups\":[{\"key\":\"main_image_rules\",\"label\":\"主图规范\",\"fields\":[{\"key\":\"white_background\",\"label\":\"白底要求\",\"type\":\"list\",\"value\":[\"...\"],\"reason\":\"为什么重要\"}]}]}."
    )


def build_dynamic_single_content(asset: dict, project: dict) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": (
                dynamic_document_instruction("competitor_image")
                + f"\n\nProject category: {project.get('category', '')}\n"
                + f"Image metadata: {json.dumps({k: asset.get(k, '') for k in ['original_name', 'asin', 'keyword', 'slot', 'source_url', 'notes']}, ensure_ascii=False)}"
            ),
        },
        {"type": "image_url", "image_url": {"url": image_to_data_url(Path(asset["file_path"]))}},
    ]


def build_dynamic_category_content(project: dict, assets: list[dict], competitor_documents: list[dict]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                dynamic_document_instruction("category_standard")
                + f"\n\nProject category: {project.get('category', '')}\n"
                + "Per-image JSON documents:\n"
                + json.dumps([doc.get("document", {}) for doc in competitor_documents], ensure_ascii=False)
            ),
        }
    ]
    for asset in assets[:MAX_OUTPUT_D_IMAGES]:
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(Path(asset["file_path"]))}})
    return content


def insert_analysis_document(
    conn,
    project_id: str,
    document_type: str,
    document: dict[str, Any],
    status: str,
    model_name: str = "",
    source_type: str = "ai_generated",
    asset_id: str | None = None,
    source_document_ids: list[str] | None = None,
    notes: str = "",
) -> dict:
    doc_id = new_id()
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO analysis_documents
        (id, project_id, document_type, asset_id, source_document_ids_json, model_name, source_type, document_json, status, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id,
            project_id,
            document_type,
            asset_id,
            to_json(source_document_ids or []),
            model_name,
            source_type,
            to_json(document),
            status,
            notes,
            ts,
            ts,
        ),
    )
    return fetch_one(conn, "SELECT * FROM analysis_documents WHERE id = ?", (doc_id,))


def field_values_for_prompt(document: dict[str, Any]) -> list[str]:
    lines = []
    doc = document.get("document", document)
    for group in doc.get("groups", []) if isinstance(doc, dict) else []:
        group_label = group.get("label") or group.get("key")
        lines.append(f"[{group_label}]")
        for field in group.get("fields", []):
            value = field.get("value", "")
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            lines.append(f"- {field.get('label') or field.get('key')}: {value}")
    return lines


def analysis_package(project: dict, documents: list[dict]) -> dict[str, Any]:
    competitor_docs = [doc for doc in documents if doc["document_type"] == "competitor_image"]
    category_docs = [doc for doc in documents if doc["document_type"] == "category_standard"]
    latest_category = category_docs[0] if category_docs else None
    return {
        "schema_version": "dynamic_competitor_analysis.v1",
        "project": {"sku": project.get("sku", ""), "category": project.get("category", ""), "name": project.get("name", "")},
        "analysis_model": {
            "provider_model": latest_category.get("model_name", "") if latest_category else (competitor_docs[0].get("model_name", "") if competitor_docs else ""),
            "created_at": now_iso(),
        },
        "competitor_documents": competitor_docs,
        "category_standard": latest_category,
    }


def compose_prompt_from_documents(
    project: dict,
    competitor_document: dict | None,
    category_document: dict | None,
    supplemental_info: str,
) -> str:
    competitor_lines = field_values_for_prompt(competitor_document or {}) if competitor_document else []
    category_lines = field_values_for_prompt(category_document or {}) if category_document else []
    return (
        "Create one professional Amazon apparel listing image.\n\n"
        "Use the JSON analysis only as abstract visual guidance. Do not copy any competitor image, brand, model identity, exact layout, text, or scene.\n\n"
        f"PROJECT:\n{json.dumps({'sku': project['sku'], 'category': project['category'], 'name': project['name']}, ensure_ascii=False)}\n\n"
        f"COMPETITOR IMAGE JSON GUIDANCE:\n{chr(10).join(competitor_lines) if competitor_lines else 'None'}\n\n"
        f"CATEGORY STANDARD JSON GUIDANCE:\n{chr(10).join(category_lines) if category_lines else 'None'}\n\n"
        f"DESIGNER SUPPLEMENTAL INFO:\n{supplemental_info or 'None'}\n\n"
        "Keep the image Amazon-ready, clean, realistic, and commercially usable. If the JSON suggests a main image, use pure white background, no text, no props, and high product occupancy. If the JSON suggests a secondary image, use realistic catalog or lifestyle photography with restrained or no text."
    )


def create_prompt_run(
    conn,
    project_id: str,
    title: str,
    prompt: str,
    supplemental_info: str,
    product_asset_ids: list[str],
    model_asset_ids: list[str],
    competitor_asset_ids: list[str],
    document_ids: list[str],
) -> dict:
    run_id = new_id()
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO generation_runs
        (id, project_id, title, image_goal, supplemental_info, product_output_id, category_output_id,
         competitor_output_ids_json, product_asset_ids_json, model_asset_ids_json, competitor_asset_ids_json,
         schema_snapshot_ids_json, prompt, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            project_id,
            title,
            "dynamic_json_document",
            supplemental_info,
            "",
            "",
            to_json(document_ids),
            to_json(product_asset_ids),
            to_json(model_asset_ids),
            to_json(competitor_asset_ids),
            to_json({"analysis_document_ids": document_ids}),
            prompt,
            "prompt_ready",
            ts,
            ts,
        ),
    )
    return fetch_one(conn, "SELECT * FROM generation_runs WHERE id = ?", (run_id,))


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "time": now_iso()}


@app.get("/api/models/analysis")
def list_analysis_models() -> list[dict[str, Any]]:
    return available_analysis_models()


@app.get("/api/models/image")
def list_image_models() -> list[dict[str, Any]]:
    return available_image_models()


@app.get("/api/docx-workflow/styles")
def list_docx_workflow_styles() -> list[dict[str, str]]:
    return style_options_payload()


@app.post("/api/docx-workflow/runs")
def create_docx_workflow_run(payload: DocxWorkflowRunIn) -> dict:
    with get_db() as conn:
        validate_docx_workflow_input(conn, payload)
        run_id = new_id()
        ts = now_iso()
        conn.execute(
            """
            INSERT INTO docx_workflow_runs
            (id, project_id, product_name, material, style_key, product_asset_id, model_asset_id,
             fit_asset_id, scene_asset_id, image_model, size, quality, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                payload.scene_asset_id,
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


@app.post("/api/docx-workflow/runs/{run_id}/preview")
def preview_docx_workflow_run(run_id: str) -> dict:
    with get_db() as conn:
        return fetch_docx_run_package(conn, run_id)


@app.get("/api/docx-workflow/runs/{run_id}")
def get_docx_workflow_run(run_id: str) -> dict:
    with get_db() as conn:
        return fetch_docx_run_package(conn, run_id)


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
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_{run_id[:8]}_images.zip"'},
    )


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
        input_paths: list[Path] = []
        for ref in refs:
            if ref["type"] == "asset":
                input_paths.append(Path(asset_by_id[ref["id"]]["file_path"]))
            else:
                source_step = step_by_stage.get(ref["id"])
                source_path = Path(source_step.get("image_path") or "") if source_step else Path("")
                if not source_step or not source_path.is_file():
                    raise HTTPException(400, f"缺少前置步骤结果，请先生成：{ref['id']}")
                input_paths.append(source_path)
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
            "reference_refs": refs,
            "reference_asset_ids": [ref["id"] for ref in refs if ref["type"] == "asset"],
            "reference_stage_ids": [ref["id"] for ref in refs if ref["type"] == "step"],
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
                            "reference_refs": refs,
                            "reference_asset_ids": [ref["id"] for ref in refs if ref["type"] == "asset"],
                            "reference_stage_ids": [ref["id"] for ref in refs if ref["type"] == "step"],
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


@app.post("/api/docx-workflow/runs/{run_id}/generate")
def generate_docx_workflow_run(run_id: str, payload: DocxWorkflowGenerateIn | None = None) -> dict:
    payload = payload or DocxWorkflowGenerateIn()
    with get_db() as conn:
        run = fetch_one(conn, "SELECT * FROM docx_workflow_runs WHERE id = ?", (run_id,))
        steps = fetch_docx_steps(conn, run_id)
        if len(steps) != 9:
            raise HTTPException(400, "流程步骤不完整，请重新创建流程")
        asset_ids = []
        for step in steps:
            for ref in normalized_docx_refs(step):
                if ref["type"] == "asset":
                    asset_ids.append(ref["id"])
        assets = get_assets_by_ids(conn, list(dict.fromkeys(asset_ids)))
        asset_by_id = {asset["id"]: asset for asset in assets}
        missing_assets = [asset_id for asset_id in dict.fromkeys(asset_ids) if asset_id not in asset_by_id]
        if missing_assets:
            raise HTTPException(400, "流程参考图缺失或已删除")
        missing_files = missing_asset_file_names(assets)
        if missing_files:
            raise HTTPException(400, "参考图文件不存在，请重新上传：" + "、".join(missing_files))
        conn.execute(
            "UPDATE docx_workflow_runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            ("running", "", now_iso(), run_id),
        )
        conn.execute(
            """
            UPDATE docx_workflow_steps
            SET status = ?, error = ?, image_path = '', params_json = ?, updated_at = ?
            WHERE run_id = ?
            """,
            ("pending", "", to_json({}), now_iso(), run_id),
        )

    size = payload.size or run.get("size") or "1024x1024"
    quality = payload.quality or run.get("quality") or "high"
    image_model = payload.image_model or run.get("image_model") or None
    stage_output_paths: dict[str, Path] = {}
    errors: list[str] = []

    def run_step(step: dict) -> tuple[bool, str, str, Path | None]:
        input_paths: list[Path] = []
        refs = normalized_docx_refs(step)
        for ref in refs:
            if ref["type"] == "asset":
                input_paths.append(Path(asset_by_id[ref["id"]]["file_path"]))
            else:
                stage_path = stage_output_paths.get(ref["id"])
                if not stage_path:
                    missing_dependency = f"缺少前置步骤结果: {ref['id']}"
                    with get_db() as conn:
                        conn.execute(
                            "UPDATE docx_workflow_steps SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                            ("failed", missing_dependency, now_iso(), step["id"]),
                        )
                    return False, step["stage_id"], missing_dependency, None
                input_paths.append(stage_path)

        image_response: dict[str, Any] = {}
        try:
            image_response = call_image_model(step["prompt"], input_paths, size=size, quality=quality, model=image_model)
            out_dir = UPLOAD_DIR / run["project_id"] / "docx_workflow" / run_id
            out_dir.mkdir(parents=True, exist_ok=True)
            image_path = out_dir / f"{step['generation_order']:02d}_{step['stage_id']}_{new_id()}.png"
            image_path.write_bytes(base64.b64decode(image_response["b64_json"]))
            params = {
                "size": size,
                "quality": quality,
                "image_model": image_response.get("model") or image_model or "",
                "image_api_type": image_response.get("api_type") or "",
                "reference_refs": refs,
                "reference_asset_ids": [ref["id"] for ref in refs if ref["type"] == "asset"],
                "reference_stage_ids": [ref["id"] for ref in refs if ref["type"] == "step"],
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
                                "reference_refs": refs,
                                "reference_asset_ids": [ref["id"] for ref in refs if ref["type"] == "asset"],
                                "reference_stage_ids": [ref["id"] for ref in refs if ref["type"] == "step"],
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
        return fetch_docx_run_package(conn, run_id)


@app.get("/api/projects")
def list_projects(
    sku: str = Query("", description="SKU fuzzy search"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    with get_db() as conn:
        if sku.strip():
            rows = conn.execute(
                """
                SELECT * FROM projects
                WHERE sku LIKE ?
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (f"%{sku.strip()}%", limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [row_to_dict(row) for row in rows]


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
            "INSERT INTO projects (id, sku, category, name, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, sku, payload.category.strip(), name, payload.notes, ts, ts),
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
        outputs = conn.execute(
            "SELECT * FROM structured_outputs WHERE project_id = ? ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
        runs = conn.execute(
            "SELECT * FROM generation_runs WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        documents = conn.execute(
            "SELECT * FROM analysis_documents WHERE project_id = ? ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
        docx_runs = conn.execute(
            "SELECT * FROM docx_workflow_runs WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        project["assets"] = [hydrate_asset(row_to_dict(row)) for row in assets]
        project["outputs"] = [row_to_dict(row) for row in outputs]
        project["runs"] = [row_to_dict(row) for row in runs]
        project["analysis_documents"] = [row_to_dict(row) for row in documents]
        project["docx_workflow_runs"] = [row_to_dict(row) for row in docx_runs]
        return project


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


@app.get("/api/schemas/{output_type}")
def get_schema(output_type: str) -> dict:
    with get_db() as conn:
        schema = fetch_one(conn, "SELECT * FROM schema_definitions WHERE output_type = ?", (output_type,))
        return schema


@app.post("/api/schemas/{output_type}")
def save_schema(output_type: str, payload: SchemaIn) -> dict:
    validate_fields(payload.fields)
    with get_db() as conn:
        current = fetch_one(conn, "SELECT * FROM schema_definitions WHERE output_type = ?", (output_type,))
        conn.execute(
            """
            UPDATE schema_definitions
            SET name = ?, fields_json = ?, version = ?, updated_at = ?
            WHERE output_type = ?
            """,
            (payload.name, to_json(payload.fields), int(current["version"]) + 1, now_iso(), output_type),
        )
        return fetch_one(conn, "SELECT * FROM schema_definitions WHERE output_type = ?", (output_type,))


@app.post("/api/outputs/product-facts")
def save_product_facts(payload: ProductFactsIn) -> dict:
    with get_db() as conn:
        return create_structured_output(conn, payload.project_id, "output_a", payload.values, "confirmed", payload.notes)


@app.get("/api/projects/{project_id}/outputs")
def list_outputs(project_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM structured_outputs WHERE project_id = ? ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.patch("/api/outputs/{output_id}")
def update_output(output_id: str, payload: OutputUpdateIn) -> dict:
    with get_db() as conn:
        conn.execute(
            "UPDATE structured_outputs SET values_json = ?, status = ?, notes = ?, updated_at = ? WHERE id = ?",
            (to_json(payload.values), payload.status, payload.notes, now_iso(), output_id),
        )
        return fetch_one(conn, "SELECT * FROM structured_outputs WHERE id = ?", (output_id,))


@app.get("/api/projects/{project_id}/analysis-documents")
def list_analysis_documents(project_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM analysis_documents WHERE project_id = ? ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.patch("/api/analysis-documents/{document_id}")
def update_analysis_document(document_id: str, payload: AnalysisDocumentUpdateIn) -> dict:
    with get_db() as conn:
        existing = fetch_one(conn, "SELECT * FROM analysis_documents WHERE id = ?", (document_id,))
        document = normalize_dynamic_document(payload.document, existing["document_type"])
        conn.execute(
            """
            UPDATE analysis_documents
            SET document_json = ?, status = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (to_json(document), payload.status, payload.notes, now_iso(), document_id),
        )
        return fetch_one(conn, "SELECT * FROM analysis_documents WHERE id = ?", (document_id,))


@app.post("/api/analysis-documents/import")
def import_analysis_documents(payload: AnalysisDocumentImportIn) -> dict:
    with get_db() as conn:
        fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (payload.project_id,))
        package = payload.package or {}
        imported = []
        for item in package.get("competitor_documents") or []:
            doc = normalize_dynamic_document(item.get("document") or item, "competitor_image")
            imported.append(
                insert_analysis_document(
                    conn,
                    payload.project_id,
                    "competitor_image",
                    doc,
                    payload.status,
                    model_name=(item.get("model_name") or package.get("analysis_model", {}).get("provider_model", "")),
                    source_type="imported",
                    asset_id=item.get("asset_id") or None,
                    notes="Imported JSON package",
                )
            )
        category_item = package.get("category_standard")
        if category_item:
            doc = normalize_dynamic_document(category_item.get("document") or category_item, "category_standard")
            imported.append(
                insert_analysis_document(
                    conn,
                    payload.project_id,
                    "category_standard",
                    doc,
                    payload.status,
                    model_name=(category_item.get("model_name") or package.get("analysis_model", {}).get("provider_model", "")),
                    source_type="imported",
                    source_document_ids=[item["id"] for item in imported if item["document_type"] == "competitor_image"],
                    notes="Imported JSON package",
                )
            )
        return {"documents": imported}


@app.get("/api/projects/{project_id}/analysis-package/export")
def export_analysis_package(project_id: str) -> dict:
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        rows = conn.execute(
            """
            SELECT * FROM analysis_documents
            WHERE project_id = ?
            ORDER BY CASE status WHEN 'confirmed' THEN 0 ELSE 1 END, updated_at DESC
            """,
            (project_id,),
        ).fetchall()
        docs = [row_to_dict(row) for row in rows]
        return analysis_package(project, docs)


def _analyze_dynamic_asset(asset: dict, project: dict, model_name: str | None) -> dict:
    started = time.perf_counter()
    try:
        raw = call_text_model([{"role": "user", "content": build_dynamic_single_content(asset, project)}], temperature=0.2, model=model_name, max_tokens=4096)
        document = normalize_dynamic_document(parse_json_object(raw), "competitor_image")
        return {"asset": asset, "raw": raw, "document": document, "status": "success", "error": "", "ms": int((time.perf_counter() - started) * 1000)}
    except Exception as exc:
        return {"asset": asset, "raw": "", "document": normalize_dynamic_document({}, "competitor_image"), "status": "failed", "error": str(exc), "ms": int((time.perf_counter() - started) * 1000)}


@app.post("/api/dynamic-analysis/preview")
def dynamic_analysis_preview(payload: DynamicAnalysisPreviewIn) -> dict:
    if not payload.asset_ids:
        raise HTTPException(400, "至少选择一张竞品图")
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (payload.project_id,))
        assets = get_assets_by_ids(conn, payload.asset_ids)
        if len(assets) != len(payload.asset_ids) or any(asset["project_id"] != payload.project_id or asset["asset_type"] != "competitor" for asset in assets):
            raise HTTPException(400, "只能选择当前项目的竞品图")

    with ThreadPoolExecutor(max_workers=min(len(assets), 6)) as pool:
        futures = [pool.submit(_analyze_dynamic_asset, asset, project, payload.model_name) for asset in assets]
        ai_results = [future.result() for future in as_completed(futures)]

    competitor_docs = []
    with get_db() as conn:
        for result in ai_results:
            if result["status"] != "success":
                continue
            source = {
                "asset_id": result["asset"]["id"],
                "original_name": result["asset"].get("original_name", ""),
                "asin": result["asset"].get("asin", ""),
                "keyword": result["asset"].get("keyword", ""),
                "slot": result["asset"].get("slot", ""),
                "source_url": result["asset"].get("source_url", ""),
            }
            result["document"]["source"] = source
            competitor_docs.append(
                insert_analysis_document(
                    conn,
                    payload.project_id,
                    "competitor_image",
                    result["document"],
                    "draft",
                    model_name=payload.model_name or "default",
                    source_type="ai_generated",
                    asset_id=result["asset"]["id"],
                    notes=f"AI dynamic analysis in {result['ms']}ms",
                )
            )
    if not competitor_docs:
        errors = [result["error"] for result in ai_results if result["error"]]
        raise HTTPException(502, "所有竞品图动态分析都失败：" + "；".join(errors[:3]))

    content = build_dynamic_category_content(project, assets, competitor_docs)
    try:
        raw_category = call_text_model([{"role": "user", "content": content}], temperature=0.2, model=payload.model_name, max_tokens=4096)
        category_document = normalize_dynamic_document(parse_json_object(raw_category), "category_standard")
    except Exception as exc:
        raise HTTPException(502, f"总品类视觉规范分析失败: {exc}") from exc
    with get_db() as conn:
        category_doc = insert_analysis_document(
            conn,
            payload.project_id,
            "category_standard",
            category_document,
            "draft",
            model_name=payload.model_name or "default",
            source_type="ai_generated",
            source_document_ids=[doc["id"] for doc in competitor_docs],
            notes="AI dynamic category standard",
        )
        prompt_previews = [
            {
                "document_id": doc["id"],
                "asset_id": doc.get("asset_id", ""),
                "prompt": compose_prompt_from_documents(project, doc, category_doc, payload.supplemental_info),
            }
            for doc in competitor_docs
        ]
        return {
            "competitor_documents": competitor_docs,
            "category_document": category_doc,
            "prompt_previews": prompt_previews,
            "model_name": payload.model_name or "default",
        }


@app.post("/api/workflows/generate-from-documents")
def generate_from_documents(payload: GenerateFromDocumentsIn) -> dict:
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (payload.project_id,))
        docs_rows = conn.execute(
            "SELECT * FROM analysis_documents WHERE project_id = ? ORDER BY updated_at DESC",
            (payload.project_id,),
        ).fetchall()
        all_docs = [row_to_dict(row) for row in docs_rows]
        if payload.competitor_document_ids:
            competitor_docs = [doc for doc in all_docs if doc["id"] in payload.competitor_document_ids and doc["document_type"] == "competitor_image"]
        else:
            competitor_docs = [doc for doc in all_docs if doc["document_type"] == "competitor_image" and doc["status"] == "confirmed"]
        if payload.category_document_id:
            category_doc = next((doc for doc in all_docs if doc["id"] == payload.category_document_id and doc["document_type"] == "category_standard"), None)
        else:
            category_doc = next((doc for doc in all_docs if doc["document_type"] == "category_standard" and doc["status"] == "confirmed"), None)
        if not category_doc:
            category_doc = next((doc for doc in all_docs if doc["document_type"] == "category_standard"), None)
        if not competitor_docs and not category_doc:
            raise HTTPException(400, "缺少可用于生图的动态 JSON 文档")
        selected_ids = [doc["id"] for doc in competitor_docs] + ([category_doc["id"]] if category_doc else [])
        for doc_id in selected_ids:
            conn.execute("UPDATE analysis_documents SET status = 'confirmed', updated_at = ? WHERE id = ?", (now_iso(), doc_id))
        runs = []
        source_docs = competitor_docs or [None]
        for index, competitor_doc in enumerate(source_docs, start=1):
            prompt = compose_prompt_from_documents(project, competitor_doc, category_doc, payload.supplemental_info)
            document_ids = ([competitor_doc["id"]] if competitor_doc else []) + ([category_doc["id"]] if category_doc else [])
            runs.append(
                create_prompt_run(
                    conn,
                    payload.project_id,
                    f"动态 JSON 生图 {index}",
                    prompt,
                    payload.supplemental_info,
                    payload.product_asset_ids,
                    payload.model_asset_ids,
                    payload.competitor_asset_ids,
                    document_ids,
                )
            )

    def _generate(run_id: str):
        return generate_image(run_id, GenerateIn(size=payload.size, quality=payload.quality, image_model=payload.image_model))

    with ThreadPoolExecutor(max_workers=min(len(runs), 6)) as pool:
        futures = [pool.submit(_generate, run["id"]) for run in runs]
        results = [future.result() for future in as_completed(futures)]
    return {"runs": runs, "results": results}


@app.post("/api/analysis/competitor-image")
def analyze_competitor_image(payload: CompetitorAnalysisIn) -> dict:
    with get_db() as conn:
        asset = fetch_one(conn, "SELECT * FROM assets WHERE id = ? AND project_id = ?", (payload.asset_id, payload.project_id))
        if asset["asset_type"] != "competitor":
            raise HTTPException(400, "只能分析竞品图")
        schema, snapshot = get_schema_with_snapshot(conn, "output_c")
        run = insert_analysis_run(
            conn,
            payload.project_id,
            "output_c",
            "single_image",
            [payload.asset_id],
            [payload.model_name or ""],
            snapshot["id"],
            {"asset_id": payload.asset_id},
        )

    content = build_single_competitor_content(asset, schema["fields"])
    started = time.perf_counter()
    try:
        raw = call_text_model([{"role": "user", "content": content}], temperature=0.15, model=payload.model_name)
        values = parse_json_object(raw)
        status = "success"
        error = ""
    except Exception as exc:
        raw = ""
        values = {}
        status = "failed"
        error = str(exc)

    with get_db() as conn:
        result = insert_analysis_result(
            conn,
            run["id"],
            payload.project_id,
            "output_c",
            payload.model_name or "default",
            status,
            raw,
            {"asset_id": payload.asset_id, "values": values},
            error,
            int((time.perf_counter() - started) * 1000),
        )
        conn.execute("UPDATE analysis_runs SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), run["id"]))
        if error:
            raise HTTPException(502, f"竞品图分析失败: {error}")
        output = create_structured_output(
            conn,
            payload.project_id,
            "output_c",
            values,
            "draft",
            f"AI generated by {payload.model_name or 'default'}; waiting for designer confirmation.",
            asset_id=payload.asset_id,
            schema_snapshot_id=snapshot["id"],
        )
        result["structured_output"] = output
        return result


@app.post("/api/analysis/competitor-batch")
def analyze_competitor_batch(payload: CompetitorBatchIn) -> dict:
    if not payload.asset_ids:
        raise HTTPException(400, "至少选择一张竞品图")
    with get_db() as conn:
        for asset_id in payload.asset_ids:
            row = conn.execute("SELECT * FROM assets WHERE id = ? AND project_id = ?", (asset_id, payload.project_id)).fetchone()
            if not row:
                raise HTTPException(404, f"竞品图不存在: {asset_id}")
            if row["asset_type"] != "competitor":
                raise HTTPException(400, f"不是竞品图: {asset_id}")

    def _run_one(asset_id: str):
        return analyze_competitor_image(CompetitorAnalysisIn(project_id=payload.project_id, asset_id=asset_id, model_name=payload.model_name))

    with ThreadPoolExecutor(max_workers=min(len(payload.asset_ids), 6)) as pool:
        futures = {pool.submit(_run_one, aid): aid for aid in payload.asset_ids}
        results = [f.result() for f in as_completed(futures)]
    return {"results": results}


@app.post("/api/analysis/category-standard")
def analyze_category_standard(payload: CategoryStandardIn) -> dict:
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (payload.project_id,))
        if not payload.competitor_output_ids:
            raise HTTPException(400, "至少选择一条已确认 OUTPUT-C")
        placeholders = ",".join("?" for _ in payload.competitor_output_ids)
        rows = conn.execute(
            f"""
            SELECT * FROM structured_outputs
            WHERE id IN ({placeholders}) AND project_id = ? AND output_type = 'output_c' AND status = 'confirmed'
            """,
            (*payload.competitor_output_ids, payload.project_id),
        ).fetchall()
        outputs = [row_to_dict(row) for row in rows]
        if len(outputs) != len(payload.competitor_output_ids):
            raise HTTPException(400, "存在未确认或不存在的 OUTPUT-C")
        schema = fetch_one(conn, "SELECT * FROM schema_definitions WHERE output_type = 'output_d'")

    messages = [
        {
            "role": "user",
            "content": (
                "You are summarizing category-level visual rules from confirmed per-image competitor analyses. "
                "Extract abstract Amazon apparel visual standards only. Do not copy any competitor image. "
                f"Project category: {project['category']}\n\n"
                f"Confirmed OUTPUT-C analyses:\n{json.dumps([o['values'] for o in outputs], ensure_ascii=False)}\n\n"
                + output_to_ai_instruction("output_d", schema["fields"])
            ),
        }
    ]
    try:
        values = parse_json_object(call_text_model(messages, temperature=0.2))
    except Exception as exc:
        raise HTTPException(502, f"类目视觉规范分析失败: {exc}") from exc

    with get_db() as conn:
        return create_structured_output(
            conn,
            payload.project_id,
            "output_d",
            values,
            "draft",
            "AI generated from confirmed OUTPUT-C; waiting for designer confirmation.",
        )


@app.post("/api/analysis/category-standard-from-images")
def analyze_category_standard_from_images(payload: CategoryStandardFromImagesIn) -> dict:
    if not payload.asset_ids:
        raise HTTPException(400, "至少选择一张竞品图")
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (payload.project_id,))
        assets = get_assets_by_ids(conn, payload.asset_ids)
        if len(assets) != len(payload.asset_ids) or any(asset["asset_type"] != "competitor" for asset in assets):
            raise HTTPException(400, "只能选择本项目的竞品图")
        competitor_outputs = confirmed_outputs_by_ids(conn, payload.project_id, "output_c", payload.competitor_output_ids, allow_draft=True)
        schema, snapshot = get_schema_with_snapshot(conn, "output_d")
        run = insert_analysis_run(
            conn,
            payload.project_id,
            "output_d",
            "multi_image_direct",
            payload.asset_ids,
            [payload.model_name or ""],
            snapshot["id"],
            {"asset_ids": payload.asset_ids, "competitor_output_ids": payload.competitor_output_ids},
        )
    content = build_category_from_images_content(project, assets, schema["fields"], competitor_outputs)
    started = time.perf_counter()
    try:
        raw = call_text_model([{"role": "user", "content": content}], temperature=0.2, model=payload.model_name)
        values = parse_json_object(raw)
        status = "success"
        error = ""
    except Exception as exc:
        raw = ""
        values = {}
        status = "failed"
        error = str(exc)
    with get_db() as conn:
        result = insert_analysis_result(
            conn,
            run["id"],
            payload.project_id,
            "output_d",
            payload.model_name or "default",
            status,
            raw,
            values,
            error,
            int((time.perf_counter() - started) * 1000),
        )
        conn.execute("UPDATE analysis_runs SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), run["id"]))
        if error:
            raise HTTPException(502, f"类目视觉规范分析失败: {error}")
        output = create_structured_output(
            conn,
            payload.project_id,
            "output_d",
            values,
            "draft",
            f"AI generated directly from competitor images by {payload.model_name or 'default'}; waiting for designer confirmation.",
            schema_snapshot_id=snapshot["id"],
        )
        result["structured_output"] = output
        return result


@app.post("/api/analysis/compare-models")
def compare_models(payload: CompareModelsIn) -> dict:
    if payload.output_type not in {"output_c", "output_d"}:
        raise HTTPException(400, "output_type 必须是 output_c 或 output_d")
    if not payload.model_names:
        raise HTTPException(400, "至少选择一个模型")
    if payload.output_type == "output_c" and not payload.asset_ids:
        raise HTTPException(400, "生成 OUTPUT-C 至少选择一张竞品图")
    if payload.output_type == "output_d" and not payload.asset_ids and not payload.competitor_output_ids:
        raise HTTPException(400, "生成 OUTPUT-D 至少选择竞品图或 OUTPUT-C")
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (payload.project_id,))
        schema, snapshot = get_schema_with_snapshot(conn, payload.output_type)
        assets = get_assets_by_ids(conn, payload.asset_ids)
        competitor_outputs = confirmed_outputs_by_ids(conn, payload.project_id, "output_c", payload.competitor_output_ids, allow_draft=True)
        run = insert_analysis_run(
            conn,
            payload.project_id,
            payload.output_type,
            "model_compare",
            payload.asset_ids,
            payload.model_names,
            snapshot["id"],
            {"asset_ids": payload.asset_ids, "competitor_output_ids": payload.competitor_output_ids},
        )
    results = []
    for model_name in payload.model_names:
        started = time.perf_counter()
        try:
            if payload.output_type == "output_d":
                content = build_category_from_images_content(project, assets, schema["fields"], competitor_outputs)
                raw = call_text_model([{"role": "user", "content": content}], temperature=0.2, model=model_name)
                parsed = parse_json_object(raw)
            else:
                items = []
                raw_parts = []
                for asset in assets:
                    raw = call_text_model([{"role": "user", "content": build_single_competitor_content(asset, schema["fields"])}], temperature=0.15, model=model_name)
                    raw_parts.append({"asset_id": asset["id"], "raw": raw})
                    items.append({"asset_id": asset["id"], "values": parse_json_object(raw)})
                raw = raw_parts
                parsed = {"items": items}
            status = "success"
            error = ""
        except Exception as exc:
            raw = ""
            parsed = {}
            status = "failed"
            error = str(exc)
        with get_db() as conn:
            results.append(
                insert_analysis_result(
                    conn,
                    run["id"],
                    payload.project_id,
                    payload.output_type,
                    model_name,
                    status,
                    raw,
                    parsed,
                    error,
                    int((time.perf_counter() - started) * 1000),
                )
            )
    with get_db() as conn:
        final_status = "success" if any(result["status"] == "success" for result in results) else "failed"
        conn.execute("UPDATE analysis_runs SET status = ?, updated_at = ? WHERE id = ?", (final_status, now_iso(), run["id"]))
    return {"run": run, "results": results}


@app.get("/api/projects/{project_id}/analysis-results")
def list_analysis_results(project_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM analysis_results WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.post("/api/analysis-results/{result_id}/confirm")
def confirm_analysis_result(result_id: str, payload: ConfirmAnalysisResultIn) -> dict:
    with get_db() as conn:
        result = fetch_one(conn, "SELECT * FROM analysis_results WHERE id = ?", (result_id,))
        run = fetch_one(conn, "SELECT * FROM analysis_runs WHERE id = ?", (result["analysis_run_id"],))
        if result["status"] != "success":
            raise HTTPException(400, "只能确认成功的分析结果")
        parsed = result["parsed"]
        created_outputs = []
        if result["output_type"] == "output_d":
            created_outputs.append(
                create_structured_output(
                    conn,
                    result["project_id"],
                    "output_d",
                    parsed,
                    payload.status,
                    f"Confirmed from model comparison: {result['model_name']}. {payload.review_notes}",
                    schema_snapshot_id=run["schema_snapshot_id"],
                )
            )
        else:
            items = parsed.get("items") if isinstance(parsed, dict) else None
            if not items and isinstance(parsed, dict) and parsed.get("values"):
                items = [parsed]
            if not items:
                raise HTTPException(400, "OUTPUT-C 分析结果缺少 items")
            for item in items:
                created_outputs.append(
                    create_structured_output(
                        conn,
                        result["project_id"],
                        "output_c",
                        item.get("values", {}),
                        payload.status,
                        f"Confirmed from model comparison: {result['model_name']}. {payload.review_notes}",
                        asset_id=item.get("asset_id"),
                        schema_snapshot_id=run["schema_snapshot_id"],
                    )
                )
        conn.execute(
            """
            UPDATE analysis_results
            SET rating = ?, review_notes = ?, result_output_ids_json = ?
            WHERE id = ?
            """,
            (payload.rating, payload.review_notes, to_json([item["id"] for item in created_outputs]), result_id),
        )
        updated = fetch_one(conn, "SELECT * FROM analysis_results WHERE id = ?", (result_id,))
        updated["created_outputs"] = created_outputs
        return updated


def compose_prompt(
    project: dict,
    product_output: dict | None,
    competitor_output: dict,
    category_output: dict,
    supplemental_info: str,
) -> str:
    c_vals = competitor_output.get("values", {})
    image_role = c_vals.get("image_role", "")
    goal_hint = "main image" if image_role == "主图" else "secondary listing image"
    return (
        f"Create one professional Amazon apparel listing {goal_hint} using Image2.\n\n"
        "Do not copy any competitor image, model, brand, layout, text, or scene. Use competitor information only as abstract category guidance.\n\n"
        f"PROJECT:\n{json.dumps({'sku': project['sku'], 'category': project['category'], 'name': project['name']}, ensure_ascii=False)}\n\n"
        f"IMAGE ROLE: {image_role}\n\n"
        f"OPTIONAL OUTPUT-A PRODUCT FACTS:\n{json.dumps(product_output['values'] if product_output else {}, ensure_ascii=False, indent=2)}\n\n"
        f"OUTPUT-C COMPETITOR STRUCTURE ANALYSIS (this image's reference):\n{json.dumps(c_vals, ensure_ascii=False, indent=2)}\n\n"
        f"OUTPUT-D CATEGORY VISUAL STANDARD:\n{json.dumps(category_output['values'], ensure_ascii=False, indent=2)}\n\n"
        f"DESIGNER SUPPLEMENTAL INFO:\n{supplemental_info or 'None'}\n\n"
        "This is a competitor-visual-style experiment. Prioritize Amazon category style, image structure, composition, lighting, background, model crop, pose, and listing realism. "
        "If product/model reference images are selected, use them only as optional references; otherwise create a generic apparel item suitable for the image role. "
        "Keep the image Amazon-ready, clean, realistic, and commercially usable. "
        "If the role is a main image, enforce pure white background, no text, no props, and high product occupancy. "
        "If the role is a secondary image, use realistic lifestyle/catalog photography with restrained or no text."
    )


def compose_workflow_prompt_preview(
    project: dict,
    competitor_outputs: list[dict],
    category_output: dict,
    supplemental_info: str,
) -> list[dict[str, Any]]:
    return [
        {
            "output_c_id": o["id"],
            "image_role": o.get("values", {}).get("image_role", ""),
            "prompt": compose_prompt(project, None, o, category_output, supplemental_info),
        }
        for o in competitor_outputs
    ]


def _analyze_single_asset(asset: dict, fields: list[dict], model_name: str | None) -> dict:
    started = time.perf_counter()
    try:
        raw = call_text_model([{"role": "user", "content": build_single_competitor_content(asset, fields)}], temperature=0.15, model=model_name)
        values = parse_json_object(raw)
        return {"asset": asset, "raw": raw, "values": values, "status": "success", "error": "", "ms": int((time.perf_counter() - started) * 1000)}
    except Exception as exc:
        return {"asset": asset, "raw": "", "values": {}, "status": "failed", "error": str(exc), "ms": int((time.perf_counter() - started) * 1000)}


@app.post("/api/workflows/analysis-preview")
def create_analysis_preview(payload: WorkflowPreviewIn) -> dict:
    if not payload.asset_ids:
        raise HTTPException(400, "至少选择一张竞品图")
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (payload.project_id,))
        assets = get_assets_by_ids(conn, payload.asset_ids)
        if len(assets) != len(payload.asset_ids) or any(asset["project_id"] != payload.project_id or asset["asset_type"] != "competitor" for asset in assets):
            raise HTTPException(400, "只能选择当前项目的竞品图")
        schema_c, snapshot_c = get_schema_with_snapshot(conn, "output_c")
        schema_d, snapshot_d = get_schema_with_snapshot(conn, "output_d")
        run_c = insert_analysis_run(
            conn,
            payload.project_id,
            "output_c",
            "one_click_preview",
            payload.asset_ids,
            [payload.model_name or ""],
            snapshot_c["id"],
            {"asset_ids": payload.asset_ids},
        )

    with ThreadPoolExecutor(max_workers=min(len(assets), 6)) as pool:
        futures = {pool.submit(_analyze_single_asset, asset, schema_c["fields"], payload.model_name): asset for asset in assets}
        ai_results = [f.result() for f in as_completed(futures)]

    output_c_items = []
    analysis_c_results = []
    with get_db() as conn:
        for r in ai_results:
            analysis_result = insert_analysis_result(
                conn,
                run_c["id"],
                payload.project_id,
                "output_c",
                payload.model_name or "default",
                r["status"],
                r["raw"],
                {"asset_id": r["asset"]["id"], "values": r["values"]},
                r["error"],
                r["ms"],
            )
            analysis_c_results.append(analysis_result)
            if r["status"] == "success":
                output = create_structured_output(
                    conn,
                    payload.project_id,
                    "output_c",
                    r["values"],
                    "draft",
                    f"One-click preview generated by {payload.model_name or 'default'}; waiting for designer confirmation.",
                    asset_id=r["asset"]["id"],
                    schema_snapshot_id=snapshot_c["id"],
                )
                output_c_items.append(output)
        c_status = "success" if output_c_items else "failed"
        conn.execute("UPDATE analysis_runs SET status = ?, updated_at = ? WHERE id = ?", (c_status, now_iso(), run_c["id"]))
    if not output_c_items:
        errors = [r["error"] for r in ai_results if r["error"]]
        raise HTTPException(502, "所有竞品图 OUTPUT-C 分析都失败：" + "；".join(errors[:3]))

    with get_db() as conn:
        run_d = insert_analysis_run(
            conn,
            payload.project_id,
            "output_d",
            "one_click_preview",
            payload.asset_ids,
            [payload.model_name or ""],
            snapshot_d["id"],
            {"asset_ids": payload.asset_ids, "competitor_output_ids": [item["id"] for item in output_c_items]},
        )
    content = build_category_from_images_content(project, assets, schema_d["fields"], output_c_items)
    started = time.perf_counter()
    try:
        raw_d = call_text_model([{"role": "user", "content": content}], temperature=0.2, model=payload.model_name)
        values_d = parse_json_object(raw_d)
        status_d = "success"
        error_d = ""
    except Exception as exc:
        raw_d = ""
        values_d = {}
        status_d = "failed"
        error_d = str(exc)
    with get_db() as conn:
        analysis_d = insert_analysis_result(
            conn,
            run_d["id"],
            payload.project_id,
            "output_d",
            payload.model_name or "default",
            status_d,
            raw_d,
            values_d,
            error_d,
            int((time.perf_counter() - started) * 1000),
        )
        conn.execute("UPDATE analysis_runs SET status = ?, updated_at = ? WHERE id = ?", (status_d, now_iso(), run_d["id"]))
        if error_d:
            raise HTTPException(502, f"OUTPUT-D 分析失败: {error_d}")
        output_d = create_structured_output(
            conn,
            payload.project_id,
            "output_d",
            values_d,
            "draft",
            f"One-click preview generated directly from competitor images by {payload.model_name or 'default'}; waiting for designer confirmation.",
            schema_snapshot_id=snapshot_d["id"],
        )

    prompt_previews = compose_workflow_prompt_preview(project, output_c_items, output_d, payload.supplemental_info)
    return {
        "output_c": output_c_items,
        "output_d": output_d,
        "analysis_results": {"output_c": analysis_c_results, "output_d": analysis_d},
        "prompt_previews": prompt_previews,
        "model_name": payload.model_name or "default",
    }


@app.post("/api/workflows/generate-all")
def generate_all_images(payload: WorkflowGenerateAllIn) -> dict:
    if not payload.output_c_ids:
        raise HTTPException(400, "缺少待确认的 OUTPUT-C")
    if not payload.output_d_id:
        raise HTTPException(400, "缺少待确认的 OUTPUT-D")
    with get_db() as conn:
        for output_id in [*payload.output_c_ids, payload.output_d_id]:
            conn.execute(
                "UPDATE structured_outputs SET status = 'confirmed', updated_at = ? WHERE id = ? AND project_id = ?",
                (now_iso(), output_id, payload.project_id),
            )
    runs = []
    for index, c_id in enumerate(payload.output_c_ids, start=1):
        run = create_generation_run(
            GenerationRunIn(
                project_id=payload.project_id,
                title=f"一键整套生图 {index}",
                image_goal="",
                supplemental_info=payload.supplemental_info,
                product_asset_ids=payload.product_asset_ids,
                model_asset_ids=payload.model_asset_ids,
                competitor_asset_ids=payload.competitor_asset_ids,
                competitor_output_ids=[c_id],
                category_output_id=payload.output_d_id,
            )
        )
        runs.append(run)

    def _gen(run_id: str):
        return generate_image(run_id, GenerateIn(size=payload.size, quality=payload.quality, image_model=payload.image_model))

    with ThreadPoolExecutor(max_workers=min(len(runs), 6)) as pool:
        futures = {pool.submit(_gen, r["id"]): r for r in runs}
        results = [f.result() for f in as_completed(futures)]
    return {"runs": runs, "results": results}


@app.post("/api/generation-runs")
def create_generation_run(payload: GenerationRunIn) -> dict:
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (payload.project_id,))
        try:
            product_output = latest_confirmed_output(conn, payload.project_id, "output_a")
        except HTTPException:
            product_output = None
        if payload.category_output_id:
            category_output = fetch_one(conn, "SELECT * FROM structured_outputs WHERE id = ? AND project_id = ? AND output_type = 'output_d'", (payload.category_output_id, payload.project_id))
        else:
            category_output = latest_confirmed_output(conn, payload.project_id, "output_d")
        if payload.competitor_output_ids:
            placeholders = ",".join("?" for _ in payload.competitor_output_ids)
            rows = conn.execute(
                f"""
                SELECT * FROM structured_outputs
                WHERE id IN ({placeholders}) AND project_id = ? AND output_type = 'output_c' AND status = 'confirmed'
                """,
                (*payload.competitor_output_ids, payload.project_id),
            ).fetchall()
            competitor_outputs = [row_to_dict(row) for row in rows]
            if len(competitor_outputs) != len(payload.competitor_output_ids):
                raise HTTPException(400, "存在未确认或不存在的 OUTPUT-C")
        else:
            competitor_outputs = []
        competitor_output = competitor_outputs[0] if competitor_outputs else {"values": {}}
        prompt = compose_prompt(project, product_output, competitor_output, category_output, payload.supplemental_info)
        run_id = new_id()
        snapshot_ids = {
            "output_a": product_output["schema_snapshot_id"] if product_output else "",
            "output_c": [o["schema_snapshot_id"] for o in competitor_outputs],
            "output_d": category_output["schema_snapshot_id"],
        }
        ts = now_iso()
        conn.execute(
            """
            INSERT INTO generation_runs
            (id, project_id, title, image_goal, supplemental_info, product_output_id, category_output_id,
             competitor_output_ids_json, product_asset_ids_json, model_asset_ids_json, competitor_asset_ids_json,
             schema_snapshot_ids_json, prompt, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                payload.project_id,
                payload.title,
                payload.image_goal,
                payload.supplemental_info,
                product_output["id"] if product_output else "",
                category_output["id"],
                to_json(payload.competitor_output_ids),
                to_json(payload.product_asset_ids),
                to_json(payload.model_asset_ids),
                to_json(payload.competitor_asset_ids),
                to_json(snapshot_ids),
                prompt,
                "prompt_ready",
                ts,
                ts,
            ),
        )
        return fetch_one(conn, "SELECT * FROM generation_runs WHERE id = ?", (run_id,))


@app.get("/api/projects/{project_id}/generation-runs")
def list_generation_runs(project_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM generation_runs WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.post("/api/generation-runs/{run_id}/generate")
def generate_image(run_id: str, payload: GenerateIn) -> dict:
    with get_db() as conn:
        run = fetch_one(conn, "SELECT * FROM generation_runs WHERE id = ?", (run_id,))
        assets = get_assets_by_ids(conn, run["product_asset_ids"] + run["model_asset_ids"])
    image_paths = [Path(asset["file_path"]) for asset in assets]
    image_response: dict[str, Any] = {}
    try:
        image_response = call_image_model(run["prompt"], image_paths, size=payload.size, quality=payload.quality, model=payload.image_model)
        b64 = image_response["b64_json"]
        out_dir = UPLOAD_DIR / run["project_id"] / "generations"
        out_dir.mkdir(parents=True, exist_ok=True)
        image_path = out_dir / f"{new_id()}.png"
        image_path.write_bytes(base64.b64decode(b64))
        status = "generated"
        result_status = "success"
        error = ""
    except Exception as exc:
        image_path = ""
        status = "failed"
        result_status = "failed"
        error = str(exc)

    with get_db() as conn:
        ts = now_iso()
        result_id = new_id()
        conn.execute(
            """
            INSERT INTO generation_results
            (id, run_id, image_path, prompt, params_json, status, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_id,
                run_id,
                str(image_path),
                run["prompt"],
                to_json(
                    {
                        "size": payload.size,
                        "quality": payload.quality,
                        "image_model": image_response.get("model") or payload.image_model or "",
                        "image_api_type": image_response.get("api_type") or "",
                        "reference_asset_ids": run["product_asset_ids"] + run["model_asset_ids"],
                        **(image_response.get("params") or {}),
                    }
                ),
                result_status,
                error,
                ts,
            ),
        )
        conn.execute(
            "UPDATE generation_runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error, ts, run_id),
        )
        result = fetch_one(conn, "SELECT * FROM generation_results WHERE id = ?", (result_id,))
        return hydrate_result(result)


@app.get("/api/generation-runs/{run_id}/results")
def list_generation_results(run_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM generation_results WHERE run_id = ? ORDER BY created_at DESC",
            (run_id,),
        ).fetchall()
        results = [row_to_dict(row) for row in rows]
        return [hydrate_result(result) for result in results]


@app.post("/api/generation-results/{result_id}/review")
def review_generation_result(result_id: str, payload: ReviewIn) -> dict:
    with get_db() as conn:
        result = fetch_one(conn, "SELECT * FROM generation_results WHERE id = ?", (result_id,))
        run = fetch_one(conn, "SELECT * FROM generation_runs WHERE id = ?", (result["run_id"],))
        conn.execute(
            """
            UPDATE generation_results
            SET rating = ?, review_notes = ?, is_knowledge_candidate = ?
            WHERE id = ?
            """,
            (payload.rating, payload.review_notes, 1 if payload.is_knowledge_candidate else 0, result_id),
        )
        if payload.is_knowledge_candidate:
            existing = conn.execute(
                "SELECT id FROM knowledge_candidates WHERE generation_result_id = ?",
                (result_id,),
            ).fetchone()
            if not existing:
                document_ids = (run.get("schema_snapshot_ids") or {}).get("analysis_document_ids", []) if isinstance(run.get("schema_snapshot_ids"), dict) else []
                documents = []
                if document_ids:
                    placeholders = ",".join("?" for _ in document_ids)
                    rows = conn.execute(f"SELECT * FROM analysis_documents WHERE id IN ({placeholders})", tuple(document_ids)).fetchall()
                    documents = [row_to_dict(row) for row in rows]
                payload_json = {
                    "run": run,
                    "result": row_to_dict(result),
                    "analysis_documents": documents,
                    "review": {"rating": payload.rating, "notes": payload.review_notes},
                }
                conn.execute(
                    """
                    INSERT INTO knowledge_candidates
                    (id, project_id, generation_result_id, payload_json, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (new_id(), run["project_id"], result_id, to_json(payload_json), "candidate", now_iso()),
                )
        updated = fetch_one(conn, "SELECT * FROM generation_results WHERE id = ?", (result_id,))
        return hydrate_result(updated)


@app.get("/api/knowledge-candidates")
def list_knowledge_candidates() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM knowledge_candidates ORDER BY created_at DESC").fetchall()
        return [row_to_dict(row) for row in rows]
