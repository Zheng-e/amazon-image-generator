# Main Image Sidecar MCP and Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an isolated sidecar package that exposes the existing nine-image generation project and the existing image RAG service through standard stdio and Streamable HTTP MCP transports, plus one Agent-readable Skill.

**Architecture:** Keep both existing codebases unchanged. Add two small HTTP adapters and two `FastMCP` servers under `standardization/`: one server for nine-image project workflows and one server for the RAG knowledge base. Add one `main-image-suite` Skill that guides Agents through RAG search, project setup, nine-image generation, progress tracking, retries, and download.

**Tech Stack:** Python 3, `requests`, MCP Python SDK `FastMCP`, `pytest`, PowerShell launch scripts, Markdown Skill format.

---

## File Structure

```text
standardization/
  mcp-server/
    .env.example
    requirements.txt
    main_image_api.py
    rag_api.py
    main_image_server.py
    rag_server.py
    start_main_image_stdio.ps1
    start_main_image_http.ps1
    start_rag_stdio.ps1
    start_rag_http.ps1
    client-config.example.json
  skills/
    main-image-suite/
      SKILL.md
      agents/openai.yaml
      references/api-guide.md
  tests/
    test_main_image_api.py
    test_rag_api.py
    test_mcp_servers_smoke.py
```

## Task 1: Main Image API Adapter

- [x] Write failing tests for project creation, material upload, workflow initialization, full generation, workflow status, single-step retry, ZIP download, RAG proxy search, RAG reference selection, RAG-to-asset copy, absolute-path checks, and HTTP error conversion.
- [x] Run the adapter test and confirm it fails because `main_image_api.py` does not exist.
- [x] Implement `MainImageApiClient` using only the existing main image FastAPI endpoints.
- [x] Run the adapter test and confirm all tests pass.

## Task 2: RAG API Adapter

- [x] Write failing tests for text search, image search, image ingest, record listing, URL generation, health check, absolute-path checks, and HTTP error conversion.
- [x] Run the adapter test and confirm it fails because `rag_api.py` does not exist.
- [x] Implement `RagApiClient` using only the existing `D:\RAG` FastAPI endpoints.
- [x] Run the adapter test and confirm all tests pass.

## Task 3: MCP Servers and Launchers

- [x] Write failing smoke tests for the registered tool names and both stdio handshakes.
- [x] Run the smoke test and confirm it fails because server files do not exist.
- [x] Implement one `FastMCP` server per capability domain.
- [x] Add independent stdio and Streamable HTTP launch scripts.
- [x] Add environment and MCP client configuration examples.
- [x] Run smoke tests and verify both stdio servers initialize.
- [x] Start both HTTP MCP servers on temporary ports and verify Streamable HTTP handshakes.

## Task 4: Agent Skill

- [x] Initialize the standard `main-image-suite` Skill scaffold.
- [x] Write concise workflow instructions for nine-image planning, reference-image boundaries, consistency protection, product suite generation, failure handling, and result download.
- [x] Document both MCP servers and expected tool usage in `references/api-guide.md`.
- [x] Generate UTF-8 `agents/openai.yaml`.
- [x] Run the Skill validator.

## Task 5: Full Verification

- [x] Run `python -m pytest standardization/tests -q`.
- [x] Run `python -m pytest -q` for the existing main image project.
- [x] Check `http://127.0.0.1:8010/health` and confirm the RAG service remains healthy.
- [x] Run `git diff --check`.
- [x] Confirm changes are limited to `standardization/` and this plan.
