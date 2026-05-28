from backend.app.main import DocxWorkflowRunIn


def test_project_workflow_payload_accepts_path_project_id():
    payload = DocxWorkflowRunIn(
        product_name="白色吊带背心",
        material="棉混纺",
        product_asset_id="product-asset",
        model_asset_id="model-asset",
        fit_asset_id="fit-asset",
        scene_asset_id="scene-asset",
        pose_asset_id="pose-asset",
    )

    assert payload.project_id == ""
    assert payload.pose_asset_id == "pose-asset"
