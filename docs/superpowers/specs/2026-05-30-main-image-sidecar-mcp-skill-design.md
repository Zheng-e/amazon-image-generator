# 主图生成旁路 MCP 与 Skill 封装设计

## 目标

在完全不修改、不重启主图生成项目和 `D:\RAG` 现有服务代码的前提下，新增独立旁路封装：

- 提供一个“主图生成任务 MCP”，统一承接项目素材准备、九图生成、进度查询、单图重生成和套图下载。
- 提供一个“图片知识库 MCP”，统一承接参考图检索、图片详情查询、图片入库和健康检查。
- 提供一个标准 `main-image-suite` Skill，指导 Agent 按业务流程调用两个 MCP。
- 同时支持本机 AI 客户端使用的 `stdio` 入口和公司内系统使用的 Streamable HTTP 入口。

## 现有代码结论

### 主图生成项目

主图生成项目已经在现有 FastAPI 服务中实现固定九图工作流：

1. 模特上身图
2. 场景模特图
3. 正面角度图
4. 侧面角度图
5. 背面角度图
6. 其他角度图
7. 穿搭图
8. 白底主图
9. 背面白底图

工作流内部已包含：

- 项目创建
- 素材上传
- 九图方案初始化
- 整套生成
- 单图重生成
- 进度和结果查询
- ZIP 下载
- RAG 参考图选择和转项目素材

### 图片知识库

`D:\RAG` 已经提供 FastAPI 服务，并在 `http://127.0.0.1:8010` 运行。现有能力包括：

- 图片入库
- 文本检索
- 图片联合检索
- 图片详情列表
- 图片访问地址
- 健康检查

`D:\RAG\mcp_server.py` 已有检索 MCP 雏形，但本次不修改该文件。旁路封装将复用其现有 FastAPI API，并补齐图片入库工具。

## 范围

### 新增内容

```text
standardization/
  mcp-server/
    .env.example
    requirements.txt
    main_image_api.py
    rag_api.py
    main_image_server.py
    rag_server.py
    start_main_image_stdio.ps1
    start_main_image_http.ps1
    start_rag_stdio.ps1
    start_rag_http.ps1
    client-config.example.json
  skills/
    main-image-suite/
      SKILL.md
      agents/
        openai.yaml
      references/
        api-guide.md
  tests/
    test_main_image_api.py
    test_rag_api.py
    test_mcp_servers_smoke.py
```

### 不修改内容

- `backend/`
- `frontend/`
- `run_backend.py`
- `D:\RAG` 下的全部文件
- 当前正在运行的 RAG 服务
- 当前正在运行的其他项目服务

## MCP 设计

## 主图生成任务 MCP

### 服务定位

将同一类“主图项目处理”能力统一归并为一个 MCP 服务。页面层的上传、查询和下载动作保留为内部工具，不拆成多个 MCP 服务。

### 工具

| 工具 | 说明 |
|---|---|
| `create_main_image_project` | 创建一个主图生成项目 |
| `upload_project_assets` | 将产品图、模特图、上身参考图、场景图、配饰图等素材上传到项目 |
| `initialize_nine_image_workflow` | 根据商品信息和素材编号初始化固定九图方案 |
| `generate_nine_image_suite` | 提交整套九图生成任务 |
| `get_nine_image_workflow` | 查询九张图片的生成状态和结果 |
| `regenerate_nine_image_step` | 对指定失败或不满意的单张图片重新生成 |
| `download_nine_image_suite` | 下载完整九图 ZIP 结果包 |
| `search_rag_references` | 通过主图服务的 RAG 代理检索参考图 |
| `add_rag_reference_to_project` | 将知识库候选图片加入指定项目 |
| `copy_rag_reference_to_project_asset` | 将知识库图片复制到项目素材中 |

### 调用映射

| MCP 工具 | 现有服务 API |
|---|---|
| `create_main_image_project` | `POST /api/projects` |
| `upload_project_assets` | `POST /api/assets` |
| `initialize_nine_image_workflow` | `POST /api/projects/{project_id}/workflow` |
| `generate_nine_image_suite` | `POST /api/projects/{project_id}/workflow/generate` |
| `get_nine_image_workflow` | `GET /api/projects/{project_id}/workflow` |
| `regenerate_nine_image_step` | `POST /api/projects/workflow/steps/{step_id}/generate` |
| `download_nine_image_suite` | `GET /api/projects/{project_id}/workflow/download` |
| `search_rag_references` | `POST /api/rag/search` |
| `add_rag_reference_to_project` | `POST /api/projects/{project_id}/rag-references` |
| `copy_rag_reference_to_project_asset` | `POST /api/projects/{project_id}/rag-to-asset` |

## 图片知识库 MCP

### 服务定位

将 RAG 视为独立的图片知识库基础能力。它不负责九图业务逻辑，只负责图片入库、检索、详情查询和健康检查。

### 工具

| 工具 | 说明 |
|---|---|
| `search_knowledge_images` | 使用文字描述检索参考图 |
| `search_knowledge_images_by_image` | 使用参考图片和可选说明检索相似图片 |
| `add_knowledge_image` | 将优秀图片加入知识库 |
| `list_knowledge_records` | 查询已入库图片记录 |
| `get_knowledge_image_url` | 获取指定图片访问地址 |
| `get_knowledge_base_health` | 查询图片知识库运行状态 |

### 调用映射

| MCP 工具 | RAG 服务 API |
|---|---|
| `search_knowledge_images` | `POST /search` |
| `search_knowledge_images_by_image` | `POST /search-image` |
| `add_knowledge_image` | `POST /ingest` |
| `list_knowledge_records` | `GET /records` |
| `get_knowledge_image_url` | 拼接 `GET /images/{image_id}` 地址 |
| `get_knowledge_base_health` | `GET /health` |

## 传输入口

两个 MCP 服务均提供两种入口，共用同一套 API 适配器：

| 入口 | 用途 |
|---|---|
| `stdio` | 本机 Codex、Claude Desktop 等 AI 客户端 |
| Streamable HTTP | 公司内其他系统或远程 Agent |

HTTP MCP 默认仅监听 `127.0.0.1`。需要局域网访问时，由部署人员显式设置监听地址为 `0.0.0.0`。

## Skill 设计

新增一个标准 `main-image-suite` Skill。它不复制后端业务实现，只指导 Agent 正确串联两个 MCP。

Skill 按以下四个业务能力组织：

| Skill 内部业务能力 | 说明 |
|---|---|
| 九图方案规划 | 使用现有固定九图流程，明确每张图片的目的、依赖顺序和参考素材 |
| 参考图说明生成 | 明确参考图中可借鉴的构图、场景、姿势和风格，以及禁止照搬的人物身份、服装、品牌和文字 |
| 人物、服装、场景一致性保护 | 在九图生成过程中保持人物身份、商品版型、材质、场景风格和摄影质感一致 |
| 产品套图生成 | 串联知识库检索、项目素材上传、九图初始化、整套生成、进度跟踪、单图重试和结果下载 |

## 数据流

```text
Agent 或公司内系统
  -> main-image-suite Skill
  -> 图片知识库 MCP
  -> D:\RAG FastAPI 服务
  -> 返回参考图片
  -> 主图生成任务 MCP
  -> 主图生成 FastAPI 服务
  -> 云端图片生成模型
  -> 返回九图状态和 ZIP 结果
```

## 配置

旁路 MCP 使用独立环境变量：

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `MAIN_IMAGE_API_BASE_URL` | `http://127.0.0.1:8020` | 主图生成现有 FastAPI 服务地址 |
| `MAIN_IMAGE_MCP_HOST` | `127.0.0.1` | 主图生成 HTTP MCP 监听地址 |
| `MAIN_IMAGE_MCP_PORT` | `8767` | 主图生成 HTTP MCP 监听端口 |
| `RAG_API_BASE_URL` | `http://127.0.0.1:8010` | 现有图片知识库 FastAPI 服务地址 |
| `RAG_MCP_HOST` | `127.0.0.1` | 图片知识库 HTTP MCP 监听地址 |
| `RAG_MCP_PORT` | `8768` | 图片知识库 HTTP MCP 监听端口 |

主图生成服务当前未运行。由于 RAG 已占用 `8010`，启动主图生成服务时建议显式设置：

```powershell
$env:PORT = "8020"
python .\run_backend.py
```

## 错误处理

- MCP 不主动启动、停止或重启现有服务。
- 提交前检查所有本机素材路径是否为绝对路径且文件存在。
- 服务不可访问时返回清晰错误，不自动修改运行环境。
- 下载结果时默认不覆盖已有 ZIP 文件。
- RAG 入库只通过现有 `/ingest` API 执行，不直接写数据库或向量库。
- 九图生成失败时保留项目和步骤状态，允许查询后按步骤重生成。

## 验证

实施后执行：

1. 使用模拟 HTTP 响应验证两个 API 适配器。
2. 启动两个 `stdio` MCP，确认初始化并列出工具。
3. 启动两个 Streamable HTTP MCP，确认客户端可以握手并列出工具。
4. 运行主图生成原项目测试。
5. 检查 `http://127.0.0.1:8010/health`，确认 RAG 服务仍正常。
6. 检查 Git diff，确认未修改现有业务代码。
