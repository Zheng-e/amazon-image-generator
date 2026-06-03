# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指引。

## 项目概述

亚马逊服装商品主图生成工具（设计部主图生成字段实验台）。通过固定的 9 步工作流，调用 AI 图片生成 API（兼容 OpenAI 和 Gemini 两种接口）自动生成一套完整的商品图。

## 常用命令

### 后端
```powershell
# 安装依赖（在项目根目录执行）
pip install -r requirements.txt

# 启动后端服务（默认端口 8010）
$env:PORT='8010'; python .\run_backend.py

# 运行测试
pytest tests/
pytest tests/test_rag_integration.py -v   # 单个测试文件
```

### 前端
```powershell
cd frontend
npm install
npm run dev       # 开发服务器 http://localhost:5173，API 代理到后端
npm run build     # 构建产物在 frontend/dist/，需手动复制到 backend/app/static/
```

### 访问地址
- 本机：`http://localhost:8010/workbench/`
- 局域网：`http://<你的IP>:8010/workbench/`

## 架构说明

### 后端（FastAPI + SQLite）

- **`run_backend.py`** — 入口文件，启动 uvicorn，加载 `backend.app.main:app`
- **`backend/app/main.py`** — 所有 API 端点。单文件 FastAPI 应用，包含项目/素材/工作流的增删改查和图片生成编排逻辑
- **`backend/app/ai_clients.py`** — AI API 调用封装层，支持两种接口：
  - `openai_images_edits` — multipart 图片编辑接口（gpt-image-2）
  - `gemini_native` — Gemini 原生生图接口（gemini-3-pro-image-preview、gemini-3.1-flash-image-preview）
  - API 密钥从项目根目录的 `api.txt`（图片模型）和 `api key.txt`（分析/文字模型）加载，按模型分组，通过 `KeyRotator` 轮询使用
- **`backend/app/db.py`** — SQLite 数据库层。数据库路径 `output/workbench/design_workbench.db`，使用 WAL 模式。`row_to_dict()` 自动反序列化 `*_json` 后缀的列。通过 `migrate_existing_db()` 做增量迁移
- **`backend/app/docx_workflow.py`** — 9 步工作流定义，包含提示词模板和 3 种摄影风格（`natural_fashion`、`cinematic_documentary`、`street_film`）
- **`backend/app/rag_integration.py`** — RAG 知识库集成。对接外部 RAG 服务（默认 `http://127.0.0.1:8010`），处理参考图搜索、图片代理、用途标签管理和提示词上下文注入
- **`backend/app/static/`** — 预构建的前端页面，挂载在 `/workbench/` 路径

### 前端（React 19 + Vite 7）

- 所有代码在 `frontend/src/App.jsx` 单文件中 — 组件、状态管理、API 调用全部集中
- 图标库：`lucide-react`
- API 基地址：`window.location.origin`（同源）或 `VITE_API_BASE` 环境变量
- Vite 基路径：`/workbench/`（需与后端挂载路径一致）

### 9 图工作流

每次工作流运行生成 9 张图：
1. 第 1-2 步：顺序执行（第 2 步依赖第 1 步输出）
2. 第 3-9 步：并行执行（ThreadPoolExecutor，最多 7 线程）

步骤之间通过 `input_refs` 引用，每个引用有 `type`（asset/step/rag）和 `id`。RAG 参考图会将上下文信息注入到提示词中。

### 数据存储

- 数据库：`output/workbench/design_workbench.db`
- 上传素材：`output/workbench/projects/{project_id}/{asset_type}/`
- 生成图片：`output/workbench/projects/{project_id}/docx_workflow/{run_id}/`
- RAG 缓存：`output/workbench/projects/{project_id}/rag_cache/`

### API 密钥配置

在项目根目录创建 `api.txt`，格式为模型名后跟密钥，每行一个：
```
gpt-image-2
sk-xxxxx
sk-yyyyy
```

文字/分析模型的密钥放在 `api key.txt`，格式相同。

环境变量可覆盖默认值：`IMAGE_API_URL`、`IMAGE_MODEL`、`IMAGE_API_KEYS`、`TEXT_API_URL`、`TEXT_MODEL`、`TEXT_API_KEYS`、`RAG_BASE_URL`（默认 `http://127.0.0.1:8010`）、`RAG_TIMEOUT_SECONDS`。

## 开发约定

- 所有界面文字使用简体中文
- ID 格式为 `uuid4().hex`（32 位十六进制字符串）
- SQLite 中 JSON 列使用 `_json` 后缀；`row_to_dict()` 会去掉后缀并反序列化
- 素材通过 `deleted_at` 字段做软删除
- 图片生成有重试机制（3-4 次，指数退避）
- `api.txt` 和 `api key.txt` 已加入 `.gitignore`（含密钥）
- `.webdeps/` 或 `.deps/` 目录存在时会自动加入 `sys.path`（预装依赖的快捷方式）
