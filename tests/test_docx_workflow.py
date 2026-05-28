from backend.app.docx_workflow import build_workflow_steps


def build_steps(pose_asset_id=""):
    return build_workflow_steps(
        product_name="白色吊带背心",
        material="棉混纺",
        style_key="natural_fashion",
        product_asset_id="product-asset",
        model_asset_id="model-asset",
        fit_asset_id="fit-asset",
        scene_asset_id="scene-asset",
        pose_asset_id=pose_asset_id,
    )


def test_angle_steps_include_uploaded_pose_reference_as_image_three():
    steps = build_steps(pose_asset_id="pose-asset")
    angle_steps = [step for step in steps if step["stage_id"].startswith("angle_")]

    assert len(angle_steps) == 4
    for step in angle_steps:
        assert step["input_asset_ids"] == ["pose-asset"]
        assert step["input_refs"] == [
            {"type": "step", "id": "scene_model"},
            {"type": "step", "id": "model_on_body"},
            {"type": "asset", "id": "pose-asset"},
        ]


def test_angle_steps_without_uploaded_pose_reference_keep_rag_fallback_slot_empty():
    steps = build_steps()
    angle_steps = [step for step in steps if step["stage_id"].startswith("angle_")]

    assert len(angle_steps) == 4
    for step in angle_steps:
        assert step["input_asset_ids"] == []
        assert step["input_refs"] == [
            {"type": "step", "id": "scene_model"},
            {"type": "step", "id": "model_on_body"},
        ]
