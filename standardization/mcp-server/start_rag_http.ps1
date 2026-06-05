$ErrorActionPreference = "Stop"

if (-not $env:RAG_MCP_HOST) { $env:RAG_MCP_HOST = "127.0.0.1" }
if (-not $env:RAG_MCP_PORT) { $env:RAG_MCP_PORT = "8768" }

python "$PSScriptRoot\rag_server.py" http
