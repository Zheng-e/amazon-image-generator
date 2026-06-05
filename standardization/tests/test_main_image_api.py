from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests


MCP_SERVER_DIR = Path(__file__).resolve().parents[1] / "mcp-server"
sys.path.insert(0, str(MCP_SERVER_DIR))

from main_image_api import MainImageApiClient, MainImageApiError  # noqa: E402


class FakeResponse:
    def __init__(self, *, json_data=None, content: bytes = b"", status_code: int = 200, text: str = ""):
        self._json_data = json_data
        self.content = content
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} error")
            error.response = self
            raise error


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _respond(self, method: str, url: str, kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def post(self, url: str, **kwargs):
        return self._respond("POST", url, kwargs)

    def get(self, url: str, **kwargs):
        return self._respond("GET", url, kwargs)


def test_create_main_image_project_posts_project_fields():
    session = FakeSession([FakeResponse(json_data={"id": "project-1", "sku": "SKU-1"})])
    client = MainImageApiClient("http://127.0.0.1:8020/", session=session)

    result = client.create_main_image_project("SKU-1", category="背心", name="项目一")

    assert result["id"] == "project-1"
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", "http://127.0.0.1:8020/api/projects")
    assert kwargs["json"]["sku"] == "SKU-1"
    assert kwargs["json"]["category"] == "背心"


def test_upload_project_assets_posts_existing_absolute_files(tmp_path: Path):
    image = tmp_path / "product.png"
    image.write_bytes(b"image")
    session = FakeSession([FakeResponse(json_data=[{"id": "asset-1"}])])
    client = MainImageApiClient("http://127.0.0.1:8020", session=session)

    result = client.upload_project_assets("project-1", "product", [str(image.resolve())], slot="product")

    assert result == [{"id": "asset-1"}]
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", "http://127.0.0.1:8020/api/assets")
    assert kwargs["data"]["project_id"] == "project-1"
    assert kwargs["data"]["asset_type"] == "product"
    assert kwargs["files"][0][0] == "files"
    assert kwargs["files"][0][1][0] == "product.png"


def test_upload_project_assets_requires_absolute_files():
    client = MainImageApiClient("http://127.0.0.1:8020", session=FakeSession([]))

    with pytest.raises(MainImageApiError, match="绝对路径"):
        client.upload_project_assets("project-1", "product", ["relative.png"])


def test_initialize_nine_image_workflow_posts_existing_payload():
    session = FakeSession([FakeResponse(json_data={"project_id": "project-1", "steps": []})])
    client = MainImageApiClient("http://127.0.0.1:8020", session=session)

    client.initialize_nine_image_workflow(
        project_id="project-1",
        product_name="运动背心",
        material="棉",
        product_asset_id="product-1",
        accessory_asset_id="accessory-1",
        model_asset_id="model-1",
    )

    _, url, kwargs = session.calls[0]
    assert url == "http://127.0.0.1:8020/api/projects/project-1/workflow"
    assert kwargs["json"]["product_name"] == "运动背心"
    assert kwargs["json"]["product_asset_id"] == "product-1"
    assert kwargs["json"]["accessory_asset_id"] == "accessory-1"


@pytest.mark.parametrize(
    ("method_name", "expected_method", "expected_path", "kwargs"),
    [
        ("generate_nine_image_suite", "POST", "/api/projects/project-1/workflow/generate", {}),
        ("get_nine_image_workflow", "GET", "/api/projects/project-1/workflow", {}),
        ("regenerate_nine_image_step", "POST", "/api/projects/workflow/steps/step-1/generate", {}),
    ],
)
def test_workflow_operations_map_to_existing_api(method_name: str, expected_method: str, expected_path: str, kwargs: dict):
    session = FakeSession([FakeResponse(json_data={"project_id": "project-1"})])
    client = MainImageApiClient("http://127.0.0.1:8020", session=session)

    target_id = "step-1" if method_name == "regenerate_nine_image_step" else "project-1"
    getattr(client, method_name)(target_id, **kwargs)

    method, url, _ = session.calls[0]
    assert method == expected_method
    assert url == f"http://127.0.0.1:8020{expected_path}"


def test_download_nine_image_suite_saves_zip(tmp_path: Path):
    session = FakeSession([FakeResponse(content=b"zip-bytes")])
    client = MainImageApiClient("http://127.0.0.1:8020", session=session)
    output = (tmp_path / "nested" / "suite.zip").resolve()

    result = client.download_nine_image_suite("project-1", str(output))

    assert output.read_bytes() == b"zip-bytes"
    assert result["output_path"] == str(output)
    assert result["bytes_written"] == 9


def test_search_rag_references_uses_main_image_proxy():
    session = FakeSession([FakeResponse(json_data={"results": [{"image_id": "rag-1"}]})])
    client = MainImageApiClient("http://127.0.0.1:8020", session=session)

    result = client.search_rag_references("运动背心 场景图", top_k=6, filters={"asset_type": "other"})

    assert result["results"][0]["image_id"] == "rag-1"
    _, url, kwargs = session.calls[0]
    assert url == "http://127.0.0.1:8020/api/rag/search"
    assert kwargs["json"]["top_k"] == 6


def test_add_rag_reference_and_copy_to_asset_use_existing_routes():
    session = FakeSession(
        [
            FakeResponse(json_data={"id": "selection-1"}),
            FakeResponse(json_data={"id": "asset-1"}),
        ]
    )
    client = MainImageApiClient("http://127.0.0.1:8020", session=session)

    selected = client.add_rag_reference_to_project("project-1", "rag-1", rag_role="pose")
    copied = client.copy_rag_reference_to_project_asset("project-1", "rag-1", rag_role="pose")

    assert selected["id"] == "selection-1"
    assert copied["id"] == "asset-1"
    assert session.calls[0][1] == "http://127.0.0.1:8020/api/projects/project-1/rag-references"
    assert session.calls[1][1] == "http://127.0.0.1:8020/api/projects/project-1/rag-to-asset"


def test_http_error_is_converted_to_readable_error():
    session = FakeSession([FakeResponse(status_code=400, text='{"detail":"SKU 为必填项"}')])
    client = MainImageApiClient("http://127.0.0.1:8020", session=session)

    with pytest.raises(MainImageApiError, match="SKU 为必填项"):
        client.create_main_image_project("")
