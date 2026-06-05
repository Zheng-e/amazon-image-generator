from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests


MCP_SERVER_DIR = Path(__file__).resolve().parents[1] / "mcp-server"
sys.path.insert(0, str(MCP_SERVER_DIR))

from rag_api import RagApiClient, RagApiError  # noqa: E402


class FakeResponse:
    def __init__(self, *, json_data=None, status_code: int = 200, text: str = ""):
        self._json_data = json_data
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


def test_search_knowledge_images_posts_text_query():
    session = FakeSession([FakeResponse(json_data={"results": [{"image_id": "rag-1"}]})])
    client = RagApiClient("http://127.0.0.1:8010/", session=session)

    result = client.search_knowledge_images("运动背心 街景", top_k=8, filters={"asset_type": "other"})

    assert result["results"][0]["image_id"] == "rag-1"
    _, url, kwargs = session.calls[0]
    assert url == "http://127.0.0.1:8010/search"
    assert kwargs["json"]["query"] == "运动背心 街景"
    assert kwargs["json"]["top_k"] == 8


def test_search_knowledge_images_by_image_posts_file_and_filters(tmp_path: Path):
    image = tmp_path / "reference.jpg"
    image.write_bytes(b"image")
    session = FakeSession([FakeResponse(json_data={"results": []})])
    client = RagApiClient("http://127.0.0.1:8010", session=session)

    client.search_knowledge_images_by_image(str(image.resolve()), query="类似姿势", filters={"asset_type": "other"})

    _, url, kwargs = session.calls[0]
    assert url == "http://127.0.0.1:8010/search-image"
    assert kwargs["data"]["query"] == "类似姿势"
    assert kwargs["files"]["file"][0] == "reference.jpg"
    assert '"asset_type": "other"' in kwargs["data"]["filters"]


def test_add_knowledge_image_posts_metadata(tmp_path: Path):
    image = tmp_path / "excellent.jpg"
    image.write_bytes(b"image")
    session = FakeSession([FakeResponse(json_data={"image_id": "rag-2"})])
    client = RagApiClient("http://127.0.0.1:8010", session=session)

    result = client.add_knowledge_image(
        str(image.resolve()),
        category="运动背心",
        scene="街景",
        image_type="场景模特图",
        asset_type="other",
        metadata={"source": "approved-suite"},
    )

    assert result["image_id"] == "rag-2"
    _, url, kwargs = session.calls[0]
    assert url == "http://127.0.0.1:8010/ingest"
    assert kwargs["data"]["category"] == "运动背心"
    assert kwargs["files"]["file"][0] == "excellent.jpg"
    assert '"source": "approved-suite"' in kwargs["data"]["extra_metadata"]


def test_list_records_slices_existing_records():
    session = FakeSession([FakeResponse(json_data={"records": [{"image_id": "1"}, {"image_id": "2"}, {"image_id": "3"}]})])
    client = RagApiClient("http://127.0.0.1:8010", session=session)

    result = client.list_knowledge_records(limit=1, offset=1)

    assert result == {"count": 3, "records": [{"image_id": "2"}]}


def test_get_image_url_and_health_use_existing_service():
    session = FakeSession([FakeResponse(json_data={"status": "ok"})])
    client = RagApiClient("http://127.0.0.1:8010/", session=session)

    assert client.get_knowledge_image_url("rag-1") == "http://127.0.0.1:8010/images/rag-1"
    assert client.get_knowledge_base_health() == {"status": "ok"}


def test_image_operations_require_absolute_paths():
    client = RagApiClient("http://127.0.0.1:8010", session=FakeSession([]))

    with pytest.raises(RagApiError, match="绝对路径"):
        client.add_knowledge_image("relative.jpg")


def test_http_error_is_converted_to_readable_error():
    session = FakeSession([FakeResponse(status_code=400, text='{"detail":"query is required"}')])
    client = RagApiClient("http://127.0.0.1:8010", session=session)

    with pytest.raises(RagApiError, match="query is required"):
        client.search_knowledge_images("")
