$ErrorActionPreference = "Stop"

if (-not $env:MAIN_IMAGE_MCP_HOST) { $env:MAIN_IMAGE_MCP_HOST = "127.0.0.1" }
if (-not $env:MAIN_IMAGE_MCP_PORT) { $env:MAIN_IMAGE_MCP_PORT = "8767" }

python "$PSScriptRoot\main_image_server.py" http
