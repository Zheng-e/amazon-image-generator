from __future__ import annotations


FIELD_TYPES = [
    "text",
    "textarea",
    "single_select",
    "multi_select",
    "number",
    "boolean",
    "image_ref",
    "list",
]


def field(
    key: str,
    label: str,
    field_type: str = "text",
    required: bool = False,
    help_text: str = "",
    options: list[str] | None = None,
    knowledge_enabled: bool = True,
) -> dict:
    return {
        "key": key,
        "label": label,
        "type": field_type,
        "required": required,
        "help_text": help_text,
        "options": options or [],
        "prompt_role": "",
        "validation_rule": "",
        "knowledge_enabled": knowledge_enabled,
    }


DEFAULT_SCHEMAS: dict[str, dict] = {
    "output_a": {
        "name": "OUTPUT-A | 结构化商品事实字段",
        "fields": [
            field("sku", "商品编号", required=True),
            field("category", "大类目", required=True),
            field("sub_category", "细分品类"),
            field("product_name", "商品名称"),
            field("base_color", "基础色"),
            field("target_colors", "目标改色", "list"),
            field("fabric", "面料"),
            field("silhouette", "版型"),
            field("neckline", "领口"),
            field("strap_or_sleeve", "肩带/袖型"),
            field("length", "衣长"),
            field("key_selling_points", "核心卖点", "list", required=True),
            field("must_keep_details", "必须保持一致的商品细节", "list"),
            field("avoid_details", "禁止生成或容易出错的细节", "list"),
            field("reference_image_notes", "商品参考图说明", "textarea"),
        ],
    },
    "output_c": {
        "name": "OUTPUT-C | 单张竞品图内容结构分析",
        "fields": [
            field("image_role", "主图/副图/细节图/场景图", "single_select", True, options=["主图", "副图", "细节图", "场景图", "组合图"]),
            field("subject_type", "真人/平铺/假模/局部特写", "single_select", options=["真人", "平铺", "假模", "局部特写", "商品组合"]),
            field("background_type", "背景类型"),
            field("composition", "构图方式", "textarea"),
            field("crop_range", "裁切范围"),
            field("product_area_ratio", "商品画面占比"),
            field("model_pose", "模特动作"),
            field("visible_product_details", "可见商品细节", "list"),
            field("selling_point_expression", "卖点表达方式", "textarea"),
            field("text_or_graphic_elements", "文字/图标/标注情况", "textarea"),
            field("style_tags", "风格标签", "list"),
            field("quality_notes", "值得借鉴点", "list"),
            field("risk_notes", "不应复刻或不适合点", "list"),
        ],
    },
    "output_d": {
        "name": "OUTPUT-D | 类目视觉规范",
        "fields": [
            field("main_image_rules", "主图规范", "list", True),
            field("secondary_image_patterns", "副图常见结构", "list"),
            field("scene_patterns", "常见场景", "list"),
            field("pose_patterns", "常见姿势", "list"),
            field("composition_rules", "构图规律", "list"),
            field("selling_point_patterns", "卖点表达规律", "list"),
            field("text_usage_rules", "文字和图标使用规则", "list"),
            field("color_and_lighting_rules", "色彩与光线规范", "list"),
            field("amazon_style_notes", "亚马逊风格要求", "list"),
            field("forbidden_patterns", "禁忌项", "list"),
            field("opportunity_notes", "可差异化机会", "list"),
            field("knowledge_candidate_tags", "未来知识库标签", "list"),
        ],
    },
}


OUTPUT_LABELS = {
    "output_a": "OUTPUT-A",
    "output_c": "OUTPUT-C",
    "output_d": "OUTPUT-D",
}
