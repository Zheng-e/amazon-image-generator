from __future__ import annotations

import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


MCP_SERVER_DIR = Path(__file__).resolve().parents[1] / "mcp-server"
sys.path.insert(0, str(MCP_SERVER_DIR))

import main_image_server  # noqa: E402
import rag_server  # noqa: E402


MAIN_IMAGE_TOOLS = {
    "create_main_image_project",
    "upload_project_assets",
    "initialize_nine_image_workflow",
    "generate_nine_image_suite",
    "get_nine_image_workflow",
    "regenerate_nine_image_step",
    "download_nine_image_suite",
    "search_rag_references",
    "add_rag_reference_to_project",
    "copy_rag_reference_to_project_asset",
}

RAG_TOOLS = {
    "search_knowledge_images",
    "search_knowledge_images_by_image",
    "add_knowledge_image",
    "list_knowledge_records",
    "get_knowledge_image_url",
    "get_knowledge_base_health",
}


def test_servers_register_expected_tools():
    async def list_tools():
        return (
            {tool.name for tool in await main_image_server.mcp.list_tools()},
            {tool.name for tool in await rag_server.mcp.list_tools()},
        )

    main_tools, rag_tools = anyio.run(list_tools)
    assert main_tools == MAIN_IMAGE_TOOLS
    assert rag_tools == RAG_TOOLS


def test_stdio_transports_initialize_and_list_tools():
    async def list_stdio_tools(server_file: str):
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(MCP_SERVER_DIR / server_file), "stdio"],
            cwd=str(MCP_SERVER_DIR),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return {tool.name for tool in result.tools}

    assert anyio.run(list_stdio_tools, "main_image_server.py") == MAIN_IMAGE_TOOLS
    assert anyio.run(list_stdio_tools, "rag_server.py") == RAG_TOOLS
