# Reliability Copilot — 15 minutes

Private copilot for reliability questions. Commercial solvers (ReliaSoft Weibull++, nCode, Minitab) stay optional via MCP later. This is **not** a ReliaSoft replacement.

## Run (hiring-manager demo)

From `backend/`:

```powershell
uv sync --all-groups
uv run python demo_copilot.py
```

That script always runs the **tools** (Weibull paper, B10 vs 200 h warranty, knowledge cite, `static/demo_report.md`). Those numbers do **not** go through the LLM — that is intentional, so an interview still works if llama.cpp is down.

If `LLM_API_BASE` in `.env` is already serving (your local OpenAI-compatible model), the same command then asks the agent one warranty question. You do **not** need a second process for that one-shot. Skip the LLM with `uv run python demo_copilot.py --no-llm`.

The **browser chat UI** still needs `uv run python main.py` (FastAPI). `.env` is loaded from the repo root; having the file is not the same as having the model server listening on that URL.

```powershell
copy ..\.env.example ..\.env
uv run python main.py
```

Open `http://localhost:8000`. If the Angular app is not built yet, run `..\scripts\build_ui.ps1` first, or `ng serve` in `frontend/` (proxies `/api`).

Ask:

> Fit Weibull to failures 150, 180, 220, 310, 400, 520, 610, 780 with suspensions 800, 800, 1000. Does B10 cover a 200 hour warranty? Cite our Weibull notes.

Metrics come from tools, not from the model.

## Python 3.12+ with uv

```powershell
cd backend
uv sync --all-groups
```

Copy `.env.example` to `.env` at the repository root. Keep real credentials only in `.env`.

Optional: `scripts/start.ps1` from the repo root, or `scripts/start-desktop.ps1` for the WebView wrapper. Tests: `uv run pytest`.

Settings: `LLM_API_KEY`, `FRONTEND_ORIGIN` (comma-separated), `PUBLIC_BASE_URL` (leave empty for same-origin `/static` URLs), `PORT`, `EMBEDDING_MODEL`.

## Knowledge base

Accepted files: `.md`, `.txt`, `.pdf`, `.doc`, `.docx`, `.ppt`, `.pptx`. Drop files into `Knowledge_Base/` or attach them on the chat prompt. Docling extracts PDF and Office files locally.

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

Host: `uv run python mcp_server.py` (see `mcp_llamacpp.json`).

## Chat API

- `POST /api/chat` and `POST /api/chat/stream`
- `GET /api/knowledge/status` and `POST /api/knowledge/upload`
