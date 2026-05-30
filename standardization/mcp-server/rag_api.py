from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests


class RagApiError(RuntimeError):
    """Readable error raised when the existing image knowledge base rejects a request."""


class RagApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def search_knowledge_images(
        self,
        query: str,
        *,
        top_k: int = 5,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._json_response(
            "post",
            "/search",
            json={"query": query, "top_k": top_k, "offset": offset, "filters": filters or {}},
        )

    def search_knowledge_images_by_image(
        self,
        image_path: str,
        *,
        query: str = "",
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = self._existing_absolute_file(image_path, "查询图片")
        with path.open("rb") as fh:
            return self._json_response(
                "post",
                "/search-image",
                data={"query": query, "top_k": str(top_k), "filters": json.dumps(filters or {}, ensure_ascii=False)},
                files={"file": (path.name, fh, "application/octet-stream")},
            )

    def add_knowledge_image(
        self,
        image_path: str,
        *,
        category: str = "unknown",
        scene: str = "unknown",
        image_type: str = "product",
        compliance: str = "approved",
        asset_type: str = "other",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = self._existing_absolute_file(image_path, "入库图片")
        with path.open("rb") as fh:
            return self._json_response(
                "post",
                "/ingest",
                data={
                    "category": category,
                    "scene": scene,
                    "image_type": image_type,
                    "compliance": compliance,
                    "asset_type": asset_type,
                    "extra_metadata": json.dumps(metadata or {}, ensure_ascii=False),
                },
                files={"file": (path.name, fh, "application/octet-stream")},
            )

    def list_knowledge_records(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        payload = self._json_response("get", "/records")
        records = payload.get("records", [])
        return {"count": len(records), "records": records[max(0, offset) : max(0, offset) + max(1, limit)]}

    def get_knowledge_image_url(self, image_id: str) -> str:
        return f"{self.base_url}/images/{self._require_id(image_id, '图片编号')}"

    def get_knowledge_base_health(self) -> dict[str, Any]:
        return self._json_response("get", "/health")

    def _json_response(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._request(method, path, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise RagApiError(f"图片知识库返回了无法识别的数据: {response.text[:300]}") from exc
        if not isinstance(payload, dict):
            raise RagApiError("图片知识库返回格式错误")
        return payload

    def _request(self, method: str, path: str, **kwargs: Any):
        try:
            response = getattr(self.session, method)(f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            detail = self._error_detail(getattr(exc, "response", None))
            raise RagApiError(f"图片知识库请求失败: {detail or exc}") from exc

    @staticmethod
    def _error_detail(response) -> str:
        if response is None:
            return ""
        text = response.text[:500]
        try:
            payload = json.loads(text)
        except ValueError:
            return text
        if isinstance(payload, dict) and payload.get("detail"):
            return str(payload["detail"])
        return text

    @staticmethod
    def _absolute_path(value: str, label: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise RagApiError(f"{label}必须使用绝对路径: {value}")
        return path.resolve()

    @classmethod
    def _existing_absolute_file(cls, value: str, label: str) -> Path:
        path = cls._absolute_path(value, label)
        if not path.is_file():
            raise RagApiError(f"{label}不存在: {path}")
        return path

    @staticmethod
    def _require_id(value: str, label: str) -> str:
        clean = value.strip()
        if not clean:
            raise RagApiError(f"{label}不能为空")
        return clean
