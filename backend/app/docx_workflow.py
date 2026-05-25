from __future__ import annotations

from typing import Any


STYLE_OPTIONS: dict[str, dict[str, str]] = {
    "cinematic_documentary": {
        "label": "电影感·硬朗纪实风格",
        "prompt": (
            "粗粝电影感特写肖像：皮肤布满明显毛孔，呈现日晒损伤的质感，保留真实肌肤瑕疵；"
            "采用落日方向的强烈戏剧性侧光，真实自然的原片效果，使用35mm镜头、f/2.8光圈拍摄，"
            "风格为Raw格式v6.0，宽高比4:5"
        ),
    },
    "natural_fashion": {
        "label": "裸妆感·高级时尚自然",
        "prompt": (
            "一位年轻女性的影棚美妆肖像照，妆容极简，肤色自然，皮肤泛着轻微红晕，毛孔清晰可见，肤质细腻。"
            "柔和的窗光漫射照明，专业编辑级摄影，"
            "使用哈苏（Hasselblad）相机拍摄，100mm焦距，焦点精准落在眼部，"
            "未经修饰——采用Raw格式，6.0版本，宽高比3:4"
        ),
    },
    "street_film": {
        "label": "街头抓拍·胶片质感",
        "prompt": (
            "一位面带自然痘印与雀斑的少女街头肖像，笑容真挚。"
            "在金色时刻逆光下拍摄，采用胶片摄影质感，柯达彩色调色，"
            "呈现逼真的细腻皮肤纹理与微粒感，使用50mm镜头拍摄——"
            "风格为原片直出（raw），6.0版本，画幅比例3:4"
        ),
    },
}


def style_options_payload() -> list[dict[str, str]]:
    return [{"key": key, "label": value["label"], "prompt": value["prompt"]} for key, value in STYLE_OPTIONS.items()]


def product_description(product_name: str, material: str) -> str:
    return f"产品为{product_name}，材质为{material}"


def _half_body_spec(style_prompt: str) -> str:
    return f"人物半身照（头顶至大腿中部）{style_prompt}"


def _upper_body_spec(style_prompt: str) -> str:
    return f"人物上衣特写（下巴至胯部）{style_prompt}"


def _stage_1_prompt(product_name: str, material: str, style_prompt: str) -> str:
    desc = product_description(product_name, material)
    return f"""重要：请严格按图片编号理解参考图，不能互换。图1只代表产品，图2只代表模特身份，图3只代表上身效果参考。

图1为我的产品图（{desc}）

图2为我的模特面部及身材参考图

图3为衣服上身效果参考图（竞品）

图片要求：

1.参考图二的面部长相及发型生成模特上身的3张正侧背特写图，产品必须完整、清晰、无变形地穿在模特身上，保留原产品的颜色、材质纹理、版型结构、所有设计细节。

2.严格参考图3的衣服松紧度，穿着方式及衣服长度

3.风格统一：严格遵循图1的摄影风格，包括色调（冷调/暖调/胶片感）、光影类型（自然光/柔光箱/逆光/侧光）、景深效果、画面质感。画面需要保持干净白底商品摄影感，不得生成街景、户外、生活场景或图3人物身份。

4.输出规格：{_half_body_spec(style_prompt)}"""


def _stage_2_prompt(product_name: str, material: str, style_prompt: str) -> str:
    desc = product_description(product_name, material)
    return f"""重要：请严格按图片编号理解参考图。图1只参考背景环境、构图氛围和摄影风格，禁止采用图1中的人物身份、脸、发型、身体、服装和姿态；图2才是最终画面必须保留的人物和服装主体。最终画面只能出现图2人物一个人。

图1是需要参考的风格和背景图片

图2是我的产品图上身图（{desc}）

【生成要求】

1.人物主体：必须使用图2模特作为唯一人物主体，严格保留图2模特的面部特征、五官比例、肤色、发型、身材轮廓，服装。禁止使用或替换成图1人物，不保留图1的配饰（例如：上衣款式，墨镜，外套，帽子，头巾，围巾等），差异化改变图1的饰品（例如：耳环，项链，戒指等）。差异化改变图1的搭配（例如：裤子，背包、手提包、斜挎包、水杯、咖啡杯、饮料杯等）。

2.场景融合：将合成后的人物自然融入图1的场景背景中，人物与地面的接触关系、光影方向、透视比例必须合理。人物、背景内容进行80%差异化改变图片。

3.风格统一：严格遵循图1的摄影风格，包括色调（冷调/暖调/胶片感）、光影类型（自然光/柔光箱/逆光/侧光）、景深效果、画面质感

4.输出规格：{_half_body_spec(style_prompt)}

【负面约束】

禁止改变模特长相和身材比例

禁止使用图1人物的脸、发型、肤色、身材或服装

禁止模特双眼无神，头发遮挡衣服

禁止产品变形、错位、材质失真

禁止出现多余的手脚、扭曲的关节，多余不合理的饰品

禁止背景与人物光影方向不一致

禁止画面出现品牌logo、水印、文字，路人

禁止出现两个或多个主体人物"""


def _angle_prompt(style_prompt: str) -> str:
    return f"""重要：请严格按图片编号理解参考图。图1是已经确定好的场景模特图，是人物身份、场景和整体风格基础；图2是模特上身3视图，只用于校准服装款式、正侧背结构和细节。最终画面只能出现图1中的同一个人物。

图1确定好的场景模特图，图2模特上身3视图

保持人物穿搭不变，只生成1张单人图片，随机生成1个正面角度的时下流行拍照姿势。衣服款式严格参考图2的款式不变，突出产品特性，手里可以提着包包或者其他穿搭道具，整体风格统一，头看向一边露出迷人的微笑。画面中只能出现一个人物，禁止三宫格、拼图、多人同框或一次生成多张图。

风格统一：严格遵循图1的摄影风格，包括色调（冷调/暖调/胶片感）、光影类型（自然光/柔光箱/逆光/侧光）、景深效果、画面质感

4.输出规格：{_half_body_spec(style_prompt)}"""


def _outfit_prompt(style_prompt: str) -> str:
    return f"""重要：图1为已经确定好的场景模特图。保持图1中的人物身份、面部特征、发型、身材比例、产品穿着状态和场景风格，只在姿势与穿搭道具上做变化。

保持人物穿搭不变，随机生成1张正面角度的时下流行拍照姿势，突出产品特性手里提着包包/相机或者其他穿搭道具（可搭配其他颜色薄款夏季防晒衬衫需要露出产品，下装其他裙装裤装）风格统一，头看向一边露出迷人的微笑。画面中只能出现一个人物，禁止三宫格、拼图、多人同框或一次生成多张图。

3.风格统一：严格遵循图1的摄影风格，包括色调（冷调/暖调/胶片感）、光影类型（自然光/柔光箱/逆光/侧光）、景深效果、画面质感

4.输出规格：{_half_body_spec(style_prompt)}"""


def _white_main_prompt(product_name: str, material: str, style_prompt: str) -> str:
    desc = product_description(product_name, material)
    return f"""重要：请严格按图片编号理解参考图。图1为产品模特上身3视图，只参考同一位模特和正面穿着状态；图2为原始产品图，只参考产品颜色、材质、版型结构和设计细节。

图1为我的产品模特上身3视图
图2为我的原始产品图

提示词：

为这款（{desc}）生成符合亚马逊规范的白底主图。

要求：

1.画面目标不是时尚人像，而是亚马逊服装主图。必须正面展示产品，人物只作为穿着载体，允许裁掉完整脸部、头发、腿部和多余身体区域。

2.构图必须为近距离商品特写：画面裁切范围优先为锁骨/下巴以下至衣服下摆附近，只保留必要肩颈、手臂边缘和少量下装边缘。产品主体必须居中，产品在整张图中的视觉占比达到85%-90%。

3.产品必须完整、清晰、无变形地穿在模特身上，严格保留图2原始产品的白色、材质纹理、版型结构、双层效果、吊带细节和所有设计细节。

4.手、头发、配饰、包、杯子、外套、衬衫、道具不得遮挡产品，不得添加多余搭配，不得出现品牌logo、水印、文字。

5.背景必须为纯白底（RGB255,255,255），无阴影杂色、无街头、无户外、无室内生活场景、无地面墙面、无路人或额外人物。

6.输出规格：亚马逊电商主图，真实棚拍质感，产品边缘清晰，面料纹理可见，高清商业摄影，未过度磨皮，画面比例3:4。"""


def _white_back_prompt(product_name: str, material: str, style_prompt: str) -> str:
    desc = product_description(product_name, material)
    return f"""重要：请严格按图片编号理解参考图。图1为产品模特上身3视图，只参考同一位模特和背面/侧背穿着状态；图2为原始产品图，只参考产品颜色、材质、版型结构和设计细节。

图1为我的产品模特上身3视图
图2为我的原始产品图

提示词：

为这款（{desc}）生成符合亚马逊规范的背面/侧背白底主图。

要求：

1.画面目标不是时尚人像，而是亚马逊服装主图。必须生成单人单图的背面或侧背面产品展示，禁止三联图、拼图、多人物、多角度同时展示。

2.构图必须为近距离商品特写：画面裁切范围优先为肩颈/下巴以下至衣服下摆附近，只保留必要肩背、手臂边缘和少量下装边缘。产品主体必须居中，产品在整张图中的视觉占比达到85%-90%。

3.产品必须完整、清晰、无变形地穿在模特身上，严格保留图2原始产品的白色、材质纹理、版型结构、双层效果、吊带细节和所有设计细节，并体现背面/侧背穿着状态。

4.手、头发、配饰、包、杯子、外套、衬衫、道具不得遮挡产品，不得添加多余搭配，不得出现品牌logo、水印、文字。

5.背景必须为纯白底（RGB255,255,255），无阴影杂色、无街头、无户外、无室内生活场景、无地面墙面、无路人或额外人物。

6.输出规格：亚马逊电商主图，真实棚拍质感，产品边缘清晰，面料纹理可见，高清商业摄影，未过度磨皮，画面比例3:4。"""


def build_workflow_steps(
    product_name: str,
    material: str,
    style_key: str,
    product_asset_id: str,
    model_asset_id: str,
    fit_asset_id: str,
    scene_asset_id: str,
) -> list[dict[str, Any]]:
    style_prompt = STYLE_OPTIONS[style_key]["prompt"]
    angle_prompt = _angle_prompt(style_prompt)
    return [
        {
            "stage_id": "model_on_body",
            "image_no": 1,
            "generation_order": 1,
            "title": "第一步：模特上身图",
            "prompt": _stage_1_prompt(product_name, material, style_prompt),
            "input_asset_ids": [product_asset_id, model_asset_id, fit_asset_id],
            "input_step_ids": [],
            "input_refs": [
                {"type": "asset", "id": product_asset_id},
                {"type": "asset", "id": model_asset_id},
                {"type": "asset", "id": fit_asset_id},
            ],
        },
        {
            "stage_id": "scene_model",
            "image_no": 2,
            "generation_order": 2,
            "title": "第二步：场景模特图",
            "prompt": _stage_2_prompt(product_name, material, style_prompt),
            "input_asset_ids": [scene_asset_id],
            "input_step_ids": ["model_on_body"],
            "input_refs": [
                {"type": "asset", "id": scene_asset_id},
                {"type": "step", "id": "model_on_body"},
            ],
        },
        *[
            {
                "stage_id": f"angle_{image_no}",
                "image_no": image_no,
                "generation_order": image_no,
                "title": f"第{image_no}张：正侧背其他角度图",
                "prompt": angle_prompt,
                "input_asset_ids": [],
                "input_step_ids": ["scene_model", "model_on_body"],
                "input_refs": [
                    {"type": "step", "id": "scene_model"},
                    {"type": "step", "id": "model_on_body"},
                ],
            }
            for image_no in range(3, 7)
        ],
        {
            "stage_id": "outfit",
            "image_no": 7,
            "generation_order": 7,
            "title": "第七张：穿搭图",
            "prompt": _outfit_prompt(style_prompt),
            "input_asset_ids": [],
            "input_step_ids": ["scene_model"],
            "input_refs": [{"type": "step", "id": "scene_model"}],
        },
        {
            "stage_id": "white_main",
            "image_no": 8,
            "generation_order": 8,
            "title": "第八张：白底主图",
            "prompt": _white_main_prompt(product_name, material, style_prompt),
            "input_asset_ids": [product_asset_id],
            "input_step_ids": ["model_on_body"],
            "input_refs": [
                {"type": "step", "id": "model_on_body"},
                {"type": "asset", "id": product_asset_id},
            ],
        },
        {
            "stage_id": "white_back",
            "image_no": 9,
            "generation_order": 9,
            "title": "第九张：背面白底图",
            "prompt": _white_back_prompt(product_name, material, style_prompt),
            "input_asset_ids": [product_asset_id],
            "input_step_ids": ["model_on_body"],
            "input_refs": [
                {"type": "step", "id": "model_on_body"},
                {"type": "asset", "id": product_asset_id},
            ],
        },
    ]
