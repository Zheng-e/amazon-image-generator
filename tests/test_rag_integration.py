import backend.app.rag_integration as rag_module
from backend.app.rag_integration import (
    allowed_aspects_for_usage_tags,
    build_default_model_description,
    build_rag_summary,
    compact_rag_record,
    predicted_steps_for_usage_tags,
    rag_search,
    reference_ids_by_type,
)


def make_reference(ref_id, tags, score=0.5, sort_order=0, scene="欧洲风格城市街道", rag_role=""):
    return {
        "id": ref_id,
        "rag_image_id": f"rag-{ref_id}",
        "filename": f"{ref_id}.jpg",
        "category": "女装 / 背心",
        "scene": scene,
        "image_type": "竖幅中景构图",
        "caption": "balanced clean product image",
        "score": score,
        "usage_tags": tags,
        "rag_role": rag_role,
        "metadata": {
            "visual_style": "高级质感的欧美都市街拍风",
            "color_tone": "低饱和暖调大地色系",
            "scene_description": scene,
            "composition": "竖幅中景构图",
            "season": "春夏",
            "lighting": "明亮柔和侧方自然光",
        },
        "sort_order": sort_order,
    }


def test_compact_rag_record_removes_large_and_private_fields():
    raw = {
        "image_id": "abc",
        "filename": "abc.jpg",
        "embedding_vector": [1, 2, 3],
        "embedding_text": "large text",
        "storage_key": "D:/RAG/data/images/abc.jpg",
        "metadata": {"scene_description": "街道"},
    }

    compact = compact_rag_record(raw)

    assert compact["image_id"] == "abc"
    assert compact["filename"] == "abc.jpg"
    assert "embedding_vector" not in compact
    assert "embedding_text" not in compact
    assert "storage_key" not in compact
    assert compact["metadata"]["scene_description"] == "街道"


def test_rag_search_slices_locally_and_reports_has_more(monkeypatch):
    class FakeResponse:
        def json(self):
            return {
                "results": [
                    {
                        "image_id": f"img-{index}",
                        "filename": f"img-{index}.jpg",
                        "embedding_vector": [index],
                    }
                    for index in range(6)
                ]
            }

    captured = {}

    def fake_rag_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr(rag_module, "rag_request", fake_rag_request)

    data = rag_search({"query": "shirt", "top_k": 6}, offset=2, limit=3)

    assert captured == {"method": "POST", "path": "/search", "json": {"query": "shirt", "top_k": 6}}
    assert [item["image_id"] for item in data["results"]] == ["img-2", "img-3", "img-4"]
    assert all("embedding_vector" not in item for item in data["results"])
    assert data["offset"] == 2
    assert data["limit"] == 3
    assert data["has_more"] is True


def test_build_rag_summary_prefers_metadata_fields():
    summary = build_rag_summary(make_reference("one", ["scene_reference"]))

    assert "欧洲风格城市街道" in summary
    assert "高级质感的欧美都市街拍风" in summary
    assert "低饱和暖调大地色系" in summary
    assert "明亮柔和侧方自然光" in summary


def test_reference_ids_by_type_includes_rag_ids():
    refs = [
        {"type": "asset", "id": "asset1"},
        {"type": "step", "id": "model_on_body"},
        {"type": "rag", "id": "rag1"},
        {"type": "rag", "id": "rag2"},
    ]

    snapshot = reference_ids_by_type(refs)

    assert snapshot == {
        "reference_refs": refs,
        "reference_asset_ids": ["asset1"],
        "reference_stage_ids": ["model_on_body"],
        "reference_rag_ids": ["rag1", "rag2"],
    }


def test_predicted_steps_for_rag_role_model():
    steps = predicted_steps_for_usage_tags([], rag_role="model")
    stage_ids = [s["stage_id"] for s in steps]
    assert "model_on_body" in stage_ids
    assert steps[0]["reason"] == "模特参考"


def test_predicted_steps_for_rag_role_scene_style():
    steps = predicted_steps_for_usage_tags([], rag_role="scene_style")
    stage_ids = [s["stage_id"] for s in steps]
    assert "scene_model" in stage_ids
    assert "场景风格参考" in steps[0]["reason"]


def test_predicted_steps_for_rag_role_pose():
    steps = predicted_steps_for_usage_tags([], rag_role="pose")
    image_nos = [s["image_no"] for s in steps]
    assert 3 in image_nos
    assert 4 in image_nos
    assert 5 in image_nos
    assert 6 in image_nos
    assert 8 in image_nos
    assert 9 in image_nos


def test_predicted_steps_for_rag_role_accessory():
    steps = predicted_steps_for_usage_tags([], rag_role="accessory")
    image_nos = [s["image_no"] for s in steps]
    assert 7 in image_nos


def test_build_default_model_description_prefers_model_description():
    ref = {
        "model_description": "自定义说明文字",
        "scene": "街道",
        "metadata": {"scene_description": "城市"},
    }
    assert build_default_model_description(ref) == "自定义说明文字"


def test_build_default_model_description_uses_metadata():
    ref = {
        "model_description": "",
        "scene": "",
        "metadata": {
            "scene_description": "欧洲城市街道",
            "visual_style": "高级街拍",
            "color_tone": "低饱和暖调",
            "lighting": "自然侧光",
        },
    }
    desc = build_default_model_description(ref)
    assert "欧洲城市街道" in desc
    assert "高级街拍" in desc
    assert "低饱和暖调" in desc


def test_build_default_model_description_fallback():
    ref = {"model_description": "", "scene": "", "metadata": {}, "filename": "test.jpg"}
    desc = build_default_model_description(ref)
    assert "test.jpg" in desc


def test_build_default_model_description_empty_fallback():
    ref = {"model_description": "", "scene": "", "metadata": {}}
    desc = build_default_model_description(ref)
    assert "知识库参考图" in desc


def test_allowed_aspects_for_rag_role_scene_style():
    aspects = allowed_aspects_for_usage_tags([], rag_role="scene_style")
    assert "背景环境" in aspects
    assert "场景氛围" in aspects
    assert "色调" in aspects


def test_allowed_aspects_for_rag_role_pose():
    aspects = allowed_aspects_for_usage_tags([], rag_role="pose")
    assert "人物姿势" in aspects
    assert "身体朝向" in aspects


def test_allowed_aspects_for_rag_role_accessory():
    aspects = allowed_aspects_for_usage_tags([], rag_role="accessory")
    assert "配饰款式" in aspects
    assert "穿搭搭配" in aspects
