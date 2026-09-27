# Reliability Copilot — backend

Private engineering agent: generic FastAPI MCP host + pluggable domain MCP servers (reliability, physics, ...). Python **3.12+**, managed with **uv** (`pyproject.toml`). Copy `.env.example` to `.env` at the **repository root**. Having the file is not the same as having the model server listening on `LLM_API_BASE`.

## Layout

```
backend/
  src/
    host/               generic FastAPI host (no domain code)
      app.py            chat/LLM/agent endpoints; ACTIVE_DOMAIN-driven
      mcp_pool.py       MultiMCPClient (stdio + SSE + streamable HTTP)
      domain_registry.py ACTIVE_DOMAIN → domain pack + server list
    common/             credential_store, rate_limit, markdown_math
    knowledge/base.py   GenericKnowledgeBase (Chroma + BM25)
    domains/
      reliability/      server.py, tools/, plugins/, prompt.md, domain.yaml
      physics/          example second domain (same shape)
  config/               mcp_servers.<domain>.json (server lists)
```
(no root-level shims — everything lives under `src/`; run with `python -m` from `backend/`).

Swap domains with `ACTIVE_DOMAIN=physics` — no host edits. Serve a domain standalone over HTTP for Open Web UI / Unsloth Studio:

```powershell
uv run python -m src.domains.reliability.server --transport streamable-http --port 8001
# tools at http://localhost:8001/mcp
```

## Run

```powershell
copy ..\.env.example ..\.env
uv sync --all-groups
uv run python -m src.host.app
```

Open `http://localhost:8000`. If the React app is not built yet, run `..\scripts\build_ui.ps1` first, or `npm run dev` in `frontend/` (proxies `/api`, `/static`, and `/health` to this process).

Ask:

> Fit Weibull to failures 150, 180, 220, 310, 400, 520, 610, 780 with suspensions 800, 800, 1000. Does B10 cover a 200 hour warranty? Cite our Weibull notes.

Metrics come from tools, not from the model.

## Scripts (repo `scripts/`, `.ps1` + `.sh` pairs)

| Script | Purpose |
| --- | --- |
| `run` | Build UI if missing, then serve the host (`-Domain` / `--domain=` selects the pack) |
| `start` | Serve the host directly (same domain flag) |
| `dev` | Host (:8000) + Vite (:4200) together (same domain flag) |
| `mcp` | Serve one domain MCP standalone: `-Transport stdio\|sse\|streamable-http -Port …` (HTTP URL for Open Web UI / Unsloth) |
| `index` | Build/refresh a domain knowledge index (`-Domain`, `-DownloadModel`, `-Force`) |
| `build_ui` | Build React UI into `backend/static/ui` |
| `start-desktop` | Host + desktop WebView window |

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

Accepted files: `.md`, `.txt`, `.pdf`, `.doc`, `.docx`, `.ppt`, `.pptx`. Drop files into `knowledge-base/` (repo root) or attach them on the chat prompt. Docling extracts PDF and Office files locally. The vector index lives under `backend/.rag`.

```powershell
uv run python -m src.knowledge.base
uv run python -m src.knowledge.base --download-model
```

## MCP tools (reliability domain)

- `search_reliability_knowledge(query, max_results)`
- `analyze_weibull(failure_times, title, censored_times, method, confidence)` — `method` is `rry` (default) or `mle`
- `calculate_b_life(beta, eta, percentage)`
- `export_reliability_report(...)` — one-page markdown from tool numbers
- plugin `calculate_mtbf`

Physics domain (template): `projectile_motion`, `kinetic_energy`, `search_physics_knowledge`, plugin `convert_units`.

Plugins: `backend/src/domains/<name>/plugins/<tool>.py` with `def register(mcp):`. Server lists: `backend/config/mcp_servers.<domain>.json` (stdio `command/args` or HTTP `url` entries).

Standalone hosts:

```powershell
uv run python -m src.domains.reliability.server --transport stdio
uv run python -m src.domains.reliability.server --transport streamable-http --port 8001
```

Host introspection: `GET /health` (now includes `domain`), `GET /api/domains`, `GET /api/mcp/tools`.

## HTTP API

- `GET /health`
- `GET /api/models`
- `GET /api/knowledge/status` and `POST /api/knowledge/upload`
- `POST /api/chat` and `POST /api/chat/stream` — body includes `prompt`, `model`, and `thinking`
