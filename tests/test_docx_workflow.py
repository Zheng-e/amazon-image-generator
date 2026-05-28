from backend.app.docx_workflow import build_workflow_steps


def build_steps(accessory_asset_id=""):
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
        accessory_asset_id=accessory_asset_id,
    )


def test_angle_steps_have_pose_slot_and_no_pose_in_input_refs():
    steps = build_steps()
    angle_steps = [step for step in steps if step["stage_id"].startswith("angle_")]

    assert len(angle_steps) == 4
    for step in angle_steps:
        assert step["pose_slot"] is True
        assert step["input_asset_ids"] == []
        assert step["input_refs"] == [
            {"type": "step", "id": "scene_model"},
            {"type": "step", "id": "model_on_body"},
        ]


def test_white_steps_have_pose_slot():
    steps = build_steps()
    white_steps = [step for step in steps if step["stage_id"] in ("white_main", "white_back")]

    assert len(white_steps) == 2
    for step in white_steps:
        assert step["pose_slot"] is True
        assert step["input_refs"] == [
            {"type": "step", "id": "model_on_body"},
            {"type": "asset", "id": "product-asset"},
        ]


def test_outfit_step_without_accessory():
    steps = build_steps()
    outfit = next(step for step in steps if step["stage_id"] == "outfit")

    assert outfit["input_asset_ids"] == []
    assert outfit["input_refs"] == [{"type": "step", "id": "scene_model"}]


def test_outfit_step_with_accessory():
    steps = build_steps(accessory_asset_id="accessory-asset")
    outfit = next(step for step in steps if step["stage_id"] == "outfit")

    assert outfit["input_asset_ids"] == ["accessory-asset"]
    assert outfit["input_refs"] == [
        {"type": "step", "id": "scene_model"},
        {"type": "asset", "id": "accessory-asset"},
    ]


def test_other_steps_do_not_have_pose_slot():
    steps = build_steps()
    non_pose_steps = [step for step in steps if step["stage_id"] not in ("angle_3", "angle_4", "angle_5", "angle_6", "white_main", "white_back")]

    assert len(non_pose_steps) == 3
    for step in non_pose_steps:
        assert "pose_slot" not in step
