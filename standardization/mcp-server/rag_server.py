from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from rag_api import RagApiClient


API_BASE_URL = os.getenv("RAG_API_BASE_URL", "http://127.0.0.1:8010")
MCP_HOST = os.getenv("RAG_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("RAG_MCP_PORT", "8768"))

api = RagApiClient(API_BASE_URL)
mcp = FastMCP(
    "Image Knowledge Base MCP",
    instructions="Use these tools to add approved images to the image knowledge base and retrieve reference images for main-image generation.",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def search_knowledge_images(query: str, top_k: int = 5, offset: int = 0, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Search the image knowledge base using a natural-language description."""
    return api.search_knowledge_images(query, top_k=top_k, offset=offset, filters=filters)


@mcp.tool()
def search_knowledge_images_by_image(image_path: str, query: str = "", top_k: int = 5, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Search for similar references using an absolute local image path and optional text."""
    return api.search_knowledge_images_by_image(image_path, query=query, top_k=top_k, filters=filters)


@mcp.tool()
def add_knowledge_image(
    image_path: str,
    category: str = "unknown",
    scene: str = "unknown",
    image_type: str = "product",
    compliance: str = "approved",
    asset_type: str = "other",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add one approved image to the knowledge base using an absolute path."""
    return api.add_knowledge_image(image_path, category=category, scene=scene, image_type=image_type, compliance=compliance, asset_type=asset_type, metadata=metadata)


@mcp.tool()
def list_knowledge_records(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """List stored knowledge-base image records."""
    return api.list_knowledge_records(limit=limit, offset=offset)


@mcp.tool()
def get_knowledge_image_url(image_id: str) -> str:
    """Return the HTTP URL for one knowledge-base image."""
    return api.get_knowledge_image_url(image_id)


@mcp.tool()
def get_knowledge_base_health() -> dict[str, Any]:
    """Check the image knowledge-base service status."""
    return api.get_knowledge_base_health()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the image knowledge-base sidecar MCP server.")
    parser.add_argument("transport", nargs="?", choices=("stdio", "http", "streamable-http"), default="stdio")
    args = parser.parse_args()
    mcp.run(transport="streamable-http" if args.transport == "http" else args.transport)


if __name__ == "__main__":
    main()
