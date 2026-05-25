# 设计部主图生成字段实验台

这是一个本地主图生成实验台，用于让设计部配置 `OUTPUT-A/C/D` 字段、手动上传素材、分析竞品图、生成单张图片实验，并沉淀知识库候选。

## 启动

### 后端

```powershell
python -m pip install -r requirements.txt
python .\run_backend.py
```

后端数据会保存到：

```text
output/workbench/design_workbench.db
output/workbench/projects/
```

API 配置优先读取环境变量；如果没有环境变量，会兼容读取当前目录的 `api.txt`。

后端自带一个无需 npm 的轻量工作台页面：

```text
http://localhost:8010/workbench
```

### 前端

React/Vite 源码在 `frontend/`。当前机器能找到 `node`，但没有 `npm` 命令。安装 npm 后运行：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开：

```text
http://localhost:5173
```

## 第一版流程

1. 创建项目：填写 SKU、品类、项目名称。
2. 上传素材：商品参考图、模特参考图、竞品图均为手动上传。
3. 配置字段：在字段配置器里调整 `OUTPUT-A`、`OUTPUT-C`、`OUTPUT-D`。
4. 填写 `OUTPUT-A`：保存后会冻结当前字段 schema 快照。
5. 逐图分析竞品：选择竞品图，生成 `OUTPUT-C`，人工确认。
6. 汇总类目规范：选择已确认的 `OUTPUT-C`，生成 `OUTPUT-D`，人工确认。
7. 单张生图实验：选择参考图、竞品分析和补充信息，生成 prompt，再调用 Image2。
8. 标记优秀结果：把效果好的生图结果标记为知识库候选。

## 关键约束

- 不使用 Excel 作为主流程入口。
- 不联网爬取竞品图。
- `OUTPUT-C` 是单张竞品图结构分析。
- `OUTPUT-D` 是多张竞品图汇总出的类目视觉规范。
- 生图默认只把商品图和模特图传给 Image2；竞品图只通过结构化分析结果进入提示词，避免复刻竞品。
