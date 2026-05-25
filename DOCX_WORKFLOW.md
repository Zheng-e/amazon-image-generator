# DOCX 固定九图自动化生图流程

亚马逊服装商品主图生成工具，基于 FastAPI + React 构建，通过固定的 9 步工作流自动生成一套完整的商品图。

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+（仅前端开发需要）

### 安装依赖

```powershell
pip install -r requirements.txt
```

### 配置 API 密钥

在项目根目录创建 `api.txt`，格式如下（模型名 + 对应的 API 密钥，每行一个）：

```
gpt-image-2-client
sk-xxxxxxxxxxxxxxxx
sk-yyyyyyyyyyyyyyyy
```

如需使用文字模型（分析功能），创建 `api key.txt`，格式相同。

### 启动服务

```powershell
$env:PORT='8010'; python .\run_backend.py
```

浏览器访问 `http://localhost:8010/workbench/`

局域网内其他电脑访问 `http://<你的IP>:8010/workbench/`（需放行防火墙端口）

## 项目结构

```
├── backend/
│   └── app/
│       ├── main.py              # FastAPI 应用（API 端点）
│       ├── ai_clients.py        # AI API 调用封装（图片生成、文字分析）
│       ├── db.py                # SQLite 数据库层
│       ├── docx_workflow.py     # 九图工作流定义（提示词、步骤、风格）
│       └── static/index.html    # 预构建的前端页面
├── frontend/                    # React 前端源码
│   ├── src/App.jsx              # 主应用组件
│   ├── src/styles.css           # 样式
│   └── package.json             # Node 依赖
├── run_backend.py               # 启动脚本
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
└── api.txt                      # API 密钥（不提交到 git）
```

## 九图工作流

每张图按固定顺序生成，后续步骤可依赖前序步骤的输出作为参考图。

| 序号 | 阶段 | 说明 | 参考图来源 |
|------|------|------|------------|
| 1 | 模特上身图 | 生成模特穿着产品的正面/侧面/背面三视图 | 产品图 + 模特参考图 + 上身效果参考图 |
| 2 | 场景模特图 | 将模特融入场景背景 | 场景风格参考图 + 第1步输出 |
| 3-6 | 正侧背角度图 | 生成不同角度的流行拍照姿势 | 第2步输出 + 第1步输出 |
| 7 | 穿搭图 | 搭配不同道具和服装的变体 | 第2步输出 |
| 8 | 白底主图 | 亚马逊规范的纯白底正面主图 | 第1步输出 + 产品图 |
| 9 | 背面白底图 | 亚马逊规范的纯白底背面/侧背图 | 第1步输出 + 产品图 |

### 执行策略

- 第 1 步：顺序执行（无依赖）
- 第 2 步：顺序执行（依赖第 1 步）
- 第 3-9 步：并行执行（最多 7 个线程）

### 风格选项

系统内置 3 种摄影风格，影响所有图片的色调、光影和质感：

| 风格 | 说明 |
|------|------|
| `natural_fashion` | 裸妆感·高级时尚自然（默认） |
| `cinematic_documentary` | 电影感·硬朗纪实风格 |
| `street_film` | 街头抓拍·胶片质感 |

## API 端点

### 项目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects` | 项目列表（支持 SKU 搜索） |
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects/{id}` | 项目详情（含素材和工作流） |
| DELETE | `/api/projects/{id}` | 删除项目 |

### 素材管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/assets` | 上传素材（支持多文件） |
| DELETE | `/api/assets/{id}` | 删除素材 |
| PATCH | `/api/assets/{id}` | 更新素材信息 |

### DOCX 工作流

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/docx-workflow/styles` | 获取风格选项列表 |
| POST | `/api/docx-workflow/runs` | 创建工作流（传入产品名、材质、4张参考图） |
| GET | `/api/docx-workflow/runs/{id}` | 获取工作流详情和所有步骤 |
| POST | `/api/docx-workflow/runs/{id}/generate` | 一键生成全部 9 张图 |
| GET | `/api/docx-workflow/runs/{id}/download` | 打包下载 9 张图（ZIP） |
| PATCH | `/api/docx-workflow/steps/{id}` | 修改单步提示词或参考图 |
| POST | `/api/docx-workflow/steps/{id}/generate` | 重新生成单张图 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/models/image` | 可用图片模型列表 |
| GET | `/api/models/analysis` | 可用分析模型列表 |

## 数据存储

- 数据库：`output/workbench/design_workbench.db`（SQLite）
- 上传素材：`output/workbench/projects/{project_id}/`
- 生成图片：`output/workbench/projects/{project_id}/docx_workflow/{run_id}/`

## 前端开发

```powershell
cd frontend
npm install
npm run dev
```

开发服务器运行在 `http://localhost:5173`，会代理 API 请求到后端。

构建生产版本：

```powershell
npm run build
```

构建产物需手动复制到 `backend/app/static/` 目录。
