# Project Workflow Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor from "one project -> multiple workflow runs" to "one project = one product = one set of 9 images", with project overview on the selection page and no sidebar.

**Architecture:** Move workflow fields (parameters, status, download tracking) from `docx_workflow_runs` onto the `projects` table. Create `project_workflow_steps` table keyed by `project_id` instead of `run_id`. Deprecate run-based tables. Frontend removes sidebar, adds project overview with status badges and SKU search to `ProjectSelectScreen`, and simplifies `DocxWorkflowPanel` to operate directly on the project.

**Tech Stack:** FastAPI + SQLite (backend), React 19 (frontend)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/db.py` | Modify | Add workflow columns to `projects`, create `project_workflow_steps` table, migrate existing data |
| `backend/app/main.py` | Modify | Add project-based workflow endpoints, update `list_projects` to return `workflow_status`, keep old run endpoints for backward compat |
| `frontend/src/App.jsx` | Modify | Remove `ProjectPanel`, update `ProjectSelectScreen` with overview+search, simplify `DocxWorkflowPanel` to project-based, remove sidebar from workspace layout |
| `frontend/src/styles.css` | Modify | Remove sidebar styles, add project overview styles, update workspace layout |

---

### Task 1: Database Schema — Add Workflow Fields to Projects

**Files:**
- Modify: `backend/app/db.py`

- [ ] **Step 1: Add workflow columns to `projects` table in `init_db()`**

In the `CREATE TABLE IF NOT EXISTS projects` statement, add after `notes TEXT DEFAULT ''`:

```sql
product_name TEXT NOT NULL DEFAULT '',
material TEXT NOT NULL DEFAULT '',
style_key TEXT NOT NULL DEFAULT 'natural_fashion',
product_asset_id TEXT DEFAULT '',
model_asset_id TEXT DEFAULT '',
fit_asset_id TEXT DEFAULT '',
scene_asset_id TEXT DEFAULT '',
image_model TEXT NOT NULL DEFAULT '',
size TEXT NOT NULL DEFAULT '1024x1024',
quality TEXT NOT NULL DEFAULT 'high',
workflow_status TEXT NOT NULL DEFAULT 'idle',
workflow_error TEXT DEFAULT '',
downloaded_at TEXT DEFAULT '',
```

- [ ] **Step 2: Create `project_workflow_steps` table in `init_db()`**

Add after the `docx_workflow_steps` CREATE TABLE block:

```sql
CREATE TABLE IF NOT EXISTS project_workflow_steps (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    image_no INTEGER NOT NULL,
    generation_order INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL DEFAULT '',
    input_asset_ids_json TEXT NOT NULL DEFAULT '[]',
    input_step_ids_json TEXT NOT NULL DEFAULT '[]',
    input_refs_json TEXT NOT NULL DEFAULT '[]',
    image_path TEXT NOT NULL DEFAULT '',
    params_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
```

- [ ] **Step 3: Add migration for existing databases in `migrate_existing_db()`**

After the existing `downloaded_at` migration block, add:

```python
# Project-level workflow fields
project_cols = table_columns(conn, "projects")
for col, definition in [
    ("product_name", "TEXT NOT NULL DEFAULT ''"),
    ("material", "TEXT NOT NULL DEFAULT ''"),
    ("style_key", "TEXT NOT NULL DEFAULT 'natural_fashion'"),
    ("product_asset_id", "TEXT DEFAULT ''"),
    ("model_asset_id", "TEXT DEFAULT ''"),
    ("fit_asset_id", "TEXT DEFAULT ''"),
    ("scene_asset_id", "TEXT DEFAULT ''"),
    ("image_model", "TEXT NOT NULL DEFAULT ''"),
    ("size", "TEXT NOT NULL DEFAULT '1024x1024'"),
    ("quality", "TEXT NOT NULL DEFAULT 'high'"),
    ("workflow_status", "TEXT NOT NULL DEFAULT 'idle'"),
    ("workflow_error", "TEXT DEFAULT ''"),
    ("downloaded_at", "TEXT DEFAULT ''"),
]:
    if col not in project_cols:
        conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {definition}")

# Create project_workflow_steps if missing
existing_tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
if "project_workflow_steps" not in existing_tables:
    conn.execute("""CREATE TABLE project_workflow_steps (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        stage_id TEXT NOT NULL,
        image_no INTEGER NOT NULL,
        generation_order INTEGER NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        prompt TEXT NOT NULL DEFAULT '',
        input_asset_ids_json TEXT NOT NULL DEFAULT '[]',
        input_step_ids_json TEXT NOT NULL DEFAULT '[]',
        input_refs_json TEXT NOT NULL DEFAULT '[]',
        image_path TEXT NOT NULL DEFAULT '',
        params_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'pending',
        error TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    )""")
```

- [ ] **Step 4: Add `project_workflow_steps` to `row_to_dict` JSON column list**

In `row_to_dict()`, add `"input_asset_ids_json"`, `"input_step_ids_json"`, and `"input_refs_json"` for the new table's JSON columns. These are already in the existing list (they match `docx_workflow_steps`), so no change is actually needed — the same column names apply.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db.py
git commit -m "feat(db): add workflow fields to projects and project_workflow_steps table"
```

---

### Task 2: Backend — Project-Based Workflow Helper Functions

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add `fetch_project_workflow_steps()` helper**

After the existing `fetch_docx_steps()` function (~line 270), add:

```python
def fetch_project_workflow_steps(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM project_workflow_steps WHERE project_id = ? ORDER BY generation_order ASC",
        (project_id,),
    ).fetchall()
    return [hydrate_docx_step(row_to_dict(row)) for row in rows]
```

- [ ] **Step 2: Add `fetch_project_workflow_package()` helper**

After the new function above, add:

```python
def fetch_project_workflow_package(conn: sqlite3.Connection, project_id: str) -> dict:
    project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
    steps = fetch_project_workflow_steps(conn, project_id)
    # Build a pseudo-run dict for reuse with attach_docx_reference_items
    pseudo_run = {
        "id": project_id,
        "project_id": project_id,
        "product_name": project.get("product_name", ""),
        "material": project.get("material", ""),
        "style_key": project.get("style_key", ""),
        "product_asset_id": project.get("product_asset_id", ""),
        "model_asset_id": project.get("model_asset_id", ""),
        "fit_asset_id": project.get("fit_asset_id", ""),
        "scene_asset_id": project.get("scene_asset_id", ""),
    }
    steps = attach_docx_reference_items(conn, pseudo_run, steps)
    return {
        "project_id": project_id,
        "product_name": project.get("product_name", ""),
        "material": project.get("material", ""),
        "style_key": project.get("style_key", ""),
        "image_model": project.get("image_model", ""),
        "size": project.get("size", "1024x1024"),
        "quality": project.get("quality", "high"),
        "workflow_status": project.get("workflow_status", "idle"),
        "workflow_error": project.get("workflow_error", ""),
        "downloaded_at": project.get("downloaded_at", ""),
        "steps": steps,
    }
```

- [ ] **Step 3: Add `insert_project_workflow_steps()` helper**

After `insert_docx_workflow_steps()` (~line 403), add a project-based variant. It's nearly identical but inserts into `project_workflow_steps` with `project_id` instead of `run_id`:

```python
def insert_project_workflow_steps(conn: sqlite3.Connection, project_id: str, payload) -> None:
    from backend.app.docx_workflow import build_workflow_steps
    ts = now_iso()
    steps = build_workflow_steps(payload.style_key)
    for step_def in steps:
        step_id = new_id()
        refs = step_def.get("input_refs") or []
        for asset_col, ref_type in [
            ("product_asset_id", "product_image"),
            ("model_asset_id", "model_reference"),
            ("fit_asset_id", "fit_reference"),
            ("scene_asset_id", "scene_style_reference"),
        ]:
            asset_id = getattr(payload, asset_col, "") or ""
            if asset_id and not any(r.get("id") == asset_id for r in refs):
                refs.append({"type": "asset", "id": asset_id})
        conn.execute(
            """INSERT INTO project_workflow_steps
               (id, project_id, stage_id, image_no, generation_order, title, prompt,
                input_asset_ids_json, input_step_ids_json, input_refs_json,
                image_path, params_json, status, error, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '{}', 'pending', '', ?, ?)""",
            (
                step_id, project_id, step_def["stage_id"], step_def["image_no"],
                step_def["generation_order"], step_def["title"], step_def["prompt"],
                to_json(step_def.get("input_asset_ids") or []),
                to_json(step_def.get("input_step_ids") or []),
                to_json(refs),
                ts, ts,
            ),
        )
    # Enrich with RAG references
    rag_refs = conn.execute(
        "SELECT * FROM rag_reference_selections WHERE project_id = ? ORDER BY sort_order ASC, selected_at DESC",
        (project_id,),
    ).fetchall()
    if rag_refs:
        steps = fetch_project_workflow_steps(conn, project_id)
        docx_config = conn.execute("SELECT * FROM rag_docx_config LIMIT 1").fetchone() if "rag_docx_config" in table_columns(conn, "rag_docx_config") else None
        for step in steps:
            current_refs = step.get("input_refs") or []
            rag_block = build_rag_context_block_for_step(step, [row_to_dict(r) for r in rag_refs], row_to_dict(docx_config) if docx_config else {})
            rag_ref_ids_in_block = extract_rag_ref_ids_from_block(rag_block)
            for rag_id in rag_ref_ids_in_block:
                if not any(r.get("type") == "rag" and r.get("id") == rag_id for r in current_refs):
                    current_refs.append({"type": "rag", "id": rag_id})
            updated_prompt = strip_rag_context_block(step.get("prompt") or "")
            if rag_block:
                updated_prompt = updated_prompt + rag_block
            conn.execute(
                "UPDATE project_workflow_steps SET input_refs_json = ?, prompt = ?, updated_at = ? WHERE id = ?",
                (to_json(current_refs), updated_prompt, now_iso(), step["id"]),
            )
```

- [ ] **Step 4: Add `update_project_workflow_status()` helper**

This replaces `update_docx_run_status_after_step()` for project-based workflows:

```python
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
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(api): add project-based workflow helper functions"
```

---

### Task 3: Backend — Project-Based Workflow Endpoints

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add `POST /api/projects/{project_id}/workflow` — Initialize workflow**

This replaces `POST /api/docx-workflow/runs`. Validates input, stores workflow params on the project, creates 9 steps in `project_workflow_steps`:

```python
@app.post("/api/projects/{project_id}/workflow")
def init_project_workflow(project_id: str, payload: DocxWorkflowRunIn) -> dict:
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        validated = validate_docx_workflow_input(conn, payload)
        conn.execute(
            """UPDATE projects SET
               product_name = ?, material = ?, style_key = ?,
               product_asset_id = ?, model_asset_id = ?, fit_asset_id = ?, scene_asset_id = ?,
               image_model = ?, size = ?, quality = ?,
               workflow_status = 'idle', workflow_error = '', updated_at = ?
               WHERE id = ?""",
            (
                payload.product_name, payload.material, payload.style_key,
                payload.product_asset_id, payload.model_asset_id,
                payload.fit_asset_id, payload.scene_asset_id,
                payload.image_model or "", payload.size, payload.quality,
                now_iso(), project_id,
            ),
        )
        # Clear old steps
        conn.execute("DELETE FROM project_workflow_steps WHERE project_id = ?", (project_id,))
        insert_project_workflow_steps(conn, project_id, payload)
        return fetch_project_workflow_package(conn, project_id)
```

- [ ] **Step 2: Add `GET /api/projects/{project_id}/workflow` — Get workflow state**

Replaces `GET /api/docx-workflow/runs/{run_id}`:

```python
@app.get("/api/projects/{project_id}/workflow")
def get_project_workflow(project_id: str) -> dict:
    with get_db() as conn:
        return fetch_project_workflow_package(conn, project_id)
```

- [ ] **Step 3: Add `POST /api/projects/{project_id}/workflow/preview` — Preview prompts**

Replaces `POST /api/docx-workflow/runs/{run_id}/preview`:

```python
@app.post("/api/projects/{project_id}/workflow/preview")
def preview_project_workflow(project_id: str) -> dict:
    with get_db() as conn:
        return fetch_project_workflow_package(conn, project_id)
```

- [ ] **Step 4: Add `POST /api/projects/{project_id}/workflow/generate` — Generate all images**

Replaces `POST /api/docx-workflow/runs/{run_id}/generate`. Launches background thread:

```python
@app.post("/api/projects/{project_id}/workflow/generate")
def generate_project_workflow(project_id: str, payload: DocxWorkflowGenerateIn) -> dict:
    with get_db() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        steps = fetch_project_workflow_steps(conn, project_id)
        if len(steps) != 9:
            raise HTTPException(400, "工作流步骤不完整，需要 9 步")
        # Update project workflow params if provided
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
```

- [ ] **Step 5: Add `GET /api/projects/{project_id}/workflow/download` — Download zip**

Replaces `GET /api/docx-workflow/runs/{run_id}/download`:

```python
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
```

- [ ] **Step 6: Add `PATCH /api/projects/workflow/steps/{step_id}` — Update step prompt/refs**

Replaces `PATCH /api/docx-workflow/steps/{step_id}`. Same logic but queries `project_workflow_steps` and uses `project_id` for status updates:

```python
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
            clean_prompt = strip_rag_context_block(prompt)
            assignments.insert(0, "prompt = ?")
            values.insert(0, clean_prompt)
        if payload.input_refs is not None:
            refs: list[dict[str, str]] = []
            for item in payload.input_refs:
                ref_type = (item.get("type") or "").strip()
                ref_id = (item.get("id") or "").strip()
                if ref_type not in ("asset", "step", "rag"):
                    raise HTTPException(400, f"无效的引用类型: {ref_type}")
                if not ref_id:
                    raise HTTPException(400, "引用 ID 不能为空")
                if ref_type == "asset":
                    asset = fetch_one(conn, "SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL", (ref_id,))
                    if asset["project_id"] != step["project_id"]:
                        raise HTTPException(400, f"素材 {ref_id} 不属于当前项目")
                elif ref_type == "step":
                    src_step = fetch_one(conn, "SELECT * FROM project_workflow_steps WHERE id = ?", (ref_id,))
                    if src_step["project_id"] != step["project_id"]:
                        raise HTTPException(400, f"步骤 {ref_id} 不属于当前项目")
                elif ref_type == "rag":
                    rag_ref = fetch_one(conn, "SELECT * FROM rag_reference_selections WHERE id = ? AND project_id = ?", (ref_id, step["project_id"]))
                refs.append({"type": ref_type, "id": ref_id})
            assignments.insert(0, "input_refs_json = ?")
            values.insert(0, to_json(refs))
        values.append(step_id)
        conn.execute(
            f"UPDATE project_workflow_steps SET {', '.join(assignments)} WHERE id = ?",
            tuple(values),
        )
        # Re-apply RAG context
        updated_step = row_to_dict(conn.execute("SELECT * FROM project_workflow_steps WHERE id = ?", (step_id,)).fetchone())
        project_id = step["project_id"]
        rag_refs = conn.execute(
            "SELECT * FROM rag_reference_selections WHERE project_id = ? ORDER BY sort_order ASC, selected_at DESC",
            (project_id,),
        ).fetchall()
        if rag_refs:
            rag_block = build_rag_context_block_for_step(updated_step, [row_to_dict(r) for r in rag_refs], {})
            base_prompt = strip_rag_context_block(updated_step.get("prompt") or "")
            final_prompt = base_prompt + rag_block
            conn.execute("UPDATE project_workflow_steps SET prompt = ?, updated_at = ? WHERE id = ?", (final_prompt, now_iso(), step_id))
        return fetch_project_workflow_package(conn, project_id)
```

- [ ] **Step 7: Add `POST /api/projects/workflow/steps/{step_id}/generate` — Generate single step**

Replaces `POST /api/docx-workflow/steps/{step_id}/generate`:

```python
@app.post("/api/projects/workflow/steps/{step_id}/generate")
def generate_project_workflow_step(step_id: str, payload: DocxWorkflowGenerateIn) -> dict:
    with get_db() as conn:
        step = fetch_one(conn, "SELECT * FROM project_workflow_steps WHERE id = ?", (step_id,))
        project_id = step["project_id"]
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        all_steps = fetch_project_workflow_steps(conn, project_id)

    # Collect input paths (same logic as existing step generation)
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
            with get_db() as conn:
                src = conn.execute("SELECT * FROM project_workflow_steps WHERE id = ?", (ref["id"],)).fetchone()
            if src:
                src = row_to_dict(src)
                if src.get("image_path") and Path(src["image_path"]).is_file():
                    input_paths.append(src["image_path"])
        elif ref.get("type") == "rag":
            with get_db() as conn:
                rag = conn.execute("SELECT * FROM rag_reference_selections WHERE id = ?", (ref["id"],)).fetchone()
            if rag:
                rag = row_to_dict(rag)
                cache_path = Path(DATA_DIR) / "projects" / project_id / "rag_cache" / f"{rag['rag_image_id']}.jpg"
                if cache_path.is_file():
                    input_paths.append(str(cache_path))

    prompt = step.get("prompt") or ""
    if not prompt.strip():
        raise HTTPException(400, "提示词为空，无法生成")

    with get_db() as conn:
        conn.execute("UPDATE project_workflow_steps SET status = 'running', error = '', updated_at = ? WHERE id = ?", (now_iso(), step_id))

    size = payload.size or project.get("size") or "1024x1024"
    quality = payload.quality or project.get("quality") or "high"
    image_model = payload.image_model or project.get("image_model") or None

    try:
        result = call_image_model(
            prompt=prompt,
            input_paths=input_paths,
            image_model=image_model,
            size=size,
            quality=quality,
        )
        step_dir = Path(DATA_DIR) / "projects" / project_id / "docx_workflow" / "_project_steps"
        step_dir.mkdir(parents=True, exist_ok=True)
        stage_id = re.sub(r"[^A-Za-z0-9_-]+", "_", step.get("stage_id") or "image").strip("_")
        ext = ".png"
        filename = f"{int(step.get('image_no') or 0):02d}_{stage_id}{ext}"
        out_path = step_dir / filename
        with open(out_path, "wb") as f:
            f.write(result["image_bytes"])
        params = {k: v for k, v in result.items() if k != "image_bytes"}
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
```

- [ ] **Step 8: Add `POST /api/projects/workflow/steps/{step_id}/knowledge-candidate`**

Replaces `POST /api/docx-workflow/steps/{step_id}/knowledge-candidate`:

```python
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
               (id, project_id, run_id, step_id, image_path, rating, review_notes,
                suggested_category, suggested_scene, suggested_image_type,
                suggested_metadata_json, status, created_at, ingested_rag_image_id)
               VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, '')""",
            (
                candidate_id, project_id, step_id, step["image_path"],
                payload.rating, payload.review_notes,
                payload.suggested_category, payload.suggested_scene, payload.suggested_image_type,
                to_json(payload.suggested_metadata), now_iso(),
            ),
        )
        return {"id": candidate_id, "status": "pending"}
```

- [ ] **Step 9: Add `_run_project_workflow_in_background()` function**

This replaces `_run_generation_in_background()` for project-based workflows. Same logic but queries `project_workflow_steps` and writes to project fields:

```python
def _run_project_workflow_in_background(project_id: str, image_model: str | None, size: str, quality: str) -> None:
    from backend.app.docx_workflow import STYLE_OPTIONS

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
            elif ref.get("type") == "rag":
                with get_db() as conn:
                    rag = conn.execute("SELECT * FROM rag_reference_selections WHERE id = ?", (ref["id"],)).fetchone()
                if rag:
                    rag = row_to_dict(rag)
                    cache_path = Path(DATA_DIR) / "projects" / project_id / "rag_cache" / f"{rag['rag_image_id']}.jpg"
                    if cache_path.is_file():
                        input_paths.append(str(cache_path))

        with get_db() as conn:
            conn.execute("UPDATE project_workflow_steps SET status = 'running', error = '', updated_at = ? WHERE id = ?", (now_iso(), step_id))

        retries = 3
        last_error = ""
        for attempt in range(retries):
            try:
                result = call_image_model(
                    prompt=prompt,
                    input_paths=input_paths,
                    image_model=image_model,
                    size=size,
                    quality=quality,
                )
                step_dir = Path(DATA_DIR) / "projects" / project_id / "docx_workflow" / "_project_steps"
                step_dir.mkdir(parents=True, exist_ok=True)
                stage_id = re.sub(r"[^A-Za-z0-9_-]+", "_", step.get("stage_id") or "image").strip("_")
                filename = f"{int(step.get('image_no') or 0):02d}_{stage_id}.png"
                out_path = step_dir / filename
                with open(out_path, "wb") as f:
                    f.write(result["image_bytes"])
                params = {k: v for k, v in result.items() if k != "image_bytes"}
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
            conn.execute(
                "UPDATE project_workflow_steps SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                (last_error, now_iso(), step_id),
            )
        return False

    stage_output_paths: dict[str, str] = {}

    with get_db() as conn:
        step_rows = conn.execute(
            "SELECT id, stage_id, generation_order FROM project_workflow_steps WHERE project_id = ? ORDER BY generation_order ASC",
            (project_id,),
        ).fetchall()

    steps_info = [{"id": r["id"], "stage_id": r["stage_id"], "order": r["generation_order"]} for r in step_rows]

    # Steps 0-1 sequential
    for i in range(min(2, len(steps_info))):
        success = run_step(steps_info[i]["id"])
        if not success:
            with get_db() as conn:
                conn.execute("UPDATE projects SET workflow_status = 'failed', workflow_error = '步骤失败', updated_at = ? WHERE id = ?", (now_iso(), project_id))
            return

    # Steps 2-8 parallel
    parallel_steps = steps_info[2:]
    if parallel_steps:
        with ThreadPoolExecutor(max_workers=min(len(parallel_steps), 7)) as executor:
            futures = {executor.submit(run_step, s["id"]): s for s in parallel_steps}
            for future in as_completed(futures):
                future.result()

    with get_db() as conn:
        update_project_workflow_status(conn, project_id)
```

- [ ] **Step 10: Update `list_projects` to return `workflow_status` and step summary**

Modify the `list_projects` endpoint to include workflow status and step counts:

```python
# In the results loop, replace the has_downloads check with:
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
```

- [ ] **Step 11: Update `get_project` to return workflow steps**

Modify the `get_project` endpoint to include `workflow_steps` alongside `assets`:

```python
# After the docx_runs query, add:
workflow_steps = conn.execute(
    "SELECT * FROM project_workflow_steps WHERE project_id = ? ORDER BY generation_order ASC",
    (project_id,),
).fetchall()
project["workflow_steps"] = [hydrate_docx_step(row_to_dict(row)) for row in workflow_steps]
```

- [ ] **Step 12: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(api): add project-based workflow endpoints"
```

---

### Task 4: Frontend — Remove Sidebar, Update Layout

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Remove `ProjectPanel` component from App.jsx**

Delete the entire `ProjectPanel` function (lines 75-121 in current file).

- [ ] **Step 2: Remove sidebar from workspace layout**

In the `App` component's workspace phase, change from `<main>` with `<aside>` + `<div className="workspace">` to a single-column layout:

```jsx
// Replace the workspace return block:
return (
  <div className="app-shell">
    <header>
      <div>
        <h1>DOCX 固定九图自动化生图流程</h1>
        <p>{selectedUser?.name} / {selectedProject?.name || selectedProject?.sku}</p>
      </div>
      <div className="header-right">
        <div className="status-pill">{selectedProject ? selectedProject.sku : "未选择项目"}</div>
        <button className="ghost" onClick={() => { setPhase("project"); loadProjects(selectedUser.id); }}>切换项目</button>
        <button className="ghost" onClick={() => { setSelectedUser(null); setSelectedProject(null); setProjectDetail(null); setPhase("user"); }}>切换用户</button>
      </div>
    </header>
    {error ? <div className="error-banner">{error}</div> : null}
    <main className="no-sidebar">
      {selectedProject && projectDetail ? (
        <div className="workspace">
          <AssetPanel project={selectedProject} assets={assets} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
          <RagKnowledgeWorkbench project={selectedProject} refreshProject={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
          <DocxWorkflowPanel project={selectedProject} assets={assets} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} onDownload={() => loadProjects(selectedUser.id)} />
        </div>
      ) : (
        <section className="empty-state">请从左侧选择一个项目。</section>
      )}
    </main>
  </div>
);
```

- [ ] **Step 3: Update CSS — remove sidebar grid, add full-width layout**

In `styles.css`, update the `main` layout:

```css
main {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  padding: 16px;
  min-height: calc(100vh - 88px);
}

main.no-sidebar {
  grid-template-columns: 1fr;
}
```

- [ ] **Step 4: Remove sidebar-related CSS**

Remove the `.project-list`, `.project-search`, `.project-done`, `.project-row`, `.project-row.active`, `.project`, `.project span` styles that were only used by the sidebar.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/styles.css
git commit -m "feat(ui): remove sidebar, workspace now single-column full-width"
```

---

### Task 5: Frontend — Update ProjectSelectScreen with Overview and Search

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add `workflow_status` badge rendering helper**

Add near the top of App.jsx (after the utility functions):

```jsx
function WorkflowStatusBadge({ project }) {
  const status = project.workflow_status || "idle";
  const labels = { idle: "待开始", running: "生成中", partial: "部分完成", success: "已完成", failed: "失败" };
  const downloaded = project.has_downloads;
  if (downloaded) {
    return <span className="workflow-badge downloaded">已下载</span>;
  }
  return <span className={`workflow-badge ${status}`}>{labels[status] || status}</span>;
}
```

- [ ] **Step 2: Add step progress display to project cards**

Add a helper to show step progress:

```jsx
function StepProgress({ project }) {
  const summary = project.step_summary;
  if (!summary || summary.total === 0) return null;
  return <small className="step-progress">{summary.success}/{summary.total} 张已完成</small>;
}
```

- [ ] **Step 3: Update `ProjectSelectScreen` — add SKU search**

Add a search state and filter logic:

```jsx
function ProjectSelectScreen({ user, projects, onSelect, onCreate, onDelete, onBack }) {
  const [form, setForm] = useState({ sku: "", category: "", name: "", notes: "" });
  const [search, setSearch] = useState("");
  const handleCreate = () => {
    if (!form.sku.trim()) return;
    onCreate(form);
    setForm({ sku: "", category: "", name: "", notes: "" });
  };
  const filtered = search.trim()
    ? projects.filter((p) => (p.sku || "").toLowerCase().includes(search.trim().toLowerCase()))
    : projects;
  return (
    <div className="centered-screen">
      <div className="centered-card wide-card">
        <div className="centered-card-header">
          <button className="ghost" onClick={onBack}>&larr; 返回</button>
          <h1>{user.name} 的项目</h1>
        </div>
        <div className="project-create-form">
          {/* ... existing form fields unchanged ... */}
        </div>
        <div className="project-overview-search">
          <Search size={14} />
          <input placeholder="搜索 SKU…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="project-select-list">
          {filtered.map((project) => (
            <div key={project.id} className="project-select-card-wrap">
              <button className="project-select-card" onClick={() => onSelect(project)}>
                <strong>{project.sku}</strong>
                <span>{project.name}</span>
                <small>{project.category || "未分类"}</small>
                <WorkflowStatusBadge project={project} />
                <StepProgress project={project} />
              </button>
              <button className="icon-btn danger project-delete-btn" title="删除项目" onClick={() => onDelete(project.id)}>
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="muted">{search.trim() ? "没有匹配的项目。" : "该用户还没有项目，请先创建一个。"}</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add CSS for project overview search and status badges**

```css
.project-overview-search {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0;
  padding: 6px 10px;
  border: 1px solid #e0ddd4;
  border-radius: 6px;
  background: #fff;
}

.project-overview-search svg {
  color: #9a9589;
  flex-shrink: 0;
}

.project-overview-search input {
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  width: 100%;
  padding: 0;
}

.workflow-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  display: inline-block;
  margin-top: 4px;
}

.workflow-badge.idle {
  background: #f1f5f9;
  color: #64748b;
}

.workflow-badge.running {
  background: #dbeafe;
  color: #1e40af;
}

.workflow-badge.partial {
  background: #fef3c7;
  color: #92400e;
}

.workflow-badge.success {
  background: #dcfce7;
  color: #166534;
}

.workflow-badge.downloaded {
  background: #bbf7d0;
  color: #14532d;
  font-weight: 600;
}

.workflow-badge.failed {
  background: #fee2e2;
  color: #991b1b;
}

.step-progress {
  font-size: 11px;
  color: #6d6a62;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/styles.css
git commit -m "feat(ui): add project overview with status badges and SKU search to selection page"
```

---

### Task 6: Frontend — Refactor DocxWorkflowPanel to Project-Based

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Change `DocxWorkflowPanel` props**

Remove `runs` prop, change to work with project-based workflow:

```jsx
function DocxWorkflowPanel({ project, assets, refresh, onDownload }) {
```

- [ ] **Step 2: Replace `activeRun` with `workflow` state**

Replace `activeRun` with `workflow` that comes from the project-based API:

```jsx
const [workflow, setWorkflow] = useState(null);
// Replace all `activeRun` references with `workflow`
```

- [ ] **Step 3: Load workflow on project change**

Replace the run-loading logic with project-based workflow loading:

```jsx
useEffect(() => {
  setWorkflow(null);
  // Load existing workflow for this project
  request(`/api/projects/${project.id}/workflow`)
    .then(setWorkflow)
    .catch(() => setWorkflow(null)); // No workflow yet = idle state
}, [project.id]);
```

- [ ] **Step 4: Update `createRun` to use project-based endpoint**

```jsx
const initWorkflow = async () => {
  return request(`/api/projects/${project.id}/workflow`, {
    method: "POST",
    body: JSON.stringify({ project_id: project.id, ...form }),
  });
};
```

- [ ] **Step 5: Update `preview` function**

```jsx
const preview = async () => {
  setBusy(true);
  try {
    await uploadRequiredAssets();
    const wf = await initWorkflow();
    setWorkflow(wf);
    await refresh();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
};
```

- [ ] **Step 6: Update `generate` function**

```jsx
const generate = async () => {
  setBusy(true);
  try {
    if (workflow) await saveAllPrompts();
    const wf = workflow ? workflow : await initWorkflow();
    if (!workflow) setWorkflow(wf);
    const generated = await request(`/api/projects/${project.id}/workflow/generate`, {
      method: "POST",
      body: JSON.stringify({ image_model: form.image_model, size: form.size, quality: form.quality }),
    });
    setWorkflow(generated);
    await refresh();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
};
```

- [ ] **Step 7: Update `downloadRun` function**

```jsx
const downloadRun = async () => {
  if (!workflow || !docxRunReadyToDownload(workflow)) return;
  setBusy(true);
  try {
    const res = await fetch(`${API}/api/projects/${project.id}/workflow/download`);
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match?.[1] || `${project.sku || "docx"}_${project.id.slice(0, 8)}_images.zip`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    onDownload?.();
  } finally {
    setBusy(false);
  }
};
```

- [ ] **Step 8: Update `savePrompt` and `saveAllPrompts`**

```jsx
const savePrompt = async (stepId, prompt) => {
  const updated = await request(`/api/projects/workflow/steps/${stepId}`, {
    method: "PATCH",
    body: JSON.stringify({ prompt }),
  });
  setWorkflow(updated);
  return updated;
};
```

- [ ] **Step 9: Update `regenerateStep`**

```jsx
const regenerateStep = async (stepId) => {
  if (!workflow) return;
  setBusy(true);
  try {
    const prompt = promptDrafts[stepId] ?? workflow.steps?.find((step) => step.id === stepId)?.prompt ?? "";
    await savePrompt(stepId, prompt);
    setWorkflow((current) => current ? {
      ...current,
      steps: (current.steps || []).map((step) => step.id === stepId ? { ...step, status: "running", error: "", url: "" } : step),
    } : current);
    const generated = await request(`/api/projects/workflow/steps/${stepId}/generate`, {
      method: "POST",
      body: JSON.stringify({ image_model: form.image_model, size: form.size, quality: form.quality }),
    });
    setWorkflow(generated);
    await refresh();
  } finally {
    setBusy(false);
  }
};
```

- [ ] **Step 10: Update `removeRagRefFromStep`**

```jsx
const removeRagRefFromStep = async (step, ragRefId) => {
  const currentRefs = step.input_refs || [];
  const newRefs = currentRefs.filter((ref) => !(ref.type === "rag" && ref.id === ragRefId));
  setBusy(true);
  try {
    const updated = await request(`/api/projects/workflow/steps/${step.id}`, {
      method: "PATCH",
      body: JSON.stringify({ input_refs: newRefs }),
    });
    setWorkflow(updated);
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
};
```

- [ ] **Step 11: Update `markKnowledgeCandidate`**

```jsx
const markKnowledgeCandidate = async (step) => {
  if (!step?.id || !step.url) return;
  setBusy(true);
  try {
    await request(`/api/projects/workflow/steps/${step.id}/knowledge-candidate`, {
      method: "POST",
      body: JSON.stringify({
        rating: 5,
        review_notes: "九图流程人工标记候选",
        suggested_category: project.category || "",
        suggested_scene: step.stage_id || "",
        suggested_image_type: "main_image",
        suggested_metadata: {},
      }),
    });
    alert("已标记为知识库候选");
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
};
```

- [ ] **Step 12: Update auto-refresh polling**

```jsx
useEffect(() => {
  if (!workflow || workflow.workflow_status !== "running") return;
  const interval = setInterval(async () => {
    try {
      const updated = await request(`/api/projects/${project.id}/workflow`);
      setWorkflow(updated);
      if (updated.workflow_status !== "running") {
        clearInterval(interval);
        await refresh();
      }
    } catch (err) {
      console.warn("Auto-refresh failed", err);
    }
  }, 10000);
  return () => clearInterval(interval);
}, [workflow?.project_id, workflow?.workflow_status]);
```

- [ ] **Step 13: Update `promptDrafts` sync**

```jsx
useEffect(() => {
  const drafts = {};
  (workflow?.steps || []).forEach((step) => {
    drafts[step.id] = step.prompt || "";
  });
  setPromptDrafts(drafts);
}, [workflow]);
```

- [ ] **Step 14: Update render — remove run list, update references**

Remove the run list (`docx-run-list`) section entirely. Replace all `activeRun` with `workflow` in the JSX. Update the action buttons:

```jsx
<div className="docx-actions">
  <button className="primary" disabled={!ready || busy} onClick={preview}>
    <FileImage size={16} />
    预览 9 张提示词
  </button>
  <button className="primary" disabled={(!ready && !workflow) || busy} onClick={generate}>
    <Sparkles size={16} />
    一键生成 9 张图
  </button>
  <button disabled={!docxRunReadyToDownload(workflow) || busy} onClick={downloadRun}>
    一键下载 9 张图
  </button>
</div>
{/* No run list here anymore */}
{workflow ? (
  <div className="docx-preview">
    {/* ... step grid uses workflow.steps ... */}
  </div>
) : null}
```

- [ ] **Step 15: Update `loadRun` — remove or replace with workflow reload**

The `loadRun` function is no longer needed. Remove it and remove the run list buttons that called it.

- [ ] **Step 16: Update `docxRunReadyToDownload` helper**

Change the helper to work with the workflow object (which has `steps` directly):

```jsx
function docxRunReadyToDownload(wf) {
  const steps = wf?.steps || [];
  return steps.length === 9 && steps.every((step) => step.status === "success" && (step.url || step.image_path));
}
```

- [ ] **Step 17: Remove `runs` from App.jsx workspace rendering**

In the App component, remove `docxRuns` variable and the `runs` prop from `DocxWorkflowPanel`:

```jsx
// Remove: const docxRuns = projectDetail?.docx_workflow_runs || [];
// Update DocxWorkflowPanel usage:
<DocxWorkflowPanel project={selectedProject} assets={assets} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} onDownload={() => loadProjects(selectedUser.id)} />
```

- [ ] **Step 18: Remove run-related CSS**

Remove `.docx-run-list`, `.docx-run-item`, `.run-status-badge`, `.run-error` styles from styles.css.

- [ ] **Step 19: Commit**

```bash
git add frontend/src/App.jsx frontend/src/styles.css
git commit -m "feat(ui): refactor DocxWorkflowPanel to project-based workflow"
```

---

### Task 7: Cleanup — Remove Unused Code and Old Run Endpoints

**Files:**
- Modify: `backend/app/main.py`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Remove old docx-workflow run endpoints (optional — keep for backward compat)**

Mark the old run-based endpoints with comments indicating they are deprecated. Do NOT delete them yet in case old clients need them:

```python
# DEPRECATED: Use /api/projects/{project_id}/workflow instead
@app.post("/api/docx-workflow/runs")
def create_docx_workflow_run(payload: DocxWorkflowRunIn) -> dict:
    ...
```

- [ ] **Step 2: Remove unused `Database` import if no longer used**

Check if `Database` icon from lucide-react is still used. If not, remove from import. (It's still used in `RagKnowledgeWorkbench`, so keep it.)

- [ ] **Step 3: Remove `loadRun` function from DocxWorkflowPanel**

This function loaded individual runs and is no longer needed.

- [ ] **Step 4: Verify no broken references**

Search for any remaining references to `activeRun`, `runs`, `docxRuns`, `ProjectPanel` in the frontend code and fix them.

- [ ] **Step 5: Build and test**

```powershell
cd frontend
npm run build
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py frontend/src/App.jsx
git commit -m "chore: cleanup deprecated run references, verify build"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Start backend and test API endpoints**

```powershell
$env:PORT='8010'; python .\run_backend.py
```

Test:
- `GET /api/projects?user_id=default` — should return projects with `workflow_status` and `step_summary`
- `POST /api/projects/{id}/workflow` — should initialize workflow
- `GET /api/projects/{id}/workflow` — should return workflow with steps

- [ ] **Step 2: Start frontend dev server and test UI**

```powershell
cd frontend; npm run dev
```

Test:
- Project selection page shows status badges and SKU search
- Clicking a project enters workspace (no sidebar)
- Workflow panel operates on project directly (no run list)
- Download triggers completion badge on project selection page

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete project-based workflow refactor"
```
