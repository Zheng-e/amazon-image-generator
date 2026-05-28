from backend.app.main import DocxWorkflowRunIn


def test_project_workflow_payload_accepts_path_project_id():
    payload = DocxWorkflowRunIn(
        product_name="白色吊带背心",
        material="棉混纺",
        product_asset_id="product-asset",
        model_asset_id="model-asset",
        fit_front_asset_id="fit-front-asset",
        fit_side_asset_id="fit-side-asset",
        fit_back_asset_id="fit-back-asset",
        scene_asset_id="scene-asset",
        accessory_asset_id="accessory-asset",
    )

    assert payload.project_id == ""
    assert payload.fit_front_asset_id == "fit-front-asset"
    assert payload.fit_side_asset_id == "fit-side-asset"
    assert payload.fit_back_asset_id == "fit-back-asset"
    assert payload.accessory_asset_id == "accessory-asset"
