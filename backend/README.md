# Reliability Copilot — backend

Private reliability engineering agent: FastAPI host, MCP tools, Weibull paper, hybrid RAG. Python **3.12+**, managed with **uv** (`pyproject.toml`). Copy `.env.example` to `.env` at the **repository root**. Having the file is not the same as having the model server listening on `LLM_API_BASE`.

## Run

```powershell
copy ..\.env.example ..\.env
uv sync --all-groups
uv run python main.py
```

Open `http://localhost:8000`. If the Angular app is not built yet, run `..\scripts\build_ui.ps1` first, or `ng serve` in `frontend/` (proxies `/api`, `/static`, and `/health` to this process).

Ask:

> Fit Weibull to failures 150, 180, 220, 310, 400, 520, 610, 780 with suspensions 800, 800, 1000. Does B10 cover a 200 hour warranty? Cite our Weibull notes.

Metrics come from tools, not from the model.

Optional: `scripts/start.ps1` from the repo root, or `scripts/start-desktop.ps1` for the WebView wrapper.

Settings: `LLM_API_BASE`, `LLM_API_KEY`, optional `LLM_MODEL` (only if it appears in `GET {base}/models`), `FRONTEND_ORIGIN` (comma-separated), `PUBLIC_BASE_URL` (leave empty for same-origin `/static` URLs), `PORT`, `EMBEDDING_MODEL`.

## Lint and format

Ruff is configured in `pyproject.toml` (line length 100; rules `E`, `F`, `I`, `W`, `UP`). From `backend/`:

```powershell
uvx ruff format .
uvx ruff check .
```

Auto-fix safe issues (import order and the selected rules):

```powershell
uvx ruff check . --fix
```

Pylint-style complexity and magic-number rules are not enabled. Fixing them would mean splitting APIs, eager-loading optional imports (Docling, LlamaIndex, WebView), or renaming numeric thresholds.

Tests: `uv run pytest`.

## Knowledge base

Accepted files: `.md`, `.txt`, `.pdf`, `.doc`, `.docx`, `.ppt`, `.pptx`. Drop files into `Knowledge_Base/` (repo root) or attach them on the chat prompt. Docling extracts PDF and Office files locally. The vector index lives under `backend/.rag`.

```powershell
uv run python knowledge_base.py
uv run python knowledge_base.py --download-model
```

## MCP tools

- `search_reliability_knowledge(query, max_results)`
- `analyze_weibull(failure_times, title, censored_times, method, confidence)` — `method` is `rry` (default) or `mle`
- `calculate_b_life(beta, eta, percentage)`
- `export_reliability_report(...)` — one-page markdown from tool numbers
- plugin `calculate_mtbf`

Plugins: `backend/plugins/<name>.py` with `def register(mcp):`. Extra stdio servers: `backend/mcp_servers.json`.

Host: `uv run python mcp_server.py`.

## HTTP API

- `GET /health`
- `GET /api/models`
- `GET /api/knowledge/status` and `POST /api/knowledge/upload`
- `POST /api/chat` and `POST /api/chat/stream` — body includes `prompt`, `model`, and `thinking`
