from backend.app.rag_integration import (
    build_rag_summary,
    compact_rag_record,
    enrich_docx_steps_with_rag,
    reference_ids_by_type,
    select_stage_references,
)


def make_reference(ref_id, tags, score=0.5, sort_order=0, scene="欧洲风格城市街道"):
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


def test_build_rag_summary_prefers_metadata_fields():
    summary = build_rag_summary(make_reference("one", ["scene_reference"]))

    assert "欧洲风格城市街道" in summary
    assert "高级质感的欧美都市街拍风" in summary
    assert "低饱和暖调大地色系" in summary
    assert "明亮柔和侧方自然光" in summary


def test_select_stage_references_filters_by_stage_tags_and_limits_to_three():
    refs = [
        make_reference("a", ["scene_reference"], score=0.1, sort_order=2),
        make_reference("b", ["pose_reference"], score=0.9, sort_order=0),
        make_reference("c", ["color_reference"], score=0.8, sort_order=0),
        make_reference("d", ["scene_reference"], score=0.7, sort_order=1),
        make_reference("e", ["scene_reference"], score=0.6, sort_order=3),
    ]

    selected = select_stage_references("scene_model", refs)

    assert [item["id"] for item in selected] == ["c", "d", "a"]
    assert len(selected) == 3


def test_enrich_docx_steps_adds_prompt_summary_and_rag_refs():
    steps = [
        {
            "stage_id": "scene_model",
            "title": "第二步：场景模特图",
            "prompt": "原始提示词",
            "input_refs": [{"type": "step", "id": "model_on_body"}],
            "input_asset_ids": [],
            "input_step_ids": ["model_on_body"],
        }
    ]
    refs = [make_reference("ref1", ["scene_reference"], score=0.9)]

    enriched = enrich_docx_steps_with_rag(steps, refs)

    assert enriched[0]["prompt"].startswith("原始提示词")
    assert "知识库参考摘要" in enriched[0]["prompt"]
    assert "欧洲风格城市街道" in enriched[0]["prompt"]
    assert enriched[0]["input_refs"][-1] == {"type": "rag", "id": "ref1"}


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
