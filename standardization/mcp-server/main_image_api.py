from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Sequence

import requests


class MainImageApiError(RuntimeError):
    """Readable error raised when the existing main-image service rejects a request."""


class MainImageApiClient:
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

    def create_main_image_project(
        self,
        sku: str,
        *,
        user_id: str = "default",
        category: str = "",
        name: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        return self._json_response(
            "post",
            "/api/projects",
            json={"user_id": user_id, "sku": sku, "category": category, "name": name, "notes": notes},
        )

    def upload_project_assets(
        self,
        project_id: str,
        asset_type: str,
        file_paths: Sequence[str],
        *,
        source_url: str = "",
        asin: str = "",
        keyword: str = "",
        slot: str = "",
        notes: str = "",
    ) -> list[dict[str, Any]]:
        paths = [self._existing_absolute_file(path, "项目素材") for path in file_paths]
        if not paths:
            raise MainImageApiError("请至少提供一个项目素材文件")
        data = {
            "project_id": self._require_id(project_id, "项目编号"),
            "asset_type": asset_type,
            "source_url": source_url,
            "asin": asin,
            "keyword": keyword,
            "slot": slot,
            "notes": notes,
        }
        with ExitStack() as stack:
            files = [
                ("files", (path.name, stack.enter_context(path.open("rb")), "application/octet-stream"))
                for path in paths
            ]
            payload = self._json_response("post", "/api/assets", data=data, files=files)
        if not isinstance(payload, list):
            raise MainImageApiError("主图生成服务返回的素材列表格式错误")
        return payload

    def initialize_nine_image_workflow(
        self,
        project_id: str,
        product_name: str,
        material: str,
        product_asset_id: str,
        accessory_asset_id: str,
        *,
        style_key: str = "natural_fashion",
        model_asset_id: str = "",
        fit_front_asset_id: str = "",
        fit_side_asset_id: str = "",
        fit_back_asset_id: str = "",
        scene_asset_id: str = "",
        image_model: str = "",
        size: str = "1024x1024",
        quality: str = "high",
    ) -> dict[str, Any]:
        return self._json_response(
            "post",
            f"/api/projects/{self._require_id(project_id, '项目编号')}/workflow",
            json={
                "product_name": product_name,
                "material": material,
                "style_key": style_key,
                "product_asset_id": product_asset_id,
                "model_asset_id": model_asset_id,
                "fit_front_asset_id": fit_front_asset_id,
                "fit_side_asset_id": fit_side_asset_id,
                "fit_back_asset_id": fit_back_asset_id,
                "scene_asset_id": scene_asset_id,
                "accessory_asset_id": accessory_asset_id,
                "image_model": image_model or None,
                "size": size,
                "quality": quality,
            },
        )

    def generate_nine_image_suite(
        self,
        project_id: str,
        *,
        image_model: str = "",
        size: str = "",
        quality: str = "",
    ) -> dict[str, Any]:
        return self._json_response(
            "post",
            f"/api/projects/{self._require_id(project_id, '项目编号')}/workflow/generate",
            json={"image_model": image_model or None, "size": size or None, "quality": quality or None},
        )

    def get_nine_image_workflow(self, project_id: str) -> dict[str, Any]:
        return self._json_response("get", f"/api/projects/{self._require_id(project_id, '项目编号')}/workflow")

    def regenerate_nine_image_step(
        self,
        step_id: str,
        *,
        image_model: str = "",
        size: str = "",
        quality: str = "",
    ) -> dict[str, Any]:
        return self._json_response(
            "post",
            f"/api/projects/workflow/steps/{self._require_id(step_id, '步骤编号')}/generate",
            json={"image_model": image_model or None, "size": size or None, "quality": quality or None},
        )

    def download_nine_image_suite(self, project_id: str, output_path: str, *, overwrite: bool = False) -> dict[str, Any]:
        target = self._absolute_path(output_path, "下载目标")
        if target.exists() and not overwrite:
            raise MainImageApiError(f"下载目标已存在，请更换路径或允许覆盖: {target}")
        response = self._request("get", f"/api/projects/{self._require_id(project_id, '项目编号')}/workflow/download")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return {"project_id": project_id, "output_path": str(target), "bytes_written": len(response.content)}

    def search_rag_references(
        self,
        query: str,
        *,
        top_k: int = 8,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._json_response(
            "post",
            "/api/rag/search",
            json={"query": query, "top_k": top_k, "offset": offset, "filters": filters or {}},
        )

    def add_rag_reference_to_project(
        self,
        project_id: str,
        rag_image_id: str,
        *,
        filename: str = "",
        category: str = "",
        scene: str = "",
        image_type: str = "",
        caption: str = "",
        score: float | None = None,
        usage_tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        model_description: str = "",
        asset_type: str = "",
        rag_role: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        return self._json_response(
            "post",
            f"/api/projects/{self._require_id(project_id, '项目编号')}/rag-references",
            json={
                "rag_image_id": rag_image_id,
                "filename": filename,
                "category": category,
                "scene": scene,
                "image_type": image_type,
                "caption": caption,
                "score": score,
                "usage_tags": usage_tags or [],
                "metadata": metadata or {},
                "model_description": model_description,
                "asset_type": asset_type,
                "rag_role": rag_role,
                "notes": notes,
            },
        )

    def copy_rag_reference_to_project_asset(
        self,
        project_id: str,
        rag_image_id: str,
        *,
        filename: str = "",
        slot: str = "",
        rag_role: str = "",
        model_description: str = "",
    ) -> dict[str, Any]:
        return self._json_response(
            "post",
            f"/api/projects/{self._require_id(project_id, '项目编号')}/rag-to-asset",
            json={
                "rag_image_id": rag_image_id,
                "filename": filename,
                "slot": slot,
                "rag_role": rag_role,
                "model_description": model_description,
            },
        )

    def _json_response(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise MainImageApiError(f"主图生成服务返回了无法识别的数据: {response.text[:300]}") from exc

    def _request(self, method: str, path: str, **kwargs: Any):
        try:
            response = getattr(self.session, method)(f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            detail = self._error_detail(getattr(exc, "response", None))
            raise MainImageApiError(f"主图生成服务请求失败: {detail or exc}") from exc

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
            raise MainImageApiError(f"{label}必须使用绝对路径: {value}")
        return path.resolve()

    @classmethod
    def _existing_absolute_file(cls, value: str, label: str) -> Path:
        path = cls._absolute_path(value, label)
        if not path.is_file():
            raise MainImageApiError(f"{label}不存在: {path}")
        return path

    @staticmethod
    def _require_id(value: str, label: str) -> str:
        clean = value.strip()
        if not clean:
            raise MainImageApiError(f"{label}不能为空")
        return clean
