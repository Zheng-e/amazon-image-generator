# RAG 参考图分配与提示词说明优化设计文档

## 1. 背景

当前项目已经完成第二版 RAG 知识库工作台，并支持把知识库图片加入“项目参考池”，再进入固定九图生成流程。

现有流程已经能自动把项目参考池中的知识库图片按用途标签分配到九图流程中，但对用户和模型来说仍然不够清楚：

1. 用户不知道项目参考池中的某张知识库图片，最终会成为九张图中哪一张图的参考图。
2. 用户不知道某张知识库图片的摘要，会被追加到哪一张图的提示词中。
3. 知识库图片加入生成时，提示词只写了摘要，没有明确告诉模型“这张知识库图是什么图”。
4. 模型拿到额外参考图后，缺少清晰的“只参考什么、不参考什么”约束，容易误用人物、服装、品牌、文字、水印等信息。

本次优化目标是把 RAG 参考图从“后台自动使用”升级为“前台可见、生成前可确认、提示词中可解释、生成后可追踪”。

## 2. 设计目标

本次只优化主图生成项目，不修改 `D:\RAG` 服务。

需要实现以下目标：

1. 在 RAG 工作台中，用户能看到每张项目参考池图片预计会影响九图流程中的哪几张图。
2. 在九图提示词预览中，用户能看到每张图实际使用了哪些知识库参考图。
3. 每张知识库参考图都要有“给模型看的说明”，明确告诉模型这张图是什么。
4. 提示词中必须明确写清：
   - 第几张输入图是知识库参考图。
   - 这张知识库图是什么图。
   - 这张知识库图只用于参考什么。
   - 这张知识库图禁止参考什么。
5. 用户可以在单张九图预览卡片中移除某张 RAG 参考图，且只影响当前这张图，不从项目参考池删除。
6. 生成记录中继续保留每张图实际使用过的 RAG 参考图 ID，方便后续追踪。

## 3. 当前流程说明

当前主要相关文件：

- `backend/app/rag_integration.py`
- `backend/app/main.py`
- `backend/app/db.py`
- `frontend/src/App.jsx`
- `tests/test_rag_integration.py`

当前 RAG 分配逻辑在 `backend/app/rag_integration.py` 中：

- `competitor_fit_reference` 用于第 1 张图：模特上身图。
- `scene_reference`、`color_reference` 用于第 2 张图：场景模特图。
- `pose_reference`、`composition_reference` 用于第 3-6 张图：角度图。
- `pose_reference`、`color_reference` 用于第 7 张图：穿搭图。
- `white_main_reference`、`composition_reference` 用于第 8、9 张图：白底主图、背面白底图。

这个自动分配逻辑可以保留，但必须变成用户可见，并且在提示词中对模型解释清楚。

## 4. 核心方案

采用“三层可见化 + 一层提示词约束”方案。

第一层：项目参考池可见  
用户在 RAG 工作台加入知识库图片后，立刻看到这张图片预计会用于第几张图。

第二层：九图预览可见  
用户点击“预览 9 张提示词”后，每张图卡片显示实际绑定的 RAG 参考图缩略图、用途、说明和输入图编号。

第三层：单图可调整  
用户可以在某张图的预览卡片中移除某张 RAG 参考图。这个操作只影响当前图，不删除项目参考池中的图片。

第四层：提示词可解释  
后端生成提示词时，为每张 RAG 图追加明确说明。例如：

```text
【知识库参考图说明】
除基础参考图外，本次额外提供以下知识库参考图：

图4：知识库参考图 street_style_001.jpg
用途：场景参考、色调参考
这张图是什么：这是一张欧美城市街道中景场景图，背景为干净街区，整体为低饱和暖调，自然侧方光，画面有高级街拍质感。
本图只参考：背景环境、场景氛围、空间关系、色调、光影。
不要参考：人物身份、人物长相、服装款式、品牌、文字、水印、无关道具、无关背景元素。
```

## 5. 后端设计

### 5.1 数据库调整

在 `rag_reference_selections` 表增加字段：

```sql
model_description TEXT DEFAULT ''
```

字段用途：

- 存储“这张图是什么”的说明。
- 该字段会写入最终提示词，因此它是给模型看的，不是内部备注。
- 默认值可以由后端根据 `scene`、`image_type`、`caption`、`metadata` 自动生成。
- 用户可在前端编辑。

不要复用 `notes` 字段，因为 `notes` 更像内部备注，不适合直接写入提示词。

迁移逻辑放在 `backend/app/db.py` 的 `migrate_existing_db()` 中：

- 如果 `rag_reference_selections` 没有 `model_description` 字段，则执行 `ALTER TABLE` 添加。
- 旧数据不需要批量回填，读取时如果为空，由后端动态生成默认说明。

### 5.2 请求模型调整

修改 `backend/app/main.py` 中的 `RagReferenceIn`：

```python
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
    notes: str = ""
```

修改 `RagReferenceUpdateIn`：

```python
class RagReferenceUpdateIn(BaseModel):
    usage_tags: list[str] | None = None
    notes: str | None = None
    sort_order: int | None = None
    model_description: str | None = None
```

新增或调整 `hydrate_rag_reference()`，返回结构中需要包含：

```json
{
  "id": "project_reference_id",
  "rag_image_id": "rag_image_id",
  "filename": "xxx.jpg",
  "scene": "街道",
  "image_type": "竖幅中景",
  "caption": "...",
  "usage_tags": ["scene_reference", "color_reference"],
  "usage_labels": ["场景参考", "色调参考"],
  "metadata": {},
  "model_description": "这是一张...",
  "image_url": "/api/rag/images/xxx",
  "applied_steps": []
}
```

其中 `applied_steps` 由后端根据 `usage_tags` 计算。

### 5.3 用途标签到九图步骤映射

在 `backend/app/rag_integration.py` 中新增固定配置：

```python
STAGE_LABELS = {
    "model_on_body": {"image_no": 1, "title": "模特上身图"},
    "scene_model": {"image_no": 2, "title": "场景模特图"},
    "angle_3": {"image_no": 3, "title": "角度图 1"},
    "angle_4": {"image_no": 4, "title": "角度图 2"},
    "angle_5": {"image_no": 5, "title": "角度图 3"},
    "angle_6": {"image_no": 6, "title": "角度图 4"},
    "outfit": {"image_no": 7, "title": "穿搭图"},
    "white_main": {"image_no": 8, "title": "白底主图"},
    "white_back": {"image_no": 9, "title": "背面白底图"},
}
```

新增函数：

```python
def predicted_steps_for_usage_tags(usage_tags: list[str]) -> list[dict[str, Any]]:
    ...
```

返回示例：

```json
[
  {
    "stage_id": "scene_model",
    "image_no": 2,
    "title": "场景模特图",
    "reason": "场景参考 / 色调参考"
  }
]
```

建议映射规则：

```python
USAGE_TAG_STAGE_MAP = {
    "competitor_fit_reference": ["model_on_body"],
    "scene_reference": ["scene_model"],
    "color_reference": ["scene_model", "outfit"],
    "pose_reference": ["angle_3", "angle_4", "angle_5", "angle_6", "outfit"],
    "composition_reference": ["angle_3", "angle_4", "angle_5", "angle_6", "white_main", "white_back"],
    "white_main_reference": ["white_main", "white_back"],
}
```

注意：

- `predicted_steps_for_usage_tags()` 只负责展示预计用途。
- 真正写入某个 step 的 RAG 引用，仍以 `select_stage_references(stage_id, references)` 为准。
- 两者必须使用同一套映射思想，避免前端显示和后端实际使用不一致。

### 5.4 默认模型说明生成

新增函数：

```python
def build_default_model_description(reference: dict[str, Any]) -> str:
    ...
```

生成优先级：

1. 如果 `reference["model_description"]` 有内容，优先使用。
2. 使用 `metadata.scene_description`。
3. 使用 `reference["scene"]`。
4. 使用 `reference["image_type"]`。
5. 使用 `metadata.visual_style`。
6. 使用 `metadata.color_tone`。
7. 使用 `metadata.lighting`。
8. 使用 `metadata.composition`。
9. 使用 `reference["caption"]`。
10. 使用 `reference["filename"]`。

生成示例：

```text
这是一张欧洲城市街道场景参考图，画面为竖幅中景构图，整体是高级质感的欧美都市街拍风，低饱和暖调色系，明亮柔和侧方自然光。
```

兜底说明：

```text
这是一张知识库参考图，请只参考其已标注用途相关的视觉特征。
```

### 5.5 参考用途说明生成

新增函数：

```python
def allowed_aspects_for_usage_tags(usage_tags: list[str]) -> list[str]:
    ...
```

建议映射：

```python
USAGE_TAG_ALLOWED_ASPECTS = {
    "scene_reference": ["背景环境", "场景氛围", "空间关系"],
    "pose_reference": ["人物姿势", "身体朝向", "动作节奏"],
    "composition_reference": ["构图方式", "画面裁切", "主体位置"],
    "color_reference": ["色调", "光影", "整体氛围"],
    "white_main_reference": ["白底构图", "商品占比", "商业主图呈现方式"],
    "competitor_fit_reference": ["上身松紧度", "穿着方式", "衣长和版型参考"],
}
```

新增固定禁止参考项：

```python
RAG_FORBIDDEN_ASPECTS = [
    "人物身份",
    "人物长相",
    "服装款式",
    "品牌",
    "文字",
    "水印",
    "无关道具",
    "无关背景元素",
]
```

第一版使用统一禁止项即可，不需要为每个用途标签拆不同禁止项。

### 5.6 提示词拼接方式

当前 `enrich_docx_steps_with_rag()` 会直接追加“知识库参考摘要”。

本次改成追加结构化说明块：

```text
【知识库参考图说明】
除基础参考图外，本次额外提供以下知识库参考图：

图4：知识库参考图，文件名 xxx.jpg
用途：场景参考、色调参考
这张图是什么：...
本图只参考：背景环境、场景氛围、空间关系、色调、光影。
不要参考：人物身份、人物长相、服装款式、品牌、文字、水印、无关道具、无关背景元素。
```

关键要求：

- 必须写真实输入图编号。
- 输入图编号根据 `input_refs` 的顺序计算，不能写死。
- 当前基础提示词里已经有“图1、图2、图3”的说明，所以 RAG 图追加到 `input_refs` 后面时，要使用后续编号。
- 例如某 step 原本有 3 张基础输入图，又追加 1 张 RAG 图，则 RAG 图说明为“图4”。

新增函数：

```python
def compose_rag_context_block(input_refs: list[dict[str, str]], rag_refs_by_id: dict[str, dict[str, Any]]) -> str:
    ...
```

新增函数：

```python
def strip_rag_context_block(prompt: str) -> str:
    ...
```

新增函数：

```python
def apply_rag_context_to_prompt(prompt: str, input_refs: list[dict[str, str]], rag_refs_by_id: dict[str, dict[str, Any]]) -> str:
    clean_prompt = strip_rag_context_block(prompt)
    context_block = compose_rag_context_block(input_refs, rag_refs_by_id)
    if not context_block:
        return clean_prompt
    return f"{clean_prompt.rstrip()}\n\n{context_block}"
```

这样可以避免用户保存提示词、多次预览后重复追加知识库说明块。

### 5.7 `enrich_docx_steps_with_rag()` 调整

`enrich_docx_steps_with_rag()` 的职责调整为：

1. 根据当前 step 的 `stage_id` 选择适合的 RAG 参考图。
2. 把选中的 RAG 参考图追加到 `input_refs`。
3. 根据最终 `input_refs` 生成结构化知识库说明块。
4. 把说明块追加到 prompt。

注意：

- 如果某个 step 没有匹配到 RAG 图，不追加说明块。
- 如果 prompt 中已经有旧的 `【知识库参考图说明】`，先移除再追加。
- `input_refs` 中不能重复加入同一张 RAG 图。

### 5.8 Step 返回结构增强

当前 `attach_docx_reference_items()` 已经会给 step 增加 `reference_items`。

需要增强每个 RAG item：

```json
{
  "type": "rag",
  "id": "reference_id",
  "order": 4,
  "input_image_no": 4,
  "label": "xxx.jpg",
  "rag_image_id": "xxx",
  "usage_tags": ["scene_reference"],
  "usage_labels": ["场景参考"],
  "url": "/api/rag/images/xxx",
  "model_description": "这是一张...",
  "rag_summary": "...",
  "allowed_aspects": ["背景环境", "构图方式"],
  "forbidden_aspects": ["人物身份", "品牌", "文字", "水印"],
  "model_instruction": "图4：知识库参考图 xxx.jpg\n用途：场景参考\n这张图是什么：..."
}
```

前端直接使用这个结构展示，不要在前端重新推断。

### 5.9 Step 编辑逻辑

当前 `/api/docx-workflow/steps/{step_id}` 已支持更新 `prompt` 和 `input_refs`。

本次继续复用该接口，但需要调整行为：

1. 如果只更新 `prompt`：
   - 保存用户修改后的基础提示词。
   - 不重复追加知识库块。
2. 如果更新 `input_refs`：
   - 校验 asset、step、rag 是否存在。
   - 保存新的 `input_refs_json`。
   - 重新生成该 step 的知识库说明块。
   - 保留用户基础提示词部分。
3. 如果用户从某张图移除 RAG 参考：
   - 只删除当前 step 的 `{type: "rag", id: "..."}`。
   - 不删除项目参考池中的 RAG 图。
   - 不影响其他 step。

实现建议：

- PATCH step 时，先从当前 prompt 中移除旧知识库块。
- 如果最终 `input_refs` 中仍有 RAG 图，则重新追加新知识库块。
- 如果最终没有 RAG 图，则只保留基础提示词。

## 6. 前端设计

### 6.1 RAG 工作台：项目参考池

在 `RagKnowledgeWorkbench` 的项目参考池卡片中增加三块信息。

第一块：“这张图是什么”

- 使用 textarea。
- 默认显示后端返回的 `model_description`。
- 用户可编辑。
- 失焦或点击保存按钮时 PATCH 到 `/api/projects/{project_id}/rag-references/{reference_id}`。

第二块：“预计用于”

- 使用后端返回的 `applied_steps`。
- 展示格式：

```text
预计用于：
第2张 场景模特图
第7张 穿搭图
```

如果没有用途标签：

```text
预计用于：未分配，请选择用途标签
```

第三块：用途标签

- 保留当前复选框。
- 修改后仍然 PATCH `usage_tags`。
- PATCH 成功后刷新当前 reference，使 `applied_steps` 立即变化。

### 6.2 搜索结果加入项目

从搜索结果点击“加入本项目”时：

- 继续传递原来的字段。
- 新增 `model_description`。
- 如果 RAG 搜索结果中没有该字段，前端传空字符串即可，后端会生成默认说明。

请求示例：

```json
{
  "rag_image_id": "xxx",
  "filename": "xxx.jpg",
  "category": "女装",
  "scene": "欧美街道",
  "image_type": "竖幅中景",
  "caption": "...",
  "score": 0.83,
  "usage_tags": ["scene_reference"],
  "metadata": {},
  "model_description": "",
  "notes": "从知识库工作台加入"
}
```

### 6.3 九图预览卡片

在 `DocxWorkflowPanel` 的每个 step 卡片中，新增“知识库参考”区域。

如果没有 RAG 参考：

```text
知识库参考：无
```

如果有 RAG 参考：

```text
知识库参考：
[缩略图]
图4 street_style_001.jpg
用途：场景参考、色调参考
说明：这是一张欧美城市街道中景图...
[从本图移除]
```

数据来源：

- `step.reference_items`
- 过滤 `type === "rag"`

移除逻辑：

1. 读取当前 step 的 `input_refs`。
2. 删除对应 RAG ref。
3. PATCH `/api/docx-workflow/steps/{step_id}`。
4. body 中传新的 `input_refs` 和当前 textarea 中的 prompt。
5. 用接口返回值更新当前 activeRun 中对应 step。

### 6.4 生成前提醒

当项目参考池中存在 RAG 图，但当前没有 activeRun 时，不建议直接一键生成。

前端行为建议：

- 如果项目参考池为空，保留原有“一键生成 9 张图”行为。
- 如果项目参考池不为空，并且没有 activeRun：
  - “一键生成 9 张图”按钮旁显示提醒：

```text
已加入知识库参考图，请先预览 9 张提示词，确认每张图使用的参考内容。
```

推荐第一版做法：

- 不强制禁用生成按钮。
- 点击生成时，如果没有 activeRun 且项目参考池不为空，则先自动执行 preview，并提示用户确认后再次点击生成。

这样既避免误生成，也不破坏原有流程。

## 7. 提示词示例

以第 2 张“场景模特图”为例。

基础输入图：

- 图1：场景风格参考图。
- 图2：第 1 张生成出的模特上身图。

如果追加一张 RAG 场景参考图，则提示词末尾追加：

```text
【知识库参考图说明】
除基础参考图外，本次额外提供以下知识库参考图：

图3：知识库参考图 street_style_001.jpg
用途：场景参考、色调参考
这张图是什么：这是一张欧美城市街道中景场景图，背景为干净街区，整体为低饱和暖调，自然侧方光，画面有高级街拍质感。
本图只参考：背景环境、场景氛围、空间关系、色调、光影。
不要参考：人物身份、人物长相、服装款式、品牌、文字、水印、无关道具、无关背景元素。
```

重要原则：

- 提示词一定要说“这张图是什么”。
- 提示词一定要说“本图只参考什么”。
- 提示词一定要说“不要参考什么”。
- 不要只写模糊的“参考知识库摘要”。

## 8. 测试要求

### 8.1 后端单元测试

修改或新增 `tests/test_rag_integration.py`。

必须覆盖以下场景：

1. `predicted_steps_for_usage_tags()`
   - `scene_reference` 返回第 2 张。
   - `pose_reference` 返回第 3、4、5、6、7 张。
   - `white_main_reference` 返回第 8、9 张。

2. `build_default_model_description()`
   - 优先使用 `model_description`。
   - 没有 `model_description` 时使用 metadata。
   - 信息为空时返回兜底说明。

3. `allowed_aspects_for_usage_tags()`
   - `scene_reference` 包含“背景环境”。
   - `composition_reference` 包含“构图方式”。
   - 多个 tag 时去重并保持稳定顺序。

4. `compose_rag_context_block()`
   - 能生成正确的“图N”。
   - 包含“这张图是什么”。
   - 包含“本图只参考”。
   - 包含“不要参考”。

5. `strip_rag_context_block()`
   - 能删除旧知识库说明块。
   - 不影响基础提示词。

6. `enrich_docx_steps_with_rag()`
   - 能把 RAG ref 写入 `input_refs`。
   - 能把说明块写入 prompt。
   - 多次执行不会重复追加说明块。

### 8.2 后端接口测试

需要手动验证：

1. `GET /api/projects/{project_id}/rag-references`
   - 返回 `model_description`。
   - 返回 `applied_steps`。

2. `PATCH /api/projects/{project_id}/rag-references/{reference_id}`
   - 可以更新 `model_description`。
   - 可以更新 `usage_tags`。
   - 更新 `usage_tags` 后 `applied_steps` 变化。

3. `GET /api/docx-workflow/runs/{run_id}`
   - 每个 step 返回增强后的 `reference_items`。
   - RAG item 中包含 `input_image_no`、`model_description`、`allowed_aspects`、`model_instruction`。

4. `PATCH /api/docx-workflow/steps/{step_id}`
   - 移除某个 RAG ref 后，该 step prompt 中对应说明块更新。
   - 不影响其他 step。

### 8.3 前端手动测试

启动服务后，在 `http://192.168.0.186:8021/workbench/` 验证：

1. 加入一张知识库图片到项目参考池。
2. 勾选“场景参考”。
3. 页面显示预计用于“第2张 场景模特图”。
4. 编辑“这张图是什么”，保存后刷新不丢失。
5. 点击“预览 9 张提示词”。
6. 第 2 张图卡片显示该 RAG 图缩略图。
7. 第 2 张提示词中出现 `【知识库参考图说明】`。
8. 提示词中出现“图N：知识库参考图”。
9. 提示词中出现“这张图是什么”。
10. 提示词中出现“本图只参考”和“不要参考”。
11. 点击“从本图移除”，该图从当前 step 的知识库参考中消失。
12. 再保存提示词，不会重复出现多个知识库说明块。

## 9. 验收标准

完成后必须满足：

1. 用户在项目参考池中能看懂每张 RAG 图会影响哪几张图。
2. 用户在九图预览中能看懂每张图实际用了哪些 RAG 图。
3. 每张 RAG 图都有“这张图是什么”的说明。
4. 提示词中能明确告诉模型：
   - 第几张输入图是知识库参考图。
   - 这张图是什么。
   - 只参考什么。
   - 不参考什么。
5. 移除单张图的 RAG 参考后，只影响当前图，不删除项目参考池。
6. 每张生成结果的 `params_json.reference_rag_ids` 仍能记录实际使用的 RAG 图。
7. 不修改 `D:\RAG` 服务。
8. 不破坏原有九图生成流程。
9. 不破坏当前 RAG 搜索、加入项目参考池、生成九图、单图重生能力。

## 10. 实施注意事项

1. 当前工作区可能存在未提交改动，开发前必须先查看 `git status`，不要回滚别人已有改动。
2. 不要修改 `D:\RAG`。
3. 不要重写整个前端，只在现有 `RagKnowledgeWorkbench` 和 `DocxWorkflowPanel` 上增量修改。
4. 不要改变现有九图核心顺序和基础提示词结构。
5. 不要让前端自己推断复杂映射，映射结果和模型说明应由后端返回。
6. 所有提示词说明块必须由后端生成，保证全量生成和单张重生一致。
7. 修改后需要重新构建前端，并更新 `backend/app/static/` 中的静态产物。
