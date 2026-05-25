# RAG Knowledge Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a RAG knowledge-base workbench before the existing DOCX nine-image workflow so users can search, select, tag, and apply knowledge-base images to each project.

**Architecture:** Keep `D:\RAG` as an independent service and call it from the main image backend through `/api/rag/*` proxy endpoints. Store project-level RAG selections in the main SQLite database, enrich DOCX prompts and input references at run creation time, and expose the workbench in the React UI served from `/workbench/`.

**Tech Stack:** FastAPI, SQLite, Python `requests`, React 19, Vite, lucide-react, pytest/httpx for backend tests.

---

## Execution Notes

- Work in `C:\Users\ASUS\Desktop\主图生成`.
- Do not revert or overwrite existing user changes, especially the already-modified `DOCX_WORKFLOW.md`.
- Existing deployed app is `http://192.168.0.186:8021/workbench/`.
- Existing RAG service is expected at `http://127.0.0.1:8010`.
- Use PowerShell commands shown here.
- If a dependency install needs network access, request permission instead of finding a workaround.
- Keep commits small. Each task below ends with a commit command.

## File Structure

- Modify `requirements.txt`: add test/runtime dependencies used by this plan.
- Create `tests/test_rag_integration.py`: pure unit tests for RAG response compaction, summary generation, stage selection, and DOCX enrichment.
- Create `backend/app/rag_integration.py`: RAG client/proxy helpers, metadata compaction, summary building, reference selection, prompt enrichment, and RAG image cache download.
- Modify `backend/app/db.py`: create `rag_reference_selections` and `docx_knowledge_candidates`.
- Modify `backend/app/main.py`: add request models, RAG proxy endpoints, reference CRUD endpoints, candidate endpoint, DOCX `rag` reference support, and workflow enrichment.
- Modify `frontend/src/App.jsx`: change API default to same-origin, add `RagKnowledgeWorkbench`, integrate it before `DocxWorkflowPanel`, and add candidate marking.
- Modify `frontend/src/styles.css`: add workbench layout, cards, tags, and reference pool styles.
- Update generated static files in `backend/app/static/` after Vite build.

---

### Task 1: Add Backend Test Scaffolding

**Files:**
- Modify: `requirements.txt`
- Create: `tests/test_rag_integration.py`

- [ ] **Step 1: Add test dependencies**

Open `requirements.txt` and append these lines:

```text
pytest>=8.0.0
httpx>=0.27.0
```

- [ ] **Step 2: Create the failing helper tests**

Create `tests/test_rag_integration.py` with this exact content:

```python
from backend.app.rag_integration import (
    build_rag_summary,
    compact_rag_record,
    enrich_docx_steps_with_rag,
    select_stage_references,
)


def make_reference(ref_id, tags, score=0.5, sort_order=0, scene="欧洲风格城市街道"):
    return {
        "id": ref_id,
        "rag_image_id": f"rag-{ref_id}",
        "filename": f"{ref_id}.jpg",
        "category": "女装 / 背心",
        "scene": scene,
        "image_type": "竖幅中景构图",
        "caption": "balanced clean product image",
        "score": score,
        "usage_tags": tags,
        "metadata": {
            "visual_style": "高级质感的欧美都市街拍风",
            "color_tone": "低饱和暖调大地色系",
            "scene_description": scene,
            "composition": "竖幅中景构图",
            "season": "春夏",
            "lighting": "明亮柔和侧方自然光",
        },
        "sort_order": sort_order,
    }


def test_compact_rag_record_removes_large_and_private_fields():
    raw = {
        "image_id": "abc",
        "filename": "abc.jpg",
        "embedding_vector": [1, 2, 3],
        "embedding_text": "large text",
        "storage_key": "D:/RAG/data/images/abc.jpg",
        "metadata": {"scene_description": "街道"},
    }

    compact = compact_rag_record(raw)

    assert compact["image_id"] == "abc"
    assert compact["filename"] == "abc.jpg"
    assert "embedding_vector" not in compact
    assert "embedding_text" not in compact
    assert "storage_key" not in compact
    assert compact["metadata"]["scene_description"] == "街道"


def test_build_rag_summary_prefers_metadata_fields():
    summary = build_rag_summary(make_reference("one", ["scene_reference"]))

    assert "欧洲风格城市街道" in summary
    assert "高级质感的欧美都市街拍风" in summary
    assert "低饱和暖调大地色系" in summary
    assert "明亮柔和侧方自然光" in summary


def test_select_stage_references_filters_by_stage_tags_and_limits_to_three():
    refs = [
        make_reference("a", ["scene_reference"], score=0.1, sort_order=2),
        make_reference("b", ["pose_reference"], score=0.9, sort_order=0),
        make_reference("c", ["color_reference"], score=0.8, sort_order=0),
        make_reference("d", ["scene_reference"], score=0.7, sort_order=1),
        make_reference("e", ["scene_reference"], score=0.6, sort_order=3),
    ]

    selected = select_stage_references("scene_model", refs)

    assert [item["id"] for item in selected] == ["c", "d", "a"]
    assert len(selected) == 3


def test_enrich_docx_steps_adds_prompt_summary_and_rag_refs():
    steps = [
        {
            "stage_id": "scene_model",
            "title": "第二步：场景模特图",
            "prompt": "原始提示词",
            "input_refs": [{"type": "step", "id": "model_on_body"}],
            "input_asset_ids": [],
            "input_step_ids": ["model_on_body"],
        }
    ]
    refs = [make_reference("ref1", ["scene_reference"], score=0.9)]

    enriched = enrich_docx_steps_with_rag(steps, refs)

    assert enriched[0]["prompt"].startswith("原始提示词")
    assert "知识库参考摘要" in enriched[0]["prompt"]
    assert "欧洲风格城市街道" in enriched[0]["prompt"]
    assert enriched[0]["input_refs"][-1] == {"type": "rag", "id": "ref1"}
```

- [ ] **Step 3: Run the tests and confirm they fail because the module does not exist**

Run:

```powershell
python -m pytest tests/test_rag_integration.py -q
```

Expected result:

```text
ModuleNotFoundError: No module named 'backend.app.rag_integration'
```

- [ ] **Step 4: Commit the failing tests**

Run:

```powershell
git add requirements.txt tests/test_rag_integration.py
git commit -m "test: define rag workbench helper behavior"
```

---

### Task 2: Implement RAG Integration Helpers

**Files:**
- Create: `backend/app/rag_integration.py`
- Test: `tests/test_rag_integration.py`

- [ ] **Step 1: Create `backend/app/rag_integration.py`**

Create the file with this exact content:

```python
from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException


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
```

- [ ] **Step 2: Run the helper tests**

Run:

```powershell
python -m pytest tests/test_rag_integration.py -q
```

Expected result:

```text
4 passed
```

- [ ] **Step 3: Commit helper implementation**

Run:

```powershell
git add backend/app/rag_integration.py tests/test_rag_integration.py
git commit -m "feat: add rag integration helpers"
```

---

### Task 3: Add Database Tables

**Files:**
- Modify: `backend/app/db.py`

- [ ] **Step 1: Add the two `CREATE TABLE` statements**

In `backend/app/db.py`, inside the large `conn.executescript("""...""")` block in `init_db()`, add these tables after `docx_workflow_steps`:

```sql
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
```

- [ ] **Step 2: Teach `row_to_dict()` to parse new JSON fields**

In `row_to_dict()`, extend the tuple of JSON column names with:

```python
        "usage_tags_json",
        "metadata_json",
        "suggested_metadata_json",
```

Then change the default calculation to this:

```python
            default = [] if key.endswith("ids_json") or key in {"input_refs_json", "usage_tags_json"} else {}
```

- [ ] **Step 3: Add migration guards for existing databases**

In `migrate_existing_db(conn)`, append:

```python
    rag_columns = table_columns(conn, "rag_reference_selections")
    if rag_columns and "sort_order" not in rag_columns:
        conn.execute("ALTER TABLE rag_reference_selections ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
```

- [ ] **Step 4: Verify the schema can initialize**

Run:

```powershell
python -c "from backend.app.db import init_db, get_db; init_db(); conn=get_db(); print(bool(conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='rag_reference_selections'\").fetchone())); print(bool(conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='docx_knowledge_candidates'\").fetchone()))"
```

Expected result:

```text
True
True
```

- [ ] **Step 5: Commit database schema**

Run:

```powershell
git add backend/app/db.py
git commit -m "feat: add rag workbench database tables"
```

---

### Task 4: Add RAG Proxy and Reference Pool API

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add imports**

In `backend/app/main.py`, extend the FastAPI responses import:

```python
from fastapi.responses import Response
```

It already exists. Keep it as-is.

Change the Pydantic import from:

```python
from pydantic import BaseModel
```

to:

```python
from pydantic import BaseModel, Field
```

Add this import below the existing local imports:

```python
from .rag_integration import (
    RAG_USAGE_TAGS,
    compact_rag_record,
    rag_health,
    rag_image_response,
    rag_search,
)
```

- [ ] **Step 2: Add Pydantic models after `DocxWorkflowStepUpdateIn`**

Insert:

```python
class RagSearchIn(BaseModel):
    query: str
    top_k: int = 8
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
    notes: str = ""


class RagReferenceUpdateIn(BaseModel):
    usage_tags: list[str] | None = None
    notes: str | None = None
    sort_order: int | None = None
```

- [ ] **Step 3: Add reference helper functions before the first route**

Insert these functions before `@app.get("/api/health")`:

```python
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
    row["usage_labels"] = [RAG_USAGE_TAGS.get(tag, tag) for tag in row.get("usage_tags") or []]
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
```

- [ ] **Step 4: Add RAG proxy routes after `/api/health`**

Insert:

```python
@app.get("/api/rag/health")
def api_rag_health() -> dict[str, Any]:
    return rag_health()


@app.post("/api/rag/search")
def api_rag_search(payload: RagSearchIn) -> dict[str, Any]:
    query = payload.query.strip()
    if not query:
        raise HTTPException(400, "检索词不能为空")
    return rag_search(
        {
            "query": query,
            "top_k": max(1, min(int(payload.top_k), 20)),
            "filters": payload.filters if isinstance(payload.filters, dict) else {},
        }
    )


@app.get("/api/rag/images/{image_id}")
def api_rag_image(image_id: str) -> Response:
    content, content_type = rag_image_response(image_id)
    return Response(content=content, media_type=content_type)
```

- [ ] **Step 5: Add reference pool routes near project routes**

Insert these routes before `@app.delete("/api/projects/{project_id}")`:

```python
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
                    usage_tags_json = ?, metadata_json = ?, notes = ?
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
                 usage_tags_json, metadata_json, sort_order, selected_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    if payload.sort_order is not None:
        assignments.append("sort_order = ?")
        values.append(int(payload.sort_order))
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
```

- [ ] **Step 6: Verify proxy and reference routes**

Start the main backend if it is not running:

```powershell
$env:PORT='8021'; python .\run_backend.py
```

In another shell, run:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8021/api/rag/health' | ConvertTo-Json -Depth 4
```

Expected result contains:

```text
"status": "ok"
```

- [ ] **Step 7: Commit API routes**

Run:

```powershell
git add backend/app/main.py
git commit -m "feat: add rag proxy and reference pool api"
```

---

### Task 5: Apply RAG References to DOCX Workflow

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Extend imports**

Update the `.rag_integration` import in `backend/app/main.py` to include:

```python
    download_rag_reference_to_cache,
    enrich_docx_steps_with_rag,
```

- [ ] **Step 2: Let DOCX refs accept `rag`**

In `normalized_docx_refs()`, change:

```python
            if ref_type in {"asset", "step"} and ref_id:
```

to:

```python
            if ref_type in {"asset", "step", "rag"} and ref_id:
```

Add this helper after `split_docx_refs()`:

```python
def rag_ref_ids(refs: list[dict[str, str]]) -> list[str]:
    return [ref["id"] for ref in refs if ref.get("type") == "rag"]
```

- [ ] **Step 3: Show RAG references in run details**

In `attach_docx_reference_items()`, collect RAG ids and fetch references:

```python
    rag_ids: list[str] = []
    for step in steps:
        for ref in normalized_docx_refs(step):
            if ref["type"] == "asset":
                asset_ids.append(ref["id"])
            elif ref["type"] == "rag":
                rag_ids.append(ref["id"])
```

After `step_by_stage = ...`, add:

```python
    rag_references = get_rag_references_by_ids(conn, run["project_id"], list(dict.fromkeys(rag_ids)))
    rag_by_id = {item["id"]: item for item in rag_references}
```

Inside the per-ref loop, keep existing `asset` and `step` branches, then add this `rag` branch:

```python
            elif ref["type"] == "rag":
                rag_ref = rag_by_id.get(ref["id"])
                items.append(
                    {
                        "type": "rag",
                        "id": ref["id"],
                        "order": index,
                        "label": rag_ref.get("filename") if rag_ref else "知识库参考图已删除",
                        "rag_image_id": rag_ref.get("rag_image_id") if rag_ref else "",
                        "usage_tags": rag_ref.get("usage_tags") if rag_ref else [],
                        "usage_labels": rag_ref.get("usage_labels") if rag_ref else [],
                        "url": rag_ref.get("image_url") if rag_ref else "",
                        "missing": not rag_ref,
                    }
                )
```

- [ ] **Step 4: Enrich steps when creating a run**

In `insert_docx_workflow_steps()`, immediately after `steps = build_workflow_steps(...)`, add:

```python
    rag_references = get_rag_references_for_project(conn, payload.project_id)
    steps = enrich_docx_steps_with_rag(steps, rag_references)
```

- [ ] **Step 5: Permit `rag` refs in step update validation**

In `update_docx_workflow_step()`, change:

```python
                if ref_type not in {"asset", "step"} or not ref_id:
```

to:

```python
                if ref_type not in {"asset", "step", "rag"} or not ref_id:
```

After the existing `if step_ids:` validation block, add:

```python
            selected_rag_ids = rag_ref_ids(refs)
            if selected_rag_ids:
                run = fetch_one(conn, "SELECT * FROM docx_workflow_runs WHERE id = ?", (step["run_id"],))
                rag_refs = get_rag_references_by_ids(conn, run["project_id"], list(dict.fromkeys(selected_rag_ids)))
                found_rag_refs = {item["id"] for item in rag_refs}
                missing_rag_refs = [ref_id for ref_id in selected_rag_ids if ref_id not in found_rag_refs]
                if missing_rag_refs:
                    raise HTTPException(400, "知识库参考图不存在或不属于当前项目")
```

- [ ] **Step 6: Resolve `rag` refs during single-step generation**

In `regenerate_docx_workflow_step()`, inside the `for ref in refs:` loop that builds `input_paths`, change the final `else` branch into explicit `elif` branches:

```python
            elif ref["type"] == "step":
                source_step = step_by_stage.get(ref["id"])
                source_path = Path(source_step.get("image_path") or "") if source_step else Path("")
                if not source_step or not source_path.is_file():
                    raise HTTPException(400, f"缺少前置步骤结果，请先生成：{ref['id']}")
                input_paths.append(source_path)
            elif ref["type"] == "rag":
                rag_ref = fetch_rag_reference(conn, run["project_id"], ref["id"])
                input_paths.append(download_rag_reference_to_cache(run["project_id"], rag_ref, UPLOAD_DIR))
```

- [ ] **Step 7: Resolve `rag` refs during full-run generation**

In `generate_docx_workflow_run()`, inside inner `run_step(step)`, change the ref loop the same way:

```python
            elif ref["type"] == "step":
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
            elif ref["type"] == "rag":
                with get_db() as conn:
                    rag_ref = fetch_rag_reference(conn, run["project_id"], ref["id"])
                input_paths.append(download_rag_reference_to_cache(run["project_id"], rag_ref, UPLOAD_DIR))
```

- [ ] **Step 8: Persist RAG reference ids in params**

Where `params` is created after successful image generation in both single-step and full-run paths, add:

```python
            "reference_rag_ids": [ref["id"] for ref in refs if ref["type"] == "rag"],
```

Also add the same key in the failure `params_json` blocks.

- [ ] **Step 9: Run helper tests and a syntax check**

Run:

```powershell
python -m pytest tests/test_rag_integration.py -q
python -m compileall backend/app
```

Expected result:

```text
4 passed
```

`compileall` should finish without `SyntaxError`.

- [ ] **Step 10: Commit DOCX RAG integration**

Run:

```powershell
git add backend/app/main.py
git commit -m "feat: apply rag references to docx workflow"
```

---

### Task 6: Add Knowledge Candidate Endpoint

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add candidate request model**

After `RagReferenceUpdateIn`, add:

```python
class KnowledgeCandidateIn(BaseModel):
    rating: int | None = None
    review_notes: str = ""
    suggested_category: str = ""
    suggested_scene: str = ""
    suggested_image_type: str = ""
    suggested_metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 2: Add endpoint before full-run generation routes**

Add:

```python
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
```

- [ ] **Step 3: Verify syntax**

Run:

```powershell
python -m compileall backend/app
```

Expected result: no `SyntaxError`.

- [ ] **Step 4: Commit candidate endpoint**

Run:

```powershell
git add backend/app/main.py
git commit -m "feat: save docx knowledge candidates"
```

---

### Task 7: Add Frontend RAG Workbench

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Change API default to same origin**

Replace:

```javascript
const API = import.meta.env.VITE_API_BASE || "http://localhost:8000";
```

with:

```javascript
const API = import.meta.env.VITE_API_BASE || window.location.origin;
```

- [ ] **Step 2: Extend icon imports**

Add these imports from `lucide-react`:

```javascript
  Check,
  Database,
  Search,
  Star,
  X,
```

- [ ] **Step 3: Add RAG usage constants after `ASSET_TYPE_LABELS`**

Insert:

```javascript
const RAG_USAGE_TAGS = [
  ["scene_reference", "场景参考"],
  ["pose_reference", "姿势参考"],
  ["composition_reference", "构图参考"],
  ["color_reference", "色调参考"],
  ["white_main_reference", "白底主图参考"],
  ["competitor_fit_reference", "竞品上身参考"],
];

function defaultRagQuery(project) {
  return [project?.category, project?.name, project?.sku, "服装 主图 场景 构图 光影"]
    .filter(Boolean)
    .join(" ");
}
```

- [ ] **Step 4: Add `RagKnowledgeWorkbench` before `DocxWorkflowPanel`**

Insert this component after `AssetPanel`:

```jsx
function RagKnowledgeWorkbench({ project, refreshProject }) {
  const [health, setHealth] = useState(null);
  const [query, setQuery] = useState(defaultRagQuery(project));
  const [topK, setTopK] = useState(8);
  const [filterText, setFilterText] = useState("");
  const [results, setResults] = useState([]);
  const [references, setReferences] = useState([]);
  const [selectedTags, setSelectedTags] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadReferences = async () => {
    if (!project?.id) return;
    const data = await request(`/api/projects/${project.id}/rag-references`);
    setReferences(data);
  };

  useEffect(() => {
    setQuery(defaultRagQuery(project));
    setResults([]);
    setError("");
    request("/api/rag/health").then(setHealth).catch((err) => setHealth({ status: "unavailable", detail: err.message }));
    loadReferences().catch((err) => setError(err.message));
  }, [project?.id]);

  const parseFilters = () => {
    const text = filterText.trim();
    if (!text) return {};
    try {
      const parsed = JSON.parse(text);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch {
      throw new Error("过滤条件必须是 JSON 对象，例如 {\"compliance\":\"approved\"}");
    }
  };

  const search = async () => {
    if (!query.trim()) return;
    setBusy(true);
    setError("");
    try {
      const data = await request("/api/rag/search", {
        method: "POST",
        body: JSON.stringify({ query, top_k: topK, filters: parseFilters() }),
      });
      setResults(data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const addReference = async (item) => {
    const usage_tags = selectedTags[item.image_id] || ["scene_reference"];
    setBusy(true);
    setError("");
    try {
      await request(`/api/projects/${project.id}/rag-references`, {
        method: "POST",
        body: JSON.stringify({
          rag_image_id: item.image_id,
          filename: item.filename || "",
          category: item.category || "",
          scene: item.scene || "",
          image_type: item.image_type || "",
          caption: item.caption || "",
          score: item.score ?? null,
          usage_tags,
          metadata: item.metadata || {},
          notes: "从知识库工作台加入",
        }),
      });
      await loadReferences();
      await refreshProject();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const updateReferenceTags = async (reference, tag, checked) => {
    const current = new Set(reference.usage_tags || []);
    if (checked) current.add(tag);
    else current.delete(tag);
    const usage_tags = [...current];
    const updated = await request(`/api/projects/${project.id}/rag-references/${reference.id}`, {
      method: "PATCH",
      body: JSON.stringify({ usage_tags }),
    });
    setReferences((items) => items.map((item) => (item.id === updated.id ? updated : item)));
  };

  const removeReference = async (referenceId) => {
    if (!confirm("确认从本项目参考池移除这张知识库图片？")) return;
    await request(`/api/projects/${project.id}/rag-references/${referenceId}`, { method: "DELETE" });
    await loadReferences();
  };

  return (
    <section className="panel rag-workbench">
      <div className="section-title">
        <Database size={18} />
        <h2>知识库工作台</h2>
      </div>
      <div className="rag-status">
        <span className={health?.status === "ok" ? "status-ok" : "status-fail"}>
          RAG：{health?.status === "ok" ? `可用 · ${health.images || 0} 张图` : "不可用"}
        </span>
      </div>
      <div className="rag-search-grid">
        <label className="stacked-field">
          <span>检索词</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label className="stacked-field">
          <span>返回数量</span>
          <input type="number" min="1" max="20" value={topK} onChange={(event) => setTopK(Number(event.target.value) || 8)} />
        </label>
        <label className="stacked-field">
          <span>过滤 JSON</span>
          <input placeholder='{"compliance":"approved"}' value={filterText} onChange={(event) => setFilterText(event.target.value)} />
        </label>
        <button className="primary" disabled={busy || !query.trim()} onClick={search}>
          <Search size={16} />
          搜索知识库
        </button>
      </div>
      {error ? <div className="error-banner">{error}</div> : null}
      <div className="rag-results-grid">
        {results.map((item) => (
          <article key={item.image_id} className="rag-card">
            <img src={`${API}/api/rag/images/${item.image_id}`} alt={item.filename || item.image_id} />
            <div className="rag-card-body">
              <strong>{item.filename || item.image_id}</strong>
              <span>{item.category || "未分类"} · {item.scene || "未知场景"}</span>
              <small>{item.image_type || item.caption || ""}</small>
              <em>相似度：{typeof item.score === "number" ? item.score.toFixed(4) : "-"}</em>
              <select
                value={(selectedTags[item.image_id] || ["scene_reference"])[0]}
                onChange={(event) => setSelectedTags({ ...selectedTags, [item.image_id]: [event.target.value] })}
              >
                {RAG_USAGE_TAGS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <button disabled={busy} onClick={() => addReference(item)}>
                <Check size={14} />
                加入本项目
              </button>
            </div>
          </article>
        ))}
      </div>
      <div className="rag-reference-pool">
        <div className="prompt-head">
          <strong>项目参考池</strong>
          <span>{references.length} 张</span>
        </div>
        {references.length ? references.map((reference) => (
          <article key={reference.id} className="rag-reference-row">
            <img src={`${API}${reference.image_url}`} alt={reference.filename || reference.rag_image_id} />
            <div>
              <strong>{reference.filename || reference.rag_image_id}</strong>
              <small>{reference.scene || reference.caption || ""}</small>
              <div className="tag-grid">
                {RAG_USAGE_TAGS.map(([value, label]) => (
                  <label key={value}>
                    <input
                      type="checkbox"
                      checked={(reference.usage_tags || []).includes(value)}
                      onChange={(event) => updateReferenceTags(reference, value, event.target.checked)}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>
            <button className="icon-btn danger" title="移除" onClick={() => removeReference(reference.id)}>
              <X size={14} />
            </button>
          </article>
        )) : <p className="muted">还没有加入本项目的知识库参考图。</p>}
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Render the workbench before DOCX workflow**

In `App()`, inside the selected project fragment, change:

```jsx
              <AssetPanel project={selectedProject} assets={assets} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
              <DocxWorkflowPanel project={selectedProject} assets={assets} runs={docxRuns} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
```

to:

```jsx
              <AssetPanel project={selectedProject} assets={assets} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
              <RagKnowledgeWorkbench project={selectedProject} refreshProject={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
              <DocxWorkflowPanel project={selectedProject} assets={assets} runs={docxRuns} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
```

- [ ] **Step 6: Run frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected result contains:

```text
built in
```

- [ ] **Step 7: Commit frontend workbench**

Run:

```powershell
cd ..
git add frontend/src/App.jsx
git commit -m "feat: add rag knowledge workbench ui"
```

---

### Task 8: Add Candidate Marking UI and Styles

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add candidate marking function in `DocxWorkflowPanel`**

Inside `DocxWorkflowPanel`, after `regenerateStep`, add:

```javascript
  const markKnowledgeCandidate = async (step) => {
    if (!step?.id || !step.url) return;
    setBusy(true);
    try {
      await request(`/api/docx-workflow/steps/${step.id}/knowledge-candidate`, {
        method: "POST",
        body: JSON.stringify({
          rating: 5,
          review_notes: "九图流程人工标记候选",
          suggested_category: project.category || "",
          suggested_scene: "",
          suggested_image_type: step.title || "",
          suggested_metadata: {
            sku: project.sku,
            project_name: project.name,
            docx_stage_id: step.stage_id,
            image_no: step.image_no,
          },
        }),
      });
      alert("已保存为知识库候选");
    } finally {
      setBusy(false);
    }
  };
```

- [ ] **Step 2: Add candidate button to each generated step**

In each workflow step action area, after the regenerate button, add:

```jsx
                  <button onClick={() => markKnowledgeCandidate(step)} disabled={busy || !step.url}>
                    <Star size={14} />
                    标记知识库候选
                  </button>
```

- [ ] **Step 3: Add RAG styles**

Append this CSS to `frontend/src/styles.css`:

```css
.rag-workbench {
  display: grid;
  gap: 16px;
}

.rag-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #475569;
  font-size: 13px;
}

.status-ok {
  color: #047857;
  font-weight: 700;
}

.status-fail {
  color: #b91c1c;
  font-weight: 700;
}

.rag-search-grid {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 110px minmax(220px, 0.7fr) auto;
  gap: 12px;
  align-items: end;
}

.rag-results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.rag-card {
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.rag-card img {
  width: 100%;
  aspect-ratio: 4 / 5;
  object-fit: cover;
  background: #f8fafc;
}

.rag-card-body {
  display: grid;
  gap: 8px;
  padding: 10px;
}

.rag-card-body span,
.rag-card-body small,
.rag-card-body em,
.muted {
  color: #64748b;
  font-size: 12px;
}

.rag-reference-pool {
  display: grid;
  gap: 10px;
}

.rag-reference-row {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  padding: 10px;
  background: #fff;
}

.rag-reference-row img {
  width: 76px;
  height: 96px;
  object-fit: cover;
  border-radius: 6px;
  background: #f8fafc;
}

.tag-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 8px;
}

.tag-grid label {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  color: #334155;
  font-size: 12px;
}

@media (max-width: 900px) {
  .rag-search-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 4: Build frontend**

Run:

```powershell
cd frontend
npm run build
```

Expected result contains:

```text
built in
```

- [ ] **Step 5: Commit candidate UI and styles**

Run:

```powershell
cd ..
git add frontend/src/App.jsx frontend/src/styles.css
git commit -m "feat: add rag candidate ui and styles"
```

---

### Task 9: Build Static App and Verify End to End

**Files:**
- Modify generated files under: `backend/app/static/`

- [ ] **Step 1: Build React production assets**

Run:

```powershell
cd frontend
npm run build
```

Expected result contains:

```text
built in
```

- [ ] **Step 2: Copy Vite output into backend static directory**

Run:

```powershell
cd ..
Remove-Item -LiteralPath '.\backend\app\static\assets' -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath '.\frontend\dist\index.html' -Destination '.\backend\app\static\index.html' -Force
Copy-Item -LiteralPath '.\frontend\dist\assets' -Destination '.\backend\app\static\assets' -Recurse -Force
```

Expected result: no PowerShell error.

- [ ] **Step 3: Start or restart backend on port 8021**

Run:

```powershell
$env:PORT='8021'; python .\run_backend.py
```

Expected result contains:

```text
Uvicorn running
```

- [ ] **Step 4: Verify RAG service is reachable through main backend**

In another shell, run:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8021/api/rag/health' | ConvertTo-Json -Depth 4
```

Expected result contains:

```text
"status": "ok"
```

- [ ] **Step 5: Verify RAG search through main backend**

Run:

```powershell
$body = @{ query = '女装 背心 欧洲街拍 高级质感'; top_k = 3; filters = @{} } | ConvertTo-Json -Depth 4
Invoke-RestMethod -Uri 'http://127.0.0.1:8021/api/rag/search' -Method Post -ContentType 'application/json; charset=utf-8' -Body $body | ConvertTo-Json -Depth 5
```

Expected result contains:

```text
"results"
"image_id"
```

Expected result does not contain:

```text
embedding_vector
```

- [ ] **Step 6: Browser verification**

Open:

```text
http://192.168.0.186:8021/workbench/
```

Verify:

1. A selected project shows the new `知识库工作台` panel between `素材上传` and `DOCX 固定九图流程`.
2. Searching `女装 背心 欧洲街拍 高级质感` returns image cards.
3. Clicking `加入本项目` adds an image to `项目参考池`.
4. Tag checkboxes can be changed and persist after refresh.
5. Creating a DOCX preview shows `知识库参考摘要` inside matching step prompts.
6. Generated step cards show `标记知识库候选`.

- [ ] **Step 7: Final test run**

Run:

```powershell
python -m pytest tests/test_rag_integration.py -q
python -m compileall backend/app
```

Expected result:

```text
4 passed
```

`compileall` should finish without `SyntaxError`.

- [ ] **Step 8: Commit generated static assets**

Run:

```powershell
git add backend/app/static frontend/src/App.jsx frontend/src/styles.css
git commit -m "build: publish rag workbench frontend"
```

---

## Final Verification Checklist

- [ ] `python -m pytest tests/test_rag_integration.py -q` prints `4 passed`.
- [ ] `python -m compileall backend/app` finishes without `SyntaxError`.
- [ ] `GET http://127.0.0.1:8021/api/rag/health` returns RAG status.
- [ ] `POST http://127.0.0.1:8021/api/rag/search` returns compact results without vectors.
- [ ] `/workbench/` loads from `http://192.168.0.186:8021/workbench/`.
- [ ] Knowledge workbench search, add, tag, delete all work for one project.
- [ ] DOCX preview includes `知识库参考摘要` for relevant steps.
- [ ] DOCX generation still works when no RAG references exist.
- [ ] If RAG is stopped, the original asset upload and DOCX workflow still load; only the workbench shows a RAG error.

## Known Follow-Up Work Not In This Plan

- Submit saved candidates to RAG `/ingest`.
- Add `/api/rag/search-image`.
- Add automatic usage-tag recommendations.
- Add drag-and-drop ordering in the reference pool.
