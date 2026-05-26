from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4



ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "output" / "workbench"
UPLOAD_DIR = DATA_DIR / "projects"
DB_PATH = DATA_DIR / "design_workbench.db"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid4().hex


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    for key in (
        "fields_json",
        "values_json",
        "competitor_output_ids_json",
        "product_asset_ids_json",
        "model_asset_ids_json",
        "competitor_asset_ids_json",
        "schema_snapshot_ids_json",
        "params_json",
        "payload_json",
        "asset_ids_json",
        "model_names_json",
        "input_json",
        "raw_response_json",
        "parsed_json",
        "result_output_ids_json",
        "source_document_ids_json",
        "document_json",
        "input_asset_ids_json",
        "input_step_ids_json",
        "input_refs_json",
        "usage_tags_json",
        "metadata_json",
        "suggested_metadata_json",
    ):
        if key in data:
            default = [] if key.endswith("ids_json") or key in {"input_refs_json", "usage_tags_json"} else {}
            data[key.replace("_json", "")] = from_json(data.pop(key), default)
    return data


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                sku TEXT NOT NULL,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                source_url TEXT DEFAULT '',
                asin TEXT DEFAULT '',
                keyword TEXT DEFAULT '',
                slot TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                deleted_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS schema_definitions (
                id TEXT PRIMARY KEY,
                output_type TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                fields_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS schema_snapshots (
                id TEXT PRIMARY KEY,
                schema_definition_id TEXT NOT NULL,
                output_type TEXT NOT NULL,
                name TEXT NOT NULL,
                version INTEGER NOT NULL,
                fields_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(schema_definition_id) REFERENCES schema_definitions(id)
            );

            CREATE TABLE IF NOT EXISTS structured_outputs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                output_type TEXT NOT NULL,
                asset_id TEXT,
                schema_snapshot_id TEXT NOT NULL,
                values_json TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(asset_id) REFERENCES assets(id),
                FOREIGN KEY(schema_snapshot_id) REFERENCES schema_snapshots(id)
            );

            CREATE TABLE IF NOT EXISTS generation_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                image_goal TEXT NOT NULL,
                supplemental_info TEXT DEFAULT '',
                product_output_id TEXT NOT NULL,
                category_output_id TEXT NOT NULL,
                competitor_output_ids_json TEXT NOT NULL,
                product_asset_ids_json TEXT NOT NULL,
                model_asset_ids_json TEXT NOT NULL,
                competitor_asset_ids_json TEXT NOT NULL,
                schema_snapshot_ids_json TEXT NOT NULL,
                prompt TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS generation_results (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                image_path TEXT DEFAULT '',
                prompt TEXT NOT NULL,
                params_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                rating INTEGER,
                review_notes TEXT DEFAULT '',
                is_knowledge_candidate INTEGER NOT NULL DEFAULT 0,
                error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES generation_runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS knowledge_candidates (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                generation_result_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(generation_result_id) REFERENCES generation_results(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                output_type TEXT NOT NULL,
                mode TEXT NOT NULL,
                asset_ids_json TEXT NOT NULL,
                model_names_json TEXT NOT NULL,
                schema_snapshot_id TEXT NOT NULL,
                input_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(schema_snapshot_id) REFERENCES schema_snapshots(id)
            );

            CREATE TABLE IF NOT EXISTS analysis_results (
                id TEXT PRIMARY KEY,
                analysis_run_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                output_type TEXT NOT NULL,
                model_name TEXT NOT NULL,
                status TEXT NOT NULL,
                raw_response_json TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                error TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                rating INTEGER,
                review_notes TEXT DEFAULT '',
                result_output_ids_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY(analysis_run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS analysis_documents (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                document_type TEXT NOT NULL,
                asset_id TEXT,
                source_document_ids_json TEXT NOT NULL DEFAULT '[]',
                model_name TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT 'ai_generated',
                document_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(asset_id) REFERENCES assets(id)
            );

            CREATE TABLE IF NOT EXISTS docx_workflow_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                material TEXT NOT NULL,
                style_key TEXT NOT NULL,
                product_asset_id TEXT NOT NULL,
                model_asset_id TEXT NOT NULL,
                fit_asset_id TEXT NOT NULL,
                scene_asset_id TEXT NOT NULL,
                image_model TEXT DEFAULT '',
                size TEXT NOT NULL DEFAULT '1024x1024',
                quality TEXT NOT NULL DEFAULT 'high',
                status TEXT NOT NULL DEFAULT 'draft',
                error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(product_asset_id) REFERENCES assets(id),
                FOREIGN KEY(model_asset_id) REFERENCES assets(id),
                FOREIGN KEY(fit_asset_id) REFERENCES assets(id),
                FOREIGN KEY(scene_asset_id) REFERENCES assets(id)
            );

            CREATE TABLE IF NOT EXISTS docx_workflow_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                stage_id TEXT NOT NULL,
                image_no INTEGER NOT NULL,
                generation_order INTEGER NOT NULL,
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                input_asset_ids_json TEXT NOT NULL,
                input_step_ids_json TEXT NOT NULL,
                input_refs_json TEXT NOT NULL DEFAULT '[]',
                image_path TEXT DEFAULT '',
                params_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES docx_workflow_runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS rag_reference_selections (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                rag_image_id TEXT NOT NULL,
                filename TEXT DEFAULT '',
                category TEXT DEFAULT '',
                scene TEXT DEFAULT '',
                image_type TEXT DEFAULT '',
                caption TEXT DEFAULT '',
                score REAL,
                usage_tags_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                selected_at TEXT NOT NULL,
                notes TEXT DEFAULT '',
                model_description TEXT DEFAULT '',
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS docx_knowledge_candidates (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                image_path TEXT NOT NULL,
                rating INTEGER,
                review_notes TEXT DEFAULT '',
                suggested_category TEXT DEFAULT '',
                suggested_scene TEXT DEFAULT '',
                suggested_image_type TEXT DEFAULT '',
                suggested_metadata_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                ingested_rag_image_id TEXT DEFAULT '',
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(run_id) REFERENCES docx_workflow_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(step_id) REFERENCES docx_workflow_steps(id) ON DELETE CASCADE
            );
            """
        )
        migrate_existing_db(conn)


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate_existing_db(conn: sqlite3.Connection) -> None:
    step_columns = table_columns(conn, "docx_workflow_steps")
    if "input_refs_json" not in step_columns:
        conn.execute("ALTER TABLE docx_workflow_steps ADD COLUMN input_refs_json TEXT NOT NULL DEFAULT '[]'")
    rag_columns = table_columns(conn, "rag_reference_selections")
    if rag_columns and "sort_order" not in rag_columns:
        conn.execute("ALTER TABLE rag_reference_selections ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
    if rag_columns and "model_description" not in rag_columns:
        conn.execute("ALTER TABLE rag_reference_selections ADD COLUMN model_description TEXT DEFAULT ''")
