from pathlib import Path


CSS_PATH = Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles.css"
APP_PATH = Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.jsx"


def _rule_body(css: str, selector: str) -> str:
    marker = f"{selector} {{"
    start = css.index(marker) + len(marker)
    end = css.index("}", start)
    return css[start:end]


def test_rag_reference_preview_layout_is_scoped_and_wraps_text():
    css = CSS_PATH.read_text(encoding="utf-8")
    app = APP_PATH.read_text(encoding="utf-8")

    workflow_step = _rule_body(css, ".workflow-step")
    generated_image = _rule_body(css, ".workflow-step > img")
    rag_thumb = _rule_body(css, ".step-rag-thumb")
    rag_item = _rule_body(css, ".step-rag-ref-item")
    rag_text = _rule_body(css, ".step-rag-ref-text")

    assert 'className="step-rag-ref-text"' in app
    assert ".workflow-step img {" not in css
    assert "overflow: hidden" in workflow_step
    assert "min-width: 0" in workflow_step
    assert "width: 100%" in generated_image
    assert "flex: 0 0 48px" in rag_thumb
    assert "min-width: 0" in rag_item
    assert "overflow: hidden" in rag_item
    assert "overflow-wrap: anywhere" in rag_text
    assert "word-break: break-word" in rag_text


if __name__ == "__main__":
    test_rag_reference_preview_layout_is_scoped_and_wraps_text()
    print("PASS")
