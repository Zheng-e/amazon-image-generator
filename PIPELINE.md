# 亚马逊服装商品图自动化流水线

## 运行方式

默认运行完整流程：

```powershell
python .\generate.py
```

常用参数：

```powershell
python .\generate.py --skip-competitors
python .\generate.py --keywords "women double lined camisole tank top" "women adjustable strap cami tank top"
python .\generate.py --asins B0XXXXXXXX B0YYYYYYYY
python .\generate.py --max-revisions 2
python .\generate.py --no-generate --skip-competitors
```

## 流程

1. 读取当前目录中的 SKU xlsx，自动跳过 Excel 临时文件 `~$*.xlsx`。
2. 轻量采集 Amazon 公开竞品图，缓存来源 URL、排名、图片 URL 和本地图片。
3. 调用 Gemini 抽象出类目视觉规范，输出 `output/_playbooks/<category>_category_playbook.json`。
4. 从 `asset_library.json` 选择场景、卖点和模特动作，输出每个 SKU 的 `output/_briefs/<SKU>/image_briefs.json`。
5. Gemini 改写每张图的最终提示词，保存到 `output/_prompts/<SKU>/`。
6. 生图模型生成候选图，Gemini 质检；不达标时按 QA 问题自动返工。
7. 每个 SKU 输出最终图、候选图、`qa_report.md` 和 `qa_report.json`。

## V1 规则

- 第 1 张主图：白底、商品占比 85-100%、不能是全身模特、不能有文字/道具/场景。
- 非主图：默认真实生活场景，例如卧室、衣帽间、穿衣镜、街景、咖啡店外、通勤/叠穿场景。
- 技术图：可以商品-only，但也放在真实家居/衣帽间/面料护理台场景中，避免纯色棚拍。
- 竞品图只用于抽象类目视觉规范，不直接复制竞品图、品牌、文字或构图。
