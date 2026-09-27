# Backend + MCP Server — Simple Guide

This explains in plain language how the Python backend works, and how a question you type in the frontend turns into tool calculations.

## 1. The big idea in one sentence

**You ask in words. The LLM plans what to do. Python tools do all the math. The LLM only explains the result.**

The LLM is never allowed to invent numbers like β (beta), η (eta), MTBF, or B10 life. Those always come from code.

## 2. The 5 pieces

```
[Frontend: React chat]
   --sends prompt as text--> 
[Backend: src/host/app.py (generic FastAPI host, ACTIVE_DOMAIN selects the domain)]
   --asks-->
[Your LLM server (Ollama, llama.cpp, LM Studio, OpenAI, ...)]
   --decides to call a tool-->
[MCP Client: src/host/mcp_pool.py (MultiMCPClient: stdio + SSE + streamable HTTP)]
   --stdio pipe (local dev) or HTTP (shared/external)-->
[MCP Server: src/domains/<name>/server.py + tools/]
```

1. **Frontend (`frontend/src/`)** — Just a chat box. It sends `{ prompt, model, thinking }` to `POST /api/chat/stream` and shows the streamed answer. It never runs Weibull math.
2. **Backend host (`backend/src/host/app.py`)** — A generic FastAPI web server. It owns the chat endpoints, talks to the LLM, and holds the MCP client. It has no reliability-specific code: the system prompt comes from `src/domains/<active>/prompt.md` and the server list from `backend/config/mcp_servers.<active>.json` (`ACTIVE_DOMAIN` env, default `reliability`).
3. **LLM (your own server)** — Any OpenAI-compatible model. It reads, reasons, and chooses which tool to call.
4. **MCP Client (`backend/src/host/mcp_pool.py`)** — A bridge. It starts/connects the configured MCP servers and translates tool calls back and forth. Entries with `command/args` spawn a local subprocess; entries with `url` connect over SSE / streamable HTTP.
5. **MCP Server (`backend/src/domains/reliability/server.py`)** — Where the real work happens: Weibull fit, B-life, MTBF, report, knowledge search. Standalone: `python -m src.domains.reliability.server --transport streamable-http --port 8001` exposes the same tools at `http://localhost:8001/mcp` for Open Web UI / Unsloth Studio — no FastAPI involved.

## 3. How the backend code is organized

| Path | Job in simple words |
|------|---------------------|
| `src/host/app.py` | The waiter. Receives your prompt from frontend, creates the AI agent, sends events back as SSE stream (`token`, `thought`, `tool_start`, `tool_end`, `image`, `done`). Also serves plots from `static/` and the built UI. Domain-agnostic. |
| `src/host/mcp_pool.py` | The phone line (`MultiMCPClient`). Connects configured MCP servers (stdio subprocess or HTTP), lists their tools, converts them to LlamaIndex `FunctionTool`s so the LLM can call them, and forwards arguments/results as JSON. |
| `src/host/domain_registry.py` | The switchboard. Resolves `ACTIVE_DOMAIN` → `src/domains/<name>/{domain.yaml,prompt.md}` + `config/mcp_servers.<name>.json`. Swapping domains is config, not code. |
| `src/domains/reliability/server.py` | The toolbox. Registers 4 tools with `@mcp.tool()` plus `plugins/`. Runs standalone (`--transport stdio|sse|streamable-http`). |
| `src/domains/reliability/tools/` | Tool implementations: `weibull.py`, `blife.py`, `report.py`, `knowledge_tool.py` (+ `_common.py`). |
| `src/domains/reliability/{weibull_fit,life_data_analysis_weibull,reliability_report}.py` | The math brain (ranks, RRY/MLE, B-life, bootstrap), the artist (probability-paper `.png` → `static/`), the writer (one-page markdown report). |
| `src/knowledge/base.py` | The librarian (`GenericKnowledgeBase`): reads per-domain KB dirs, builds Chroma + BM25 index (`backend/.rag/`, `.rag-physics/`), hybrid-searches them. |
| `src/domains/reliability/plugins/mtbf.py` | Example plugin. Any file with `def register(mcp):` auto-adds a new tool. No change to `server.py` needed. |
| `config/mcp_servers.<domain>.json` | Server list per domain (`${PYTHON}`/`${BACKEND_DIR}` placeholders allowed). `url` entries connect over HTTP instead of spawning a process. |
| `src/common/` | Domain-free utilities: `credential_store.py`, `rate_limit.py`, `markdown_math.py` (fixes `\sb{...}` LaTeX so markdown doesn't break subscripts). |
| `static/` | Plots (`.png`) + report (`.md`) + built React UI (`static/ui`). |
| `desktop_app.py` | Local launcher: serves the app and opens it in a desktop WebView window. |

## 3b. Swapping domains: Reliability → Physics with no host changes

1. The `physics` pack already exists: `src/domains/physics/` (`server.py`, `tools/kinematics.py`, `plugins/units.py`, `prompt.md`, `domain.yaml`) + `config/mcp_servers.physics.json`.
2. Run the host with `ACTIVE_DOMAIN=physics` — chat, prompt, tools, and KB collection (`physics_knowledge` in `backend/.rag-physics/`) all switch; `src/host/` is untouched.
3. Serve it standalone: `python -m src.domains.physics.server --transport streamable-http --port 8002`, or `docker compose --profile physics up --build`.
4. Copy the pack to start your own domain: new folder under `src/domains/`, new JSON under `config/`, set `ACTIVE_DOMAIN`.

## 4. The MCP tools (what the LLM can actually call)

| Tool | Input | Output | Simple meaning |
|------|-------|--------|----------------|
| `analyze_weibull` | `failure_times`, optional `censored_times` (suspensions), `method=rry/mle`, `confidence` | β, η, MTBF, B10/B20, plot filename, ranks | "Fit the data and draw the paper plot." |
| `calculate_b_life` | `beta, eta, percentage` | one number | "At what hours will X% have failed?" e.g. B10 = 10% failed. |
| `calculate_mtbf` (plugin) | `failure_times`, optional `censored_times` | mtbf, failure_rate | "Average life" from total time / failures. |
| `search_reliability_knowledge` | `query` | text chunks + citations | "What do our own notes say?" |
| `export_reliability_report` | same as analyze + `question`, `warranty_hours` | markdown + file | "Make the one-page report that matches the plot." |

`analyze_weibull` and `export_reliability_report` additionally return the plot PNG as an MCP image block, so external clients (Unsloth Studio, VS Code, Claude Desktop) render the graph inline instead of just JSON. Our own UI keeps its existing flow (filename → `/static/` URL → image event).

All NumPy/Path values are cleaned to plain JSON by `json_safe()` (`tools/_common.py`) before returning.

## 5. Step-by-step: what happens when you ask a question

Example prompt:

> Fit Weibull to failures 150, 180, 220, 310 with suspensions 800, 800. Does B10 cover 200h warranty?

1. **Frontend → Backend:** `httpApi.ts: streamMessage()` does `POST /api/chat/stream` with `{ prompt: "Fit Weibull..." }`.
2. **Backend builds agent (only once per model):** `src/host/app.py: apply_chat_model()` → `build_agent()` creates a `ReActAgent` with:
   - `system_prompt` = the active domain's `prompt.md` (reliability: strict rule "Never invent β, η, B-life. Always call tools."), plus operator `systemPrompt` override when set.
   - `tools` = `await mcp_client.llama_tools()` (the 5 tools above).
   - `llm` = `OpenAILike` pointing at your `LLM_API_BASE`.
3. **LLM thinks:** The ReAct loop produces `Thought: I need to call analyze_weibull...`
4. **Tool call goes through client → server:**
   - LlamaIndex calls the wrapper function in `mcp_pool.py:_to_llama_tool()`.
   - That calls `session.call_tool("analyze_weibull", {...})` over stdio (or HTTP when the entry has a `url`).
   - `domains/reliability/tools/weibull.py: analyze_weibull()` validates inputs, calls `plot_weibull_analysis()` under `PLOT_LOCK`, saves e.g. `weibull_abc123.png` in `static/`, returns JSON.
5. **LLM may call more tools:** e.g. `calculate_b_life(beta, eta, 10)` to get B10, `search_reliability_knowledge("warranty")` for citations.
6. **Backend streams back to frontend:** `src/host/app.py: stream_agent_events()` yields SSE events:
   - `tool_start` / `tool_end` → frontend shows "calling analyze_weibull..."
   - `thought` → foldable "thinking" panel
   - `token` → the visible answer words
   - `image` → plot URL like `/static/weibull_abc123.png` found by `infer_latest_image_url()`
   - `done` → final text + image_url
7. **Frontend renders:** Markdown + MathJax + plot image. Copy / regenerate / export buttons are UI-only.

If a tool can't run, the system prompt forces the LLM to say "I cannot give a number" instead of guessing.

## 6. Why two processes (host + MCP server)?

- The host and each domain MCP server are **separate programs**. Locally they talk over a stdio pipe (like a private chat line); deployed/shared they talk HTTP.
- Benefit: a domain server runs standalone (`--transport streamable-http`), gains plugins, or is consumed by external hosts (Open Web UI, Unsloth Studio) without touching the web host.
- `MultiMCPClient.start()` connects at startup (FastAPI `lifespan`), `close()` shuts down.

## 7. How to add a new calculation

1. Create `backend/src/domains/reliability/plugins/my_tool.py`:
   ```python
   def register(mcp):
       @mcp.tool()
       def my_calc(x: float) -> float:
           """What it does in plain words."""
           return x * 2
   ```
2. Restart backend. `load_plugins(mcp)` auto-loads it. No frontend change needed — the LLM will see the new tool description automatically.

## 8. Cheat-sheet diagram

```
Type prompt in React UI
        |
        v
POST /api/chat/stream  (frontend/src/services/browser/httpApi.ts)
        |
        v
app.py: ReActAgent + domain prompt.md ("don't invent numbers")
        |
        v
LLM decides: "call analyze_weibull"
        |
        v
mcp_pool.py: call_tool() over stdio (or HTTP)
        |
        v
domains/reliability: server.py → tools/ → weibull_fit.py + life_data_analysis_weibull.py
        |  saves static/*.png
        v
JSON result back to LLM → LLM writes explanation
        |
        v
SSE stream → frontend shows text + plot
```
