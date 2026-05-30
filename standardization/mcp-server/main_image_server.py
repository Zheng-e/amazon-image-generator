from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from main_image_api import MainImageApiClient


API_BASE_URL = os.getenv("MAIN_IMAGE_API_BASE_URL", "http://127.0.0.1:8020")
MCP_HOST = os.getenv("MAIN_IMAGE_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MAIN_IMAGE_MCP_PORT", "8767"))

api = MainImageApiClient(API_BASE_URL)
mcp = FastMCP(
    "Main Image Suite Task MCP",
    instructions="Use these tools to prepare project assets, run the fixed nine-image workflow, track progress, retry a single image, and download the completed suite.",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def create_main_image_project(sku: str, user_id: str = "default", category: str = "", name: str = "", notes: str = "") -> dict[str, Any]:
    """Create one product project before uploading references or generating a nine-image suite."""
    return api.create_main_image_project(sku, user_id=user_id, category=category, name=name, notes=notes)


@mcp.tool()
def upload_project_assets(
    project_id: str,
    asset_type: str,
    file_paths: list[str],
    source_url: str = "",
    asin: str = "",
    keyword: str = "",
    slot: str = "",
    notes: str = "",
) -> list[dict[str, Any]]:
    """Upload product, model, fit, scene, accessory, or competitor reference images from absolute paths."""
    return api.upload_project_assets(project_id, asset_type, file_paths, source_url=source_url, asin=asin, keyword=keyword, slot=slot, notes=notes)


@mcp.tool()
def initialize_nine_image_workflow(
    project_id: str,
    product_name: str,
    material: str,
    product_asset_id: str,
    accessory_asset_id: str,
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
    """Initialize the existing fixed nine-image workflow using uploaded asset IDs."""
    return api.initialize_nine_image_workflow(
        project_id,
        product_name,
        material,
        product_asset_id,
        accessory_asset_id,
        style_key=style_key,
        model_asset_id=model_asset_id,
        fit_front_asset_id=fit_front_asset_id,
        fit_side_asset_id=fit_side_asset_id,
        fit_back_asset_id=fit_back_asset_id,
        scene_asset_id=scene_asset_id,
        image_model=image_model,
        size=size,
        quality=quality,
    )


@mcp.tool()
def generate_nine_image_suite(project_id: str, image_model: str = "", size: str = "", quality: str = "") -> dict[str, Any]:
    """Start background generation for the complete nine-image product suite."""
    return api.generate_nine_image_suite(project_id, image_model=image_model, size=size, quality=quality)


@mcp.tool()
def get_nine_image_workflow(project_id: str) -> dict[str, Any]:
    """Get current status and result details for all nine images."""
    return api.get_nine_image_workflow(project_id)


@mcp.tool()
def regenerate_nine_image_step(step_id: str, image_model: str = "", size: str = "", quality: str = "") -> dict[str, Any]:
    """Regenerate one failed or unsatisfactory image step."""
    return api.regenerate_nine_image_step(step_id, image_model=image_model, size=size, quality=quality)


@mcp.tool()
def download_nine_image_suite(project_id: str, output_path: str, overwrite: bool = False) -> dict[str, Any]:
    """Download the complete nine-image ZIP result to an absolute path."""
    return api.download_nine_image_suite(project_id, output_path, overwrite=overwrite)


@mcp.tool()
def search_rag_references(query: str, top_k: int = 8, offset: int = 0, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Search reference images through the main-image service RAG proxy."""
    return api.search_rag_references(query, top_k=top_k, offset=offset, filters=filters)


@mcp.tool()
def add_rag_reference_to_project(
    project_id: str,
    rag_image_id: str,
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
    """Select one RAG image as a named reference for a project."""
    return api.add_rag_reference_to_project(
        project_id,
        rag_image_id,
        filename=filename,
        category=category,
        scene=scene,
        image_type=image_type,
        caption=caption,
        score=score,
        usage_tags=usage_tags,
        metadata=metadata,
        model_description=model_description,
        asset_type=asset_type,
        rag_role=rag_role,
        notes=notes,
    )


@mcp.tool()
def copy_rag_reference_to_project_asset(
    project_id: str,
    rag_image_id: str,
    filename: str = "",
    slot: str = "",
    rag_role: str = "",
    model_description: str = "",
) -> dict[str, Any]:
    """Copy one RAG image into the project asset area for workflow use."""
    return api.copy_rag_reference_to_project_asset(project_id, rag_image_id, filename=filename, slot=slot, rag_role=rag_role, model_description=model_description)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the main-image suite sidecar MCP server.")
    parser.add_argument("transport", nargs="?", choices=("stdio", "http", "streamable-http"), default="stdio")
    args = parser.parse_args()
    mcp.run(transport="streamable-http" if args.transport == "http" else args.transport)


if __name__ == "__main__":
    main()
