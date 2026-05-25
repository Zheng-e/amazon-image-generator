# 亚马逊服装商品图生成 SOP

## 0. SOP说明

### SOP定义

SOP 是 Standard Operating Procedure，即标准作业流程。

在本项目中，SOP 用来规定“亚马逊服装商品图从输入、竞品研究、图片策划、生图、质检、人工终审、批量改色到知识库沉淀”的完整操作标准，确保不同人员、不同 SKU、不同批次都能按同一套流程产出稳定、可复用、接近亚马逊 Listing 风格的商品图片。

### 适用范围

- 适用品类：女装上衣内搭，包括背心、吊带、T 恤、打底衫等。
- 适用图片：亚马逊 Listing 主图和副图。
- 适用流程：基础色套图生成，以及基础色套图通过后进行批量改色。
- 不适用范围：直接复制竞品图片、绕过平台限制采集图片、无人审核直接上架。

### 角色分工

- 研发：负责流程搭建、工具维护、API 调用、爬虫合规控制、异常排查、自动质检规则维护。
- 运营：负责商品事实输入、竞品图确认、图片计划确认、最终图片终审、知识库维护。
- AI：负责竞品图片结构分析、图片计划建议、提示词生成、初步质检、返工建议生成。

### 核心原则

- 只抽象竞品图片风格和结构，不复制竞品图片构图、模特、场景或素材。
- 主图必须优先满足亚马逊规则：纯白背景、商品占比 85-100%、无文字、无水印、无道具、不可全身模特。
- 副图应符合亚马逊服装类目风格：真实生活场景、自然模特动作、清晰展示卖点，避免淘宝或拼多多式海报风格。
- 图片数量和每张图内容不固定，由 AI 建议、运营确认。
- 通过终审的图片结构、场景、卖点、提示词和质检结论都要沉淀进知识库。

### 标准输出目录示例

```text
FS03767/
  00_input/
    FS03767.xlsx
    reference_front.png
    reference_model_01.png
  01_competitor/
    selected_images/
    competitor_summary.json
  02_plan/
    image_plan_ai.json
    image_plan_confirmed.json
  03_prompts/
    final_prompts.json
  04_candidates/
    image_01_main/
    image_02_detail/
  05_final_base/
    01_main.png
    02_fabric_detail.png
    03_support_feature.png
  06_recolor_input/
    FS03767.txt
    base_images/
  07_recolor_output/
    Black/
    White/
    Pink/
  qa_report.md
  knowledge_update.md
```

### 示例

```text
SKU：FS03767
品类：女装双层支撑背心
基础色：Black
目标：先生成一套符合亚马逊风格的黑色基础套图，运营终审通过后，再批量改成 White、Pink、Army Green。
```

## 1. 输入商品事实

### 引用上一步输出

- 本阶段为流程起点，无上一步输出。

### 数据源/外部输入

- SKU xlsx 表格。
- 商品参考图。
- 模特参考图。
- 类目。
- 关键词或 ASIN 列表。
- 基础色。
- 需要改色的目标颜色清单。

### 处理动作

- 运营整理商品事实字段。
- 研发或脚本读取 xlsx 中的商品信息。
- AI 将非结构化描述整理成标准商品事实。
- 对缺失字段做标记，交由运营补充。

### 本阶段输出

`OUTPUT-A｜商品事实字段`

建议字段：

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| sku | 商品编号 | FS03767 |
| category | 类目 | 女装背心 |
| product_type | 细分品类 | 双层支撑背心 |
| base_color | 基础色 | Black |
| target_colors | 改色目标色 | White, Pink, Army Green |
| fabric | 面料 | 双层弹力面料 |
| neckline | 领口 | 圆领 |
| strap | 肩带 | 宽肩带 |
| fit | 版型 | 修身 |
| key_selling_points | 核心卖点 | 支撑包覆、防透、可叠穿 |
| reference_images | 参考图 | 商品平铺图、模特图 |

### 示例

```json
{
  "sku": "FS03767",
  "category": "女装上衣内搭",
  "product_type": "双层支撑背心",
  "base_color": "Black",
  "target_colors": ["White", "Pink", "Army Green"],
  "fabric": "双层弹力面料",
  "neckline": "圆领",
  "strap": "宽肩带",
  "fit": "修身短款",
  "key_selling_points": ["支撑胸部", "防透", "可外穿", "可叠穿"]
}
```

## 2. 采集并确认竞品图

### 引用上一步输出

- `OUTPUT-A｜商品事实字段`

### 数据源/外部输入

- 亚马逊关键词搜索结果。
- 亚马逊 ASIN 页面图片。
- 运营提供的竞品链接。

### 处理动作

- 按关键词或 ASIN 轻量采集竞品图片。
- 不绕过登录、验证码或平台限制。
- 保存图片来源 URL、排名、采集时间、关键词。
- AI 初筛明显无关图片。
- 运营人工确认可用于风格分析的竞品图，建议每个细分品类确认约 20 张。

### 本阶段输出

`OUTPUT-B｜竞品确认图集`

每张图应包含：

- 图片文件。
- 来源 URL。
- 关键词或 ASIN。
- 图片位置，如主图、第 2 张、第 3 张。
- 运营确认状态。

### 示例

```json
{
  "category": "women tank top with built in bra",
  "confirmed_count": 20,
  "images": [
    {
      "file": "competitor_001_main.jpg",
      "source_url": "https://www.amazon.com/example-asin",
      "rank": 1,
      "slot": "main_image",
      "confirmed_by_operator": true
    }
  ]
}
```

## 3. AI分析竞品图片结构

### 引用上一步输出

- `OUTPUT-B｜竞品确认图集`

### 数据源/外部输入

- 已确认竞品图片。
- 图片来源信息。
- 商品类目。

### 处理动作

- AI 只分析图片结构和风格规律，不生成“照着某张图做”的模仿指令。
- 分析主图构图、裁切、商品占比、模特是否出现、背景规范。
- 分析副图类型、场景、模特动作、卖点表达、常见裁切比例。
- 提取亚马逊风格共性，过滤淘宝、拼多多式海报特征。

### 本阶段输出

`OUTPUT-C｜竞品图片结构摘要`

`OUTPUT-D｜类目视觉规范`

### 示例

```json
{
  "main_image_rules": {
    "background": "pure white",
    "crop": "upper body crop or product-only crop",
    "product_area": "85-100%",
    "forbidden": ["full body model", "text", "props", "scene background", "watermark"]
  },
  "secondary_image_patterns": [
    "fabric close-up",
    "built-in support feature",
    "front and back try-on",
    "anti-see-through comparison",
    "layering scene",
    "size and fit reference"
  ],
  "amazon_style_notes": [
    "clean catalog photography",
    "natural model pose",
    "realistic lifestyle scene",
    "no poster-style large Chinese text",
    "no exaggerated e-commerce collage"
  ]
}
```

## 4. 检索类目/场景/卖点/图片槽位知识库

### 引用上一步输出

- `OUTPUT-A｜商品事实字段`
- `OUTPUT-C｜竞品图片结构摘要`
- `OUTPUT-D｜类目视觉规范`

### 数据源/外部输入

- 类目视觉规范库。
- 场景库。
- 卖点库。
- 模特/姿势库。
- 图片槽位知识库。
- 过往成功案例和失败案例。

### 处理动作

- 按类目和细分品类检索已有知识。
- 按商品卖点匹配可用图片槽位。
- 按基础色和服装风格匹配适合的场景。
- 过滤不适合亚马逊风格的场景和构图。

### 本阶段输出

`OUTPUT-E｜知识库检索结果`

### 知识库内容建议

| 知识库 | 内容 | 示例 |
| --- | --- | --- |
| 类目视觉规范库 | 主图规则、副图结构、禁忌项 | 女装背心主图不可全身模特 |
| 场景库 | 卧室、衣帽间、街景、咖啡店外、通勤、运动休闲 | 衣帽间镜前整理肩带 |
| 卖点库 | 防透、双层面料、支撑包覆、叠穿、尺码参考 | 双层支撑适合无内衣穿着 |
| 模特/姿势库 | 半身、侧身、背面、走动、整理肩带、穿外套 | 街边行走展示叠穿 |
| 图片槽位库 | 每张图的内容类型和适用条件 | 防透对比图适合白色/浅色款 |

### 示例

```json
{
  "matched_slots": [
    {
      "slot_name": "main_white_background",
      "required": true,
      "scene": "pure white background",
      "model_crop": "upper torso only"
    },
    {
      "slot_name": "support_feature_try_on",
      "required": true,
      "scene": "bright bedroom or walk-in closet",
      "pose": "model gently adjusts strap, upper body crop"
    },
    {
      "slot_name": "layering_lifestyle",
      "required": false,
      "scene": "coffee shop exterior or city street",
      "pose": "model walking with open shirt layered over tank"
    }
  ]
}
```

## 5. 生成动态图片计划

### 引用上一步输出

- `OUTPUT-A｜商品事实字段`
- `OUTPUT-D｜类目视觉规范`
- `OUTPUT-E｜知识库检索结果`

### 数据源/外部输入

- 商品事实字段。
- 类目规范。
- 图片槽位知识库。
- 竞品结构摘要。

### 处理动作

- AI 根据商品特性建议图片数量和每张图内容。
- 主图固定为必选。
- 副图数量不固定，由卖点复杂度、颜色、款式和运营目标决定。
- 每张图都要说明：图片目的、场景、构图、模特动作、展示卖点、是否允许文字、质检重点。

### 本阶段输出

`OUTPUT-F｜AI建议图片计划`

### 示例

```json
{
  "sku": "FS03767",
  "recommended_image_count": 7,
  "images": [
    {
      "image_no": 1,
      "type": "main",
      "purpose": "亚马逊主图",
      "scene": "pure white background",
      "composition": "upper torso crop, tank top fills 85-100% of frame",
      "model_action": "neutral natural posture, no full body",
      "text_allowed": false,
      "qa_focus": ["white background", "product ratio", "no full-body model"]
    },
    {
      "image_no": 2,
      "type": "secondary",
      "purpose": "展示支撑包覆",
      "scene": "bright walk-in closet",
      "composition": "waist-up try-on",
      "model_action": "adjusting shoulder strap naturally",
      "text_allowed": false,
      "qa_focus": ["support structure visible", "realistic home scene"]
    },
    {
      "image_no": 3,
      "type": "secondary",
      "purpose": "展示面料细节",
      "scene": "close-up fabric detail",
      "composition": "macro crop of fabric, neckline and seam",
      "model_action": "no face, close crop",
      "text_allowed": false,
      "qa_focus": ["fabric texture", "seam accuracy"]
    }
  ]
}
```

## 6. 运营确认图片计划

### 引用上一步输出

- `OUTPUT-F｜AI建议图片计划`

### 数据源/外部输入

- AI 建议图片计划。
- 运营推广重点。
- 商品实际上架需求。

### 处理动作

- 运营确认图片数量。
- 运营确认每张图的卖点和场景。
- 删除不必要图片。
- 增加必须图片。
- 标记重点图和可返工图。

### 本阶段输出

`OUTPUT-G｜运营确认图片计划`

### 示例

```json
{
  "sku": "FS03767",
  "confirmed_image_count": 7,
  "operator_notes": [
    "第 2 张必须突出支撑胸部，不要只像普通背心",
    "第 5 张增加街景叠穿，体现可外穿",
    "不要出现中文大字或促销海报风格"
  ],
  "approved": true
}
```

## 7. 生成提示词并生图

### 引用上一步输出

- `OUTPUT-G｜运营确认图片计划`

### 数据源/外部输入

- 商品参考图。
- 模特参考图。
- 运营确认图片计划。
- 类目视觉规范。
- 生图模型参数。

### 处理动作

- AI 将每张图的计划扩写成生图提示词。
- 主图提示词必须强调亚马逊规则。
- 副图提示词必须强调真实生活场景和自然动作。
- 对同一 SKU 的真人图增加姿势变化，避免全部复用参考图姿势。
- 使用参考图约束服装颜色、肩带、领口、衣长、下摆和面料纹理。

### 本阶段输出

`OUTPUT-H｜最终生图提示词`

`OUTPUT-I｜候选图片`

### 主图提示词示例

```text
Create an Amazon-compliant main product image for a women's built-in support tank top.
Use a pure white background. Show only upper torso or product-focused crop, not a full-body model.
The tank top must occupy 85-100% of the image area.
No text, no logo, no watermark, no props, no lifestyle scene.
Keep the garment consistent with the reference image: round neckline, wide straps, fitted cropped length, double-layer fabric, black color.
Clean catalog photography, realistic fabric texture, sharp edges, natural lighting.
```

### 副图提示词示例

```text
Create an Amazon secondary listing image for a women's built-in support tank top.
Scene: bright walk-in closet at home, realistic lifestyle photography.
The adult model is shown from waist up, naturally adjusting one shoulder strap to demonstrate support and secure fit.
Keep the garment consistent with the reference image: round neckline, wide straps, fitted cropped length, double-layer black fabric.
No poster layout, no large text, no collage, no Taobao-style promotional design.
The image should feel like clean Amazon apparel listing photography.
```

## 8. AI质检与自动返工

### 引用上一步输出

- `OUTPUT-I｜候选图片`
- `OUTPUT-G｜运营确认图片计划`
- `OUTPUT-D｜类目视觉规范`

### 数据源/外部输入

- 候选图片。
- 每张图的图片计划。
- 质检规则。

### 处理动作

- AI 对每张候选图打分。
- 主图低于硬性规则直接返工。
- 副图检查是否真实场景、是否亚马逊风格、是否商品一致、是否姿势重复。
- 对不合格图片生成返工提示词并重跑。
- 保存每次返工原因。

### 本阶段输出

`OUTPUT-J｜AI质检报告`

### 质检标准

| 检查项 | 主图要求 | 副图要求 |
| --- | --- | --- |
| 背景 | 纯白 | 真实生活场景优先 |
| 商品占比 | 85-100% | 按图片目的决定 |
| 模特裁切 | 不可全身 | 可半身、全身、背面、侧身、走动 |
| 文字 | 不允许 | 默认不允许，特殊说明才允许 |
| 风格 | 亚马逊目录图 | 亚马逊生活方式图 |
| 商品一致性 | 必须一致 | 必须一致 |
| 禁止项 | 水印、Logo、道具、场景、全身模特 | 淘宝海报风、拼多多拼贴风、错误文字、水印 |

### 示例

```markdown
FS03767 - image_01_main

- 总分：72/100
- 结果：不通过，必须返工
- 问题：
  - 模特为全身图，不符合主图要求
  - 商品占比约 45%，低于 85%
  - 背景虽然接近白色，但有地面阴影和场景感
- 返工方向：
  - 改为上半身裁切
  - 强调 tank top fills 85-100% of frame
  - 强调 pure white background, no floor, no scene
```

## 9. 运营终审基础套图

### 引用上一步输出

- `OUTPUT-I｜候选图片`
- `OUTPUT-J｜AI质检报告`

### 数据源/外部输入

- AI 质检通过图片。
- 运营审美判断。
- 上架平台要求。

### 处理动作

- 运营逐张确认是否可用于 Listing。
- 标记通过、返工、废弃。
- 确认基础色最终套图。
- 基础色套图通过后，才能进入批量改色阶段。

### 本阶段输出

`OUTPUT-K｜运营终审套图`

### 示例

```json
{
  "sku": "FS03767",
  "base_color": "Black",
  "final_images": [
    "01_main.png",
    "02_support_feature.png",
    "03_fabric_detail.png",
    "04_back_view.png",
    "05_layering_street.png",
    "06_anti_see_through.png",
    "07_size_reference.png"
  ],
  "operator_approved": true,
  "next_step": "batch_recolor"
}
```

## 10. 批量改色

### 引用上一步输出

- `OUTPUT-K｜运营终审套图`

### 数据源/外部输入

- 基础色最终套图文件夹。
- 标准颜色 TXT。
- 现有改色项目：`D:\AI改色-v2`
- Web 工作台地址：`http://192.168.0.186/`

### 处理动作

- 运营或设计将基础色最终套图整理为一个商品文件夹。
- 商品文件夹建议用 SKU 命名。
- 准备标准颜色 TXT 文件。
- 打开改色 Web 工作台。
- 上传商品图片文件夹。
- 上传颜色 TXT。
- 选择默认改色引擎。
- 提交改色任务。
- 等待任务完成后下载 ZIP。

### 本阶段输出

`OUTPUT-L｜批量改色输入包`

`OUTPUT-M｜改色后颜色变体套图`

### 批量改色输入包示例

```text
FS03767/
  01_main.png
  02_support_feature.png
  03_fabric_detail.png
  04_back_view.png
  05_layering_street.png
  06_anti_see_through.png
  07_size_reference.png
  FS03767.txt
```

### 标准颜色 TXT 示例

```text
GARMENT: 女装双层支撑圆领背心
COLORS:
White: #f2f2f2
Pink: #e271a5
Army Green: #65634a
```

### Web 工作台操作示例

```text
1. 打开 http://192.168.0.186/
2. 选择商品图片文件夹：FS03767
3. 选择颜色定义 TXT：FS03767.txt
4. 改色引擎保持默认
5. 点击开始改色
6. 在任务进度中查看状态
7. 完成后下载结果 ZIP
```

### 改色注意事项

- 只有运营终审通过的基础套图才能进入改色。
- 每张基础图都要参与改色，保证每个颜色拥有完整 Listing 套图。
- 颜色值必须是 6 位 HEX，例如 `#f2f2f2`。
- 不使用 RGB、CMYK、Pantone 或中文描述替代 HEX。
- TXT 中必须包含 `COLORS:`。
- 改色时应保持模特、背景、姿势、构图、光线和服装结构不变，只改变目标服装颜色。

## 11. 改色图质检

### 引用上一步输出

- `OUTPUT-M｜改色后颜色变体套图`
- `OUTPUT-K｜运营终审套图`
- 标准颜色 TXT

### 数据源/外部输入

- 改色输出图。
- 基础色终审图。
- 目标 HEX 色号。

### 处理动作

- 检查每个颜色是否生成完整套图。
- 检查图片数量是否等于“基础图数量 × 目标颜色数量”。
- 检查是否只改变服装颜色。
- 检查模特、背景、姿势、构图、卖点表达是否保持不变。
- 检查目标颜色是否接近 HEX 色号。
- 标记需要重跑的颜色或图片。

### 本阶段输出

`OUTPUT-M｜改色后颜色变体套图`

`OUTPUT-J｜改色质检报告`

### 示例

```markdown
FS03767 改色质检

- 基础图数量：7
- 目标颜色数量：3
- 预计输出：21 张
- 实际输出：21 张
- 结果：通过

White #f2f2f2
- 7/7 张完整生成
- 主图背景保持纯白
- 服装颜色接近目标色
- 未发现模特脸部、背景、姿势变化

Pink #e271a5
- 7/7 张完整生成
- 第 3 张面料细节偏亮，建议人工确认

Army Green #65634a
- 7/7 张完整生成
- 通过
```

## 12. 最终交付与知识库更新

### 引用上一步输出

- `OUTPUT-K｜运营终审套图`
- `OUTPUT-M｜改色后颜色变体套图`
- `OUTPUT-J｜AI质检报告`
- `OUTPUT-J｜改色质检报告`

### 数据源/外部输入

- 基础色终审图片。
- 改色后图片。
- 图片计划。
- 最终提示词。
- 质检报告。
- 运营终审意见。

### 处理动作

- 整理最终交付目录。
- 每个颜色单独成套保存。
- 保存图片计划、提示词、质检报告和终审结论。
- 将通过终审的图片槽位、场景、卖点、提示词结构写入知识库。
- 将失败案例和返工原因也写入知识库，避免重复踩坑。

### 本阶段输出

`OUTPUT-N｜知识库更新项`

最终交付图：

- 基础色套图。
- 每个目标颜色的完整改色套图。
- 质检报告。
- 提示词记录。
- 知识库更新记录。

### 知识库更新示例

```json
{
  "category": "女装上衣内搭",
  "sub_category": "双层支撑背心",
  "slot_name": "support_feature_try_on",
  "scene": "bright walk-in closet",
  "pose": "model adjusting shoulder strap",
  "selling_points": ["built-in support", "secure fit"],
  "passed_cases": ["FS03767_02_support_feature.png"],
  "failed_cases": [
    {
      "case": "full body main image",
      "reason": "主图商品占比不足，且出现全身模特",
      "avoidance": "主图必须使用上半身或商品特写裁切"
    }
  ],
  "prompt_pattern": "Amazon secondary apparel image, realistic home scene, waist-up model crop, natural strap-adjusting pose..."
}
```

## 13. 数据流串联索引

### OUTPUT-A｜商品事实字段

- 来源：SKU xlsx、商品参考图、运营输入。
- 去向：竞品采集、知识库检索、图片计划、生图提示词。

### OUTPUT-B｜竞品确认图集

- 来源：轻量采集和运营确认。
- 去向：AI 分析竞品图片结构。

### OUTPUT-C｜竞品图片结构摘要

- 来源：AI 分析竞品确认图集。
- 去向：类目视觉规范、动态图片计划。

### OUTPUT-D｜类目视觉规范

- 来源：竞品结构摘要、亚马逊图片规则、知识库。
- 去向：图片计划、生图提示词、AI 质检。

### OUTPUT-E｜知识库检索结果

- 来源：类目视觉规范库、场景库、卖点库、模特/姿势库、图片槽位库。
- 去向：动态图片计划。

### OUTPUT-F｜AI建议图片计划

- 来源：商品事实、类目规范、知识库检索结果。
- 去向：运营确认。

### OUTPUT-G｜运营确认图片计划

- 来源：运营对 AI 建议图片计划的确认。
- 去向：提示词生成和生图。

### OUTPUT-H｜最终生图提示词

- 来源：运营确认图片计划、商品参考图、模特参考图。
- 去向：生图模型。

### OUTPUT-I｜候选图片

- 来源：生图模型。
- 去向：AI 质检和自动返工。

### OUTPUT-J｜AI质检报告

- 来源：候选图片、图片计划、类目规范。
- 去向：自动返工、运营终审、知识库更新。

### OUTPUT-K｜运营终审套图

- 来源：AI 质检通过图片和运营终审。
- 去向：批量改色、最终交付、知识库更新。

### OUTPUT-L｜批量改色输入包

- 来源：基础色终审套图、标准颜色 TXT。
- 去向：`D:\AI改色-v2` Web 工作台。

### OUTPUT-M｜改色后颜色变体套图

- 来源：改色 Web 工作台。
- 去向：改色质检、最终交付。

### OUTPUT-N｜知识库更新项

- 来源：最终图片、图片计划、提示词、质检报告、运营终审意见。
- 去向：下一批 SKU 的图片策划和质量控制。

## 14. 快速执行清单

### 运营执行清单

- 准备 SKU xlsx。
- 准备商品参考图和模特参考图。
- 确认竞品图。
- 确认 AI 建议图片计划。
- 终审基础色套图。
- 准备标准颜色 TXT。
- 使用改色 Web 工作台提交批量改色。
- 终审改色后套图。
- 确认知识库更新项。

### 研发执行清单

- 确保 xlsx 解析正常。
- 确保竞品图采集合规。
- 维护 Gemini 提示词改写流程。
- 维护生图模型调用。
- 维护 AI 质检与返工逻辑。
- 维护输出目录和报告。
- 维护知识库检索与写入逻辑。
- 维护 `D:\AI改色-v2` Web 工作台可用性。

### AI质检硬性失败项

- 主图不是纯白背景。
- 主图出现全身模特。
- 主图商品占比低于 85%。
- 主图出现文字、水印、Logo、道具或场景。
- 副图明显为淘宝/拼多多海报风。
- 商品颜色、领口、肩带、衣长、下摆、面料纹理严重偏离参考图。
- 模特肢体、手指、脸部明显错误。
- 改色图改变了背景、模特、姿势或构图。

### 最终交付验收标准

- 每个 SKU 有一套基础色终审图。
- 如有改色需求，每个目标颜色都有完整套图。
- 每张图都有对应图片计划和最终提示词。
- 每张图都有 AI 质检记录。
- 不合格图片有返工记录。
- 通过终审的经验已写入知识库。
