from backend.app import main as main_module


def test_api_rag_search_fetches_enough_results_for_local_page(monkeypatch):
    captured = {}

    def fake_rag_search(payload, offset=0, limit=None):
        captured["payload"] = payload
        captured["offset"] = offset
        captured["limit"] = limit
        return {"results": [], "has_more": False}

    monkeypatch.setattr(main_module, "rag_search", fake_rag_search)

    result = main_module.api_rag_search(
        main_module.RagSearchIn(query=" shirt ", top_k=8, offset=16, filters={"asset_type": "model"})
    )

    assert result == {"results": [], "has_more": False}
    assert captured == {
        "payload": {"query": "shirt", "top_k": 25, "filters": {"asset_type": "model"}},
        "offset": 16,
        "limit": 8,
    }
