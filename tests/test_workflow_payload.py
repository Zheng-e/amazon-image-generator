from backend.app.main import DocxWorkflowRunIn


def test_project_workflow_payload_accepts_path_project_id():
    payload = DocxWorkflowRunIn(
        product_name="白色吊带背心",
        material="棉混纺",
        product_asset_id="product-asset",
        model_asset_id="model-asset",
        fit_front_asset_id="fit-front",
        fit_side_asset_id="fit-side",
        fit_back_asset_id="fit-back",
        scene_asset_id="scene-asset",
        accessory_asset_id="accessory-asset",
    )

    assert payload.project_id == ""
    assert payload.product_asset_id == "product-asset"
    assert payload.model_asset_id == "model-asset"
    assert payload.fit_front_asset_id == "fit-front"
    assert payload.fit_side_asset_id == "fit-side"
    assert payload.fit_back_asset_id == "fit-back"
    assert payload.scene_asset_id == "scene-asset"
    assert payload.style_key == "natural_fashion"


def test_payload_has_model_scene_fields():
    payload = DocxWorkflowRunIn(
        product_name="测试",
        material="棉",
        product_asset_id="p",
        model_asset_id="m1",
        fit_front_asset_id="f1",
        fit_side_asset_id="f2",
        fit_back_asset_id="f3",
        scene_asset_id="s1",
        accessory_asset_id="acc1",
    )
    assert payload.model_asset_id == "m1"
    assert payload.scene_asset_id == "s1"
    assert not hasattr(payload, "pose_asset_id")


def test_payload_accessory_is_required():
    payload = DocxWorkflowRunIn(
        product_name="测试",
        material="棉",
        product_asset_id="p",
        fit_front_asset_id="f1",
        fit_side_asset_id="f2",
        fit_back_asset_id="f3",
        accessory_asset_id="acc1",
    )
    assert payload.accessory_asset_id == "acc1"


def test_payload_fit_asset_id_backward_compat():
    payload = DocxWorkflowRunIn(
        product_name="测试",
        material="棉",
        product_asset_id="p",
        fit_asset_id="old-fit",
        accessory_asset_id="acc1",
    )
    assert payload.fit_asset_id == "old-fit"
    assert payload.fit_front_asset_id == ""
