from __future__ import annotations

import base64
import io
import json
import re
import shutil
import sys
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
from pydantic import BaseModel

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
        docx_runs = conn.execute(
            "SELECT * FROM docx_workflow_runs WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        project["assets"] = [hydrate_asset(row_to_dict(row)) for row in assets]
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
