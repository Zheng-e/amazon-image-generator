from pathlib import Path


CSS_PATH = Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles.css"
APP_PATH = Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.jsx"


def _rule_body(css: str, selector: str) -> str:
    marker = f"{selector} {{"
    start = css.index(marker) + len(marker)
    end = css.index("}", start)
    return css[start:end]


def test_pose_ref_layout_is_scoped_and_wraps_text():
    css = CSS_PATH.read_text(encoding="utf-8")
    app = APP_PATH.read_text(encoding="utf-8")

    workflow_step = _rule_body(css, ".workflow-step")
    generated_image = _rule_body(css, ".workflow-step > img")
    base_refs = _rule_body(css, ".step-base-refs")
    base_ref_thumb = _rule_body(css, ".step-base-ref-thumb")

    assert "className=" in app and "step-base-refs" in app
    assert "step-pose-select" in app
    assert ".workflow-step img {" not in css
    assert "overflow: hidden" in workflow_step
    assert "min-width: 0" in workflow_step
    assert "width: 100%" in generated_image
    assert "background" in base_refs
    assert "width: 48px" in base_ref_thumb
    assert "height: 48px" in base_ref_thumb


def test_rag_search_split_layout_exists():
    css = CSS_PATH.read_text(encoding="utf-8")

    split = _rule_body(css, ".rag-search-split")
    panel = _rule_body(css, ".rag-search-panel")

    assert "grid-template-columns: 1fr 1fr" in split
    assert "display: grid" in panel


def test_rag_use_buttons_exist():
    css = CSS_PATH.read_text(encoding="utf-8")

    buttons = _rule_body(css, ".rag-use-buttons")
    assert "flex-wrap: wrap" in buttons
    assert "gap: 4px" in buttons


def test_rag_pagination_uses_local_cache_after_first_search():
    app = APP_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")
    pagination = _rule_body(css, ".rag-pagination")

    assert "const RAG_SEARCH_CACHE_LIMIT = 200" in app
    assert "const [cachedResults, setCachedResults]" in app
    assert "const [searchCache, setSearchCache]" in app
    assert "const cacheKey = JSON.stringify({ query: query.trim(), filters })" in app
    assert "const cached = searchCache[cacheKey]" in app
    assert "[cacheKey]: { results: nextResults, hasMore: Boolean(data.has_more) }" in app
    assert "const showCachedPage =" in app
    assert "body: JSON.stringify({ query, top_k: fetchLimit, offset: 0, filters })" in app
    assert "showCachedPage(cachedResults, page - 1)" in app
    assert "showCachedPage(cachedResults, page + 1)" in app
    assert "const [hasMore, setHasMore]" in app
    assert "if (!hasMore) return;" in app
    assert 'disabled={!hasMore || searchBusy}' in app
    assert "flex-wrap: wrap" in pagination
