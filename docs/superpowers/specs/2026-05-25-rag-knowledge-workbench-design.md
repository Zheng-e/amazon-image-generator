# RAG 知识库工作台式主图生成 V2 设计

## 状态

草案，等待用户评审后进入实施计划拆分。

## 背景

当前主图生成工具运行在 `http://192.168.0.186:8021/workbench/`，核心能力是固定九图 DOCX 工作流。用户上传产品图、模特图、上身效果参考图、场景图后，系统创建 9 个步骤，支持预览提示词、修改提示词、单张重生、一键生成和打包下载。

RAG 知识库项目位于 `D:\RAG`，当前本机服务可通过 `http://127.0.0.1:8010` 访问。已验证 `/health` 正常，当前约 27 张图，使用 `qwen` embedding 和 `qdrant` 向量后端。RAG 提供图片检索、图片访问、记录管理和入库能力。

第二版目标不是推翻现有九图流程，而是在九图流程之前增加一个“知识库工作台”，让用户先从 RAG 中选图、筛图、归类，再把选中的知识库图片和字段摘要带入九图生成流程。

## 目标

1. 在主图工具中新增 RAG 知识库工作台，作为九图流程的前置入口。
2. 支持按产品、风格、场景、构图、光影、季节、关键词检索知识库图片。
3. 支持把知识库结果加入当前项目，形成项目级参考池。
4. 支持为选中图片标注用途，例如场景参考、姿势参考、构图参考、色调参考、白底主图参考、竞品上身参考。
5. 创建九图流程时，根据参考池自动增强各步骤提示词，并把合适参考图带入对应步骤。
6. 生成完成后，支持把优质结果标记为知识库候选，后续沉淀回 RAG。

## 非目标

1. V2 首期不合并 `D:\RAG` 与主图生成项目，两者保持独立服务。
2. V2 首期不重做现有九图工作流，只在其前后扩展。
3. V2 首期不实现复杂自动审图，只保留人工评分、人工标记和候选入库入口。
4. V2 首期不强制支持视频、`multi_images` 多图序列或 RAG 高级模型参数控制台。

## 推荐架构

采用“主图后端代理 RAG”的架构。

浏览器只访问主图生成工具：

```text
Browser
  -> http://192.168.0.186:8021/workbench/
  -> http://192.168.0.186:8021/api/rag/*
  -> Main Image Backend
  -> RAG_BASE_URL=http://127.0.0.1:8010
  -> RAG FastAPI / Qwen embedding / Qdrant
```

这样前端不直接访问 RAG 端口，局域网访问、CORS、图片代理和后续端口调整都由主图后端统一处理。

推荐新增环境变量：

```text
RAG_BASE_URL=http://127.0.0.1:8010
RAG_TIMEOUT_SECONDS=30
```

## 用户流程

1. 用户打开主图工具 `http://192.168.0.186:8021/workbench/`。
2. 用户创建或选择一个项目，填写 SKU、品类、产品名、材质等基础信息。
3. 用户进入“知识库工作台”。
4. 系统根据项目字段生成默认检索词，例如“女装 背心 欧洲街拍 低饱和暖调 竖幅中景构图”。
5. 用户可手动调整检索词和过滤条件。
6. 工作台展示 RAG 返回的图片卡片，包含缩略图、相似度、品类、场景、构图、caption、metadata 摘要。
7. 用户选择满意图片，点击“加入本项目”。
8. 用户为选中图片分配用途标签。
9. 用户进入九图流程，系统基于参考池自动创建 RAG 增强版流程。
10. 用户检查每一步提示词和参考图，必要时手动调整。
11. 用户一键生成九图。
12. 用户对结果评分，将优秀结果标记为知识库候选。
13. 用户确认后，候选结果提交到 RAG `/ingest`，成为后续项目可检索的知识库图片。

## 页面设计

新增一个主区域或标签页：`知识库工作台`。

工作台分为四块：

1. 检索区：关键词输入、top_k、品类、场景、构图、合规状态等过滤条件。
2. 结果区：RAG 图片卡片瀑布流或网格，支持预览大图、查看元数据、加入项目。
3. 项目参考池：显示已加入的图片，支持删除、调整用途标签、排序。
4. 流程联动区：显示“将参考池应用到九图流程”的预览，说明每类参考图会影响哪些步骤。

图片用途标签首期固定为：

```text
scene_reference
pose_reference
composition_reference
color_reference
white_main_reference
competitor_fit_reference
```

前端显示中文名：

```text
场景参考
姿势参考
构图参考
色调参考
白底主图参考
竞品上身参考
```

## 后端接口设计

主图后端首期新增 RAG 代理接口：

```text
GET  /api/rag/health
POST /api/rag/search
GET  /api/rag/images/{image_id}
```

第二阶段新增以图搜图代理：

```text
POST /api/rag/search-image
```

主图后端新增项目参考池接口：

```text
GET    /api/projects/{project_id}/rag-references
POST   /api/projects/{project_id}/rag-references
PATCH  /api/projects/{project_id}/rag-references/{reference_id}
DELETE /api/projects/{project_id}/rag-references/{reference_id}
```

生成后候选保存接口：

```text
POST /api/docx-workflow/steps/{step_id}/knowledge-candidate
```

第二阶段新增一键提交 RAG 入库接口：

```text
POST /api/knowledge-candidates/{candidate_id}/ingest-to-rag
```

首期只实现“保存候选记录”。这样即使 RAG 入库暂未接通，也不会丢失人工筛选结果。

## 数据模型

新增表 `rag_reference_selections`：

```text
id TEXT PRIMARY KEY
project_id TEXT NOT NULL
rag_image_id TEXT NOT NULL
filename TEXT DEFAULT ''
category TEXT DEFAULT ''
scene TEXT DEFAULT ''
image_type TEXT DEFAULT ''
caption TEXT DEFAULT ''
score REAL
usage_tags_json TEXT NOT NULL DEFAULT '[]'
metadata_json TEXT NOT NULL DEFAULT '{}'
sort_order INTEGER NOT NULL DEFAULT 0
selected_at TEXT NOT NULL
notes TEXT DEFAULT ''
```

新增表 `docx_knowledge_candidates`：

```text
id TEXT PRIMARY KEY
project_id TEXT NOT NULL
run_id TEXT NOT NULL
step_id TEXT NOT NULL
image_path TEXT NOT NULL
rating INTEGER
review_notes TEXT DEFAULT ''
suggested_category TEXT DEFAULT ''
suggested_scene TEXT DEFAULT ''
suggested_image_type TEXT DEFAULT ''
suggested_metadata_json TEXT NOT NULL DEFAULT '{}'
status TEXT NOT NULL DEFAULT 'pending'
created_at TEXT NOT NULL
ingested_rag_image_id TEXT DEFAULT ''
```

`rag_reference_selections` 保存 RAG 记录快照和用途标签，不复制原图文件。生成时如果图片模型需要本地文件，主图后端通过 RAG 图片代理临时下载到项目缓存目录，并把缓存路径作为参考图传入现有生图调用。

## 九图流程联动规则

创建九图流程时，系统读取项目参考池，根据用途标签生成增强内容。

第 1 张“模特上身图”：

```text
主要使用用户上传的产品图、模特图、上身效果参考图。
可选吸收 competitor_fit_reference 的上身松紧、衣长、产品展示方式摘要。
```

第 2 张“场景模特图”：

```text
优先使用 scene_reference、color_reference。
将 RAG 场景、色调、光影字段摘要追加到场景融合要求。
```

第 3-6 张“正侧背其他角度图”：

```text
优先使用 pose_reference、composition_reference。
将姿势、构图、镜头距离、画幅比例摘要追加到角度图要求。
```

第 7 张“穿搭图”：

```text
优先使用 pose_reference、color_reference。
强化道具、搭配氛围、街拍感或日常感，但不覆盖产品主体。
```

第 8 张“白底主图”：

```text
优先使用 white_main_reference、composition_reference。
仅吸收构图、产品占比、裁切方式，不吸收复杂背景。
```

第 9 张“背面白底图”：

```text
优先使用 white_main_reference、composition_reference。
强调背面或侧背产品展示，保持白底规范。
```

## 提示词增强策略

RAG 字段不直接整段塞入提示词。系统先生成短摘要，再按步骤追加。

摘要格式：

```text
知识库参考摘要：{场景}，{视觉风格}，{整体色调}，{构图}，{光影}，{季节}。
```

示例：

```text
知识库参考摘要：欧洲风格城市街道，高级质感的欧美都市街拍风，低饱和暖调大地色系，竖幅中景构图，明亮柔和侧方自然光，春夏。
```

每个步骤最多吸收 3 张 RAG 图的摘要。超过 3 张时按用户排序和相似度选择前 3 张。这样可以避免提示词过长、互相冲突。

## 参考图传递策略

首期保持现有 `input_refs` 机制，新增一种内部引用来源：

```text
{"type": "rag", "id": "<reference_selection_id>"}
```

在实际调用图片模型前，后端把 `rag` 引用解析为本地缓存图片路径。缓存位置建议：

```text
output/workbench/projects/{project_id}/rag_cache/{rag_image_id}.<ext>
```

缓存文件可复用，不随单次流程删除。删除项目时随项目目录一起清理。

## 错误处理

1. RAG 服务不可达：工作台显示“知识库暂不可用”，不影响普通九图流程。
2. RAG 搜索失败：保留用户检索词，展示错误详情，允许重试。
3. RAG 图片下载失败：该参考图在九图流程中跳过，并在步骤预览中提示。
4. RAG 摘要字段缺失：用已有字段拼摘要，缺失项不展示。
5. 入库回流失败：候选记录保持 `pending` 或 `failed`，允许用户稍后重试。

## 测试与验证

后端测试重点：

1. RAG 代理能正确转发 `/health`、`/search`、`/images/{image_id}`。
2. 项目参考池 CRUD 正常，且只能操作当前项目的数据。
3. RAG 引用能解析为本地缓存图片路径。
4. 创建九图流程时，RAG 摘要能追加到正确步骤。
5. RAG 不可用时，普通九图流程仍能创建和生成。

前端验证重点：

1. 在 `http://192.168.0.186:8021/workbench/` 打开后，知识库工作台可搜索。
2. 搜索结果图片能显示，元数据中文正常。
3. 选图、打标签、删除、排序体验顺畅。
4. 进入九图流程后，能看到 RAG 增强提示词和参考图。
5. 生成结果能标记为知识库候选。

## MVP 实施范围

第一阶段实现：

1. 主图后端新增 RAG 配置和代理接口。
2. 新增项目参考池数据表和 CRUD 接口。
3. 前端新增知识库工作台。
4. 九图流程创建时支持 RAG 摘要增强。
5. RAG 图片作为参考图进入图片模型调用。
6. 生成结果支持保存为知识库候选。

第二阶段实现：

1. 候选结果一键提交到 RAG `/ingest`。
2. 支持按图片反搜 `/search-image`。
3. 支持参考池批量自动推荐用途标签。
4. 支持从生成结果评分中学习默认检索词和排序偏好。

## 成功标准

1. 用户可以在主图工具内完成 RAG 搜索、选图、打标签，不需要打开 RAG 独立页面。
2. 用户选中的知识库图片能实际影响九图流程的提示词和参考图。
3. RAG 服务故障不会阻断原有九图流程。
4. 生成结果可以被沉淀为候选，形成“检索参考 -> 生成 -> 人工筛选 -> 回流知识库”的闭环。
5. V2 改动保持在主图项目的清晰边界内，不破坏现有 DOCX 九图流程。
