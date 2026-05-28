from backend.app.rag_integration import (
    RAG_CONTEXT_BLOCK_LEGACY,
    RAG_CONTEXT_BLOCK_START,
    allowed_aspects_for_usage_tags,
    build_default_model_description,
    build_rag_summary,
    compact_rag_record,
    compose_rag_context_block,
    enrich_docx_steps_with_rag,
    predicted_steps_for_usage_tags,
    reference_ids_by_type,
    select_stage_references,
    strip_rag_context_block,
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


def test_angle_stage_uses_single_pose_reference_as_image_three():
    steps = [
        {
            "stage_id": "angle_3",
            "title": "第3张：正侧背其他角度图",
            "prompt": "角度提示词：图1场景模特图，图2模特上身3视图，图3姿势参考图",
            "input_refs": [
                {"type": "step", "id": "scene_model"},
                {"type": "step", "id": "model_on_body"},
            ],
            "input_asset_ids": [],
            "input_step_ids": ["scene_model", "model_on_body"],
        }
    ]
    refs = [
        make_reference("composition", ["composition_reference"], score=0.99, sort_order=0),
        make_reference("pose", ["pose_reference"], score=0.5, sort_order=1),
        make_reference("pose-extra", ["pose_reference"], score=0.4, sort_order=2),
    ]

    enriched = enrich_docx_steps_with_rag(steps, refs)

    assert enriched[0]["input_refs"] == [
        {"type": "step", "id": "scene_model"},
        {"type": "step", "id": "model_on_body"},
        {"type": "rag", "id": "pose"},
    ]
    assert "图3：知识库参考图" in enriched[0]["prompt"]
    assert "姿势参考" in enriched[0]["prompt"]
    assert "composition" not in enriched[0]["prompt"]


def test_angle_stage_with_selected_pose_asset_does_not_add_rag_pose_reference():
    steps = [
        {
            "stage_id": "angle_3",
            "title": "第3张：正侧背其他角度图",
            "prompt": "角度提示词：图1场景模特图，图2模特上身3视图，图3姿势参考图",
            "input_refs": [
                {"type": "step", "id": "scene_model"},
                {"type": "step", "id": "model_on_body"},
                {"type": "asset", "id": "selected-pose"},
            ],
            "input_asset_ids": ["selected-pose"],
            "input_step_ids": ["scene_model", "model_on_body"],
        }
    ]
    refs = [make_reference("rag-pose", ["pose_reference"], score=0.9, sort_order=0)]

    enriched = enrich_docx_steps_with_rag(steps, refs)

    assert enriched[0]["input_refs"] == [
        {"type": "step", "id": "scene_model"},
        {"type": "step", "id": "model_on_body"},
        {"type": "asset", "id": "selected-pose"},
    ]
    assert RAG_CONTEXT_BLOCK_START not in enriched[0]["prompt"]
    assert "rag-pose" not in enriched[0]["prompt"]


def test_enrich_docx_steps_adds_structured_context_block():
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
    assert RAG_CONTEXT_BLOCK_START in enriched[0]["prompt"]
    assert "知识库参考摘要" not in enriched[0]["prompt"]
    assert "这张图是什么" in enriched[0]["prompt"]
    assert "本图只参考" in enriched[0]["prompt"]
    assert "不要参考" in enriched[0]["prompt"]
    assert enriched[0]["input_refs"][-1] == {"type": "rag", "id": "ref1"}


def test_enrich_docx_steps_does_not_duplicate_context_block():
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

    enriched_once = enrich_docx_steps_with_rag(steps, refs)
    enriched_twice = enrich_docx_steps_with_rag(enriched_once, refs)

    count = enriched_twice[0]["prompt"].count(RAG_CONTEXT_BLOCK_START)
    assert count == 1


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


def test_predicted_steps_for_scene_reference():
    steps = predicted_steps_for_usage_tags(["scene_reference"])
    stage_ids = [s["stage_id"] for s in steps]
    assert "scene_model" in stage_ids
    assert steps[0]["image_no"] == 2
    assert "场景参考" in steps[0]["reason"]


def test_predicted_steps_for_pose_reference():
    steps = predicted_steps_for_usage_tags(["pose_reference"])
    image_nos = [s["image_no"] for s in steps]
    assert 3 in image_nos
    assert 4 in image_nos
    assert 5 in image_nos
    assert 6 in image_nos
    assert 7 in image_nos


def test_predicted_steps_for_white_main_reference():
    steps = predicted_steps_for_usage_tags(["white_main_reference"])
    image_nos = [s["image_no"] for s in steps]
    assert 8 in image_nos
    assert 9 in image_nos


def test_predicted_steps_for_composition_reference_only_targets_white_images():
    steps = predicted_steps_for_usage_tags(["composition_reference"])
    image_nos = [s["image_no"] for s in steps]
    assert image_nos == [8, 9]


def test_predicted_steps_merges_multiple_tags():
    steps = predicted_steps_for_usage_tags(["scene_reference", "color_reference"])
    stage_ids = [s["stage_id"] for s in steps]
    assert "scene_model" in stage_ids
    assert "outfit" in stage_ids
    # scene_model should have combined reason
    scene_step = next(s for s in steps if s["stage_id"] == "scene_model")
    assert "场景参考" in scene_step["reason"]
    assert "色调参考" in scene_step["reason"]


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


def test_allowed_aspects_for_scene_reference():
    aspects = allowed_aspects_for_usage_tags(["scene_reference"])
    assert "背景环境" in aspects
    assert "场景氛围" in aspects
    assert "空间关系" in aspects


def test_allowed_aspects_for_composition_reference():
    aspects = allowed_aspects_for_usage_tags(["composition_reference"])
    assert "构图方式" in aspects
    assert "画面裁切" in aspects


def test_allowed_aspects_deduplicates():
    aspects = allowed_aspects_for_usage_tags(["scene_reference", "color_reference"])
    # "色调" is only in color_reference, "背景环境" only in scene_reference
    assert aspects.count("背景环境") == 1
    assert "色调" in aspects


def test_compose_rag_context_block_generates_correct_image_number():
    input_refs = [
        {"type": "asset", "id": "asset1"},
        {"type": "step", "id": "model_on_body"},
        {"type": "rag", "id": "rag1"},
    ]
    rag_ref = {
        "id": "rag1",
        "rag_image_id": "rag-img-1",
        "filename": "street.jpg",
        "usage_tags": ["scene_reference"],
        "usage_labels": ["场景参考"],
        "model_description": "这是一张街道场景图",
        "metadata": {},
    }
    rag_refs_by_id = {"rag1": rag_ref}

    block = compose_rag_context_block(input_refs, rag_refs_by_id)

    assert "图3" in block
    assert "street.jpg" in block
    assert "这张图是什么" in block
    assert "本图只参考" in block
    assert "不要参考" in block


def test_compose_rag_context_block_empty_for_no_rag_refs():
    input_refs = [{"type": "asset", "id": "asset1"}]
    block = compose_rag_context_block(input_refs, {})
    assert block == ""


def test_strip_rag_context_block_removes_new_format():
    prompt = f"基础提示词\n\n{RAG_CONTEXT_BLOCK_START}\n一些说明\n"
    assert strip_rag_context_block(prompt) == "基础提示词"


def test_strip_rag_context_block_removes_legacy_format():
    prompt = f"基础提示词\n\n{RAG_CONTEXT_BLOCK_LEGACY}\n一些摘要\n"
    assert strip_rag_context_block(prompt) == "基础提示词"


def test_strip_rag_context_block_no_op_when_absent():
    prompt = "基础提示词，没有知识库说明"
    assert strip_rag_context_block(prompt) == prompt
