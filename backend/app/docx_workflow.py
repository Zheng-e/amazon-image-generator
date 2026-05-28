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
    return f"""重要：请严格按图片编号理解参考图，不能互换。图1只代表产品，图2只代表模特身份，图3只代表上身效果正面参考。图4只代表上身效果侧面参考。图5只代表上身效果背面参考。

图1为我的产品图（{desc}）

图2为我的模特面部及身材参考图

图3上身效果正面参考。

图4上身效果侧面参考。

图5上身效果背面参考。

图片要求：

1.参考图二的面部长相及发型生成模特上身的3张正侧背特写图，产品必须完整、清晰、无变形地穿在模特身上，100%保留图1产品的颜色、材质纹理、版型结构、所有设计细节不随意发挥。

2.严格参考图3的衣服松紧度，穿着方式及衣服长度

3.下装与图3风格一致，做10%差异化处理

4.风格统一：严格遵循图1的摄影风格，包括色调（冷调/暖调/胶片感）、光影类型（自然光/柔光箱/逆光/侧光）、景深效果、画面质感。画面需要保持干净白底商品摄影感，不得生成街景、户外、生活场景或图3人物身份。

5.输出规格：{_half_body_spec(style_prompt)}"""


def _stage_2_prompt(product_name: str, material: str, style_prompt: str) -> str:
    desc = product_description(product_name, material)
    return f"""重要：请严格按图片编号理解参考图。图1只参考背景环境、构图氛围和摄影风格，禁止采用图1中的人物身份、脸、发型、身体、服装和姿态；图2才是最终画面必须保留的人物和服装主体。最终画面只能出现图2人物一个人。

图1是需要参考的风格，姿势和背景图片

图2是我的产品图上身图（{desc}）

【生成要求】

1.人物主体：必须使用图2模特作为唯一人物主体，严格保留图2模特的面部特征、五官比例、肤色、发型、身材轮廓，服装。禁止使用或替换成图1人物，不保留图1的配饰（例如：上衣款式，墨镜，外套，帽子，头巾，围巾等），差异化改变图1的饰品（例如：耳环，项链，戒指等）。差异化改变图1的搭配（例如：裤子，背包、手提包、斜挎包、水杯、咖啡杯、饮料杯等）。

2.人物姿势和表情参考图1并做90%差异化。

3.场景融合：将合成后的人物自然融入图1的场景背景中，人物与地面的接触关系、光影方向、透视比例必须合理。人物姿势、背景内容与图1保持80%差异化改变。

4.风格统一：严格遵循图1的摄影风格，包括色调（冷调/暖调/胶片感）、光影类型（自然光/柔光箱/逆光/侧光）、景深效果、画面质感，修图风格。

5.输出规格：{_half_body_spec(style_prompt)}

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
    return f"""重要：请严格按图片编号理解参考图。图1是已经确定好的场景模特图，是人物身份、场景和整体风格基础；图2是模特上身3视图，只用于校准服装款式、正侧背结构和细节。图3是姿势参考，只用于改变模特的表情和姿势最终。画面只能出现图1中的同一个人物。

图1确定好的场景模特图，图2模特上身3视图，图3姿势参考图

【生成要求】
保持图1人物穿搭（包包，项链，耳环，手链，帽子）完全不变，服装款式严格参考图2的款式不变，姿势和人物表情100%还原换成图3的姿势表情，手和头发，包包道具不挡住产品，整体风格统一，画面中只能出现一个人物，禁止三宫格、拼图、多人同框或一次生成多张图。

风格统一：严格遵循图1的摄影风格，包括色调（冷调/暖调/胶片感）、光影类型（自然光/柔光箱/逆光/侧光）、景深效果、画面质感

4.输出规格：{_half_body_spec(style_prompt)}"""


def _outfit_prompt(style_prompt: str) -> str:
    return f"""重要：图1为已经确定好的场景模特图。保持图1中的人物身份、面部特征、发型、身材比例、产品穿着状态和场景风格，只在姿势与穿搭道具上做变化。

保持人物穿搭不变，随机生成1张正面角度的时下流行拍照姿势，突出产品特性手里提着包包/相机或者其他穿搭道具（可搭配其他颜色薄款夏季防晒衬衫需要露出产品，下装其他裙装裤装）风格统一，头看向一边露出迷人的微笑。画面中只能出现一个人物，禁止三宫格、拼图、多人同框或一次生成多张图。

3.风格统一：严格遵循图1的摄影风格，包括色调（冷调/暖调/胶片感）、光影类型（自然光/柔光箱/逆光/侧光）、景深效果、画面质感

4.输出规格：{_half_body_spec(style_prompt)}"""


def _white_main_prompt(product_name: str, material: str, style_prompt: str) -> str:
    desc = product_description(product_name, material)
    return f"""重要：请严格按图片编号理解参考图，不能互换。图1只代表场景模特服装图，图2只代表正侧背款式参考，图3只代表姿势参考。

图1为我的场景模特服装图

图2为我的正侧背款式参考

图3为我的姿势参考

图片要求：为这款{desc}生成白底主图。人物姿势100%参考图3，严格保留图1模特面部特征、五官比例、肤色、发型、身材轮廓，严格保留图2服装的颜色、材质纹理、版型结构、所有设计细节不随意发挥。构图近距离特写（锁骨至胯部，露出下装），产品居中占比85%-90%。背景纯白（RGB255,255,255），无阴影杂色。使用哈苏Hasselblad 100mm镜头拍摄，自然肤质，毛孔清晰可见，不过度磨皮。输出规格：亚马逊电商主图，高清商业摄影，画面比例3:4。"""


def _white_back_prompt(product_name: str, material: str, style_prompt: str) -> str:
    desc = product_description(product_name, material)
    return f"""重要：请严格按图片编号理解参考图，不能互换。图1只代表场景模特服装图，图2只代表正侧背款式参考，图3只代表姿势参考。

图1为我的场景模特服装图

图2为我的正侧背款式参考

图3为我的姿势参考

图片要求：为这款{desc}生成侧背面视角白底主图。人物姿势100%参考图3，严格保留图1模特面部特征、五官比例、肤色、发型、身材轮廓，严格保留图2正侧背款式的背面/侧背穿着状态、颜色、材质纹理、版型结构、所有设计细节不随意发挥。构图近距离特写（肩颈至胯部，露出下装），产品居中占比85%-90%。背景纯白（RGB255,255,255），无阴影杂色。使用哈苏Hasselblad 100mm镜头拍摄，自然肤质，毛孔清晰可见，不过度磨皮。输出规格：亚马逊电商主图，高清商业摄影，画面比例3:4。"""


def build_workflow_steps(
    product_name: str,
    material: str,
    style_key: str,
    product_asset_id: str,
    model_asset_id: str,
    fit_front_asset_id: str,
    fit_side_asset_id: str,
    fit_back_asset_id: str,
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
            "input_asset_ids": [product_asset_id, model_asset_id, fit_front_asset_id, fit_side_asset_id, fit_back_asset_id],
            "input_step_ids": [],
            "input_refs": [
                {"type": "asset", "id": product_asset_id},
                {"type": "asset", "id": model_asset_id},
                {"type": "asset", "id": fit_front_asset_id},
                {"type": "asset", "id": fit_side_asset_id},
                {"type": "asset", "id": fit_back_asset_id},
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
                "pose_slot": True,
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
            "pose_slot": True,
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
            "pose_slot": True,
        },
    ]
