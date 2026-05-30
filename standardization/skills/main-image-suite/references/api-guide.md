# 商品九图生成 MCP 使用说明

## 服务划分

| MCP | 职责 |
|---|---|
| 主图生成任务 MCP | 项目创建、素材上传、九图初始化、生成、查询、单图重生成、套图下载和项目参考图管理 |
| 图片知识库 MCP | 参考图检索、相似图检索、优秀图片入库、记录列表、图片地址和健康检查 |

## 主图生成任务 MCP

### `create_main_image_project`

创建项目。至少提供 `sku`。

### `upload_project_assets`

上传项目素材。图片必须使用绝对路径。

主要参数：

| 参数 | 说明 |
|---|---|
| `project_id` | 项目编号 |
| `asset_type` | `product`、`model` 或 `competitor` |
| `file_paths` | 一个或多个图片绝对路径 |
| `slot` | 可选，素材用途 |

### `initialize_nine_image_workflow`

初始化固定九图方案。

主要参数：

| 参数 | 说明 |
|---|---|
| `project_id` | 项目编号 |
| `product_name` | 商品名称 |
| `material` | 商品材质 |
| `product_asset_id` | 产品图素材编号 |
| `accessory_asset_id` | 穿搭配饰素材编号 |
| `model_asset_id` | 可选，模特参考素材编号 |
| `fit_front_asset_id` | 可选，正面上身参考素材编号 |
| `fit_side_asset_id` | 可选，侧面上身参考素材编号 |
| `fit_back_asset_id` | 可选，背面上身参考素材编号 |
| `scene_asset_id` | 可选，场景参考素材编号 |

### `generate_nine_image_suite`

启动完整九图后台生成任务。

### `get_nine_image_workflow`

查看九张图的生成状态和结果。

### `regenerate_nine_image_step`

根据步骤编号重新生成单张图片。

### `download_nine_image_suite`

下载完整套图 ZIP 文件。保存路径必须为绝对路径。

### `search_rag_references`

通过主图服务代理检索知识库候选图。

### `add_rag_reference_to_project`

将候选图片作为项目参考图保存。

### `copy_rag_reference_to_project_asset`

将知识库图片复制到项目素材中。

## 图片知识库 MCP

### `search_knowledge_images`

使用自然语言检索参考图，可使用 `filters` 缩小范围。

### `search_knowledge_images_by_image`

使用一张本机图片和可选文字检索相似参考图。图片必须使用绝对路径。

### `add_knowledge_image`

将经过业务确认的优秀图片加入知识库。图片必须使用绝对路径。

### `list_knowledge_records`

分页查看知识库记录。

### `get_knowledge_image_url`

获取指定图片的 HTTP 地址。

### `get_knowledge_base_health`

查询知识库服务状态。

## 本机启动

```powershell
.\standardization\mcp-server\start_main_image_stdio.ps1
.\standardization\mcp-server\start_rag_stdio.ps1
```

本机 MCP 客户端配置可参考：

```text
standardization/mcp-server/client-config.example.json
```

## HTTP MCP 启动

```powershell
.\standardization\mcp-server\start_main_image_http.ps1
.\standardization\mcp-server\start_rag_http.ps1
```

默认地址：

```text
http://127.0.0.1:8767/mcp
http://127.0.0.1:8768/mcp
```

## 主图服务启动建议

现有 RAG 服务已使用 `8010`，因此主图生成服务建议使用 `8020`：

```powershell
$env:PORT = "8020"
python .\run_backend.py
```
