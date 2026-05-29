from backend.app.docx_workflow import build_workflow_steps


def build_steps():
    return build_workflow_steps(
        product_name="白色吊带背心",
        material="棉混纺",
        style_key="natural_fashion",
        product_asset_id="product-asset",
        model_asset_id="model-asset",
        fit_front_asset_id="fit-front-asset",
        fit_side_asset_id="fit-side-asset",
        fit_back_asset_id="fit-back-asset",
        scene_asset_id="scene-asset",
        accessory_asset_id="accessory-asset",
    )


def test_workflow_has_nine_steps():
    steps = build_steps()
    assert len(steps) == 9


def test_step1_model_on_body_uses_product_and_fit_assets():
    steps = build_steps()
    step1 = steps[0]
    assert step1["stage_id"] == "model_on_body"
    assert step1["input_asset_ids"] == ["product-asset", "model-asset", "fit-front-asset", "fit-side-asset", "fit-back-asset"]
    assert step1["input_refs"] == [
        {"type": "asset", "id": "product-asset"},
        {"type": "asset", "id": "model-asset"},
        {"type": "asset", "id": "fit-front-asset"},
        {"type": "asset", "id": "fit-side-asset"},
        {"type": "asset", "id": "fit-back-asset"},
    ]


def test_step2_scene_model_has_scene_asset_ref():
    steps = build_steps()
    step2 = steps[1]
    assert step2["stage_id"] == "scene_model"
    assert step2["input_asset_ids"] == ["scene-asset"]
    assert step2["input_refs"] == [
        {"type": "asset", "id": "scene-asset"},
        {"type": "step", "id": "model_on_body"},
    ]


def test_angle_steps_have_only_step_refs():
    steps = build_steps()
    angle_steps = [step for step in steps if step["stage_id"].startswith("angle_")]

    assert len(angle_steps) == 4
    for step in angle_steps:
        assert step["input_asset_ids"] == []
        assert step["input_refs"] == [
            {"type": "step", "id": "scene_model"},
            {"type": "step", "id": "model_on_body"},
        ]
        assert step.get("pose_slot") is True


def test_outfit_step_always_has_accessory():
    steps = build_steps()
    outfit = next(s for s in steps if s["stage_id"] == "outfit")
    assert outfit["input_refs"] == [
        {"type": "step", "id": "scene_model"},
        {"type": "asset", "id": "accessory-asset"},
    ]
    assert outfit["input_asset_ids"] == ["accessory-asset"]


def test_white_steps_have_pose_slot():
    steps = build_steps()
    white_main = next(s for s in steps if s["stage_id"] == "white_main")
    white_back = next(s for s in steps if s["stage_id"] == "white_back")
    assert white_main.get("pose_slot") is True
    assert white_back.get("pose_slot") is True
