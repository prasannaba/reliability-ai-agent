# Reliability Copilot — frontend

React 19 + TypeScript + Bootstrap 5 + React-Bootstrap chat UI for the local Reliability Copilot. Single page: thread, composer (Enter to send, Shift+Enter for a new line), attachments, provider badge + Chat Settings (Ollama, LM Studio, llama.cpp, LiteRT-LM, Unsloth, OpenAI, custom) with test-connection, model dropdown with refresh + manual id entry, multi-session history with search, per-message copy / edit-and-resend / regenerate, timestamps + model labels + response stats, stop-generating, foldable thinking, Weibull plots, export (Markdown/HTML/PDF), and markdown (react-markdown + GFM) with MathJax (`\sb{...}` for subscripts so markdown does not eat `_`).

The UI talks to the FastAPI backend. It does not compute Weibull or search the knowledge base itself.

## Development — live updates with `npm run dev`

Needs Node.js and npm. From `frontend/`:

```powershell
npm install
npm run dev
```

`npm run dev` starts the Vite dev server on `http://localhost:4200` **with hot reload** — edits to `src/` refresh live in the browser. `vite.config.ts` proxies `/api`, `/static`, and `/health` to `http://localhost:8000`, so run the backend first (`cd backend` then `.\.venv\Scripts\python.exe main.py`).

Other scripts: `npm run build` (typecheck + production build), `npm run preview` (serve the built output locally), `npm test` (Vitest unit tests).

## Production (served by FastAPI)

From the repo root:

```powershell
.\scripts\build_ui.ps1
```

That runs `npm run build` and copies `dist/frontend/browser` into `backend/static/ui`. Then start the backend to serve the UI at `http://localhost:8000`.

## Notes

- Chat uses `POST /api/chat/stream` (`prompt`, `model`, `thinking`). Models come from `GET /api/models` (provider-aware, Ollama `/api/tags` fallback). Provider config lives in `GET/PUT /api/llm/config`, connection probe in `POST /api/llm/test`. The active domain pack comes from `GET /api/domains` (badge in the sidebar, title in the hero) and its MCP tool inventory from `GET /api/mcp/tools` (listed in Settings → Domain & tools).
- UI icons are Bootstrap Icons via `react-bootstrap-icons` (`<Icon name="…" />`, see `src/components/Icon.tsx`).
- Theming: CSS variables in `src/styles.css` (`:root` light, `[data-theme="dark"]` dark) plus Bootstrap's built-in dark mode via `data-bs-theme`. Preference lives in `src/hooks/useTheme.ts` (System/Light/Dark, persisted as `reliability-copilot-theme`, default System following the OS) with a switcher in the Settings panel (`src/components/ThemeToggle.tsx`).
- MathJax is vendored at `public/mathjax/` (no CDN at runtime) and loaded in `index.html`. The app has no router.
- Source layout: `src/services/` (platform boundary — see below), `src/components/` (Sidebar, MessageItem, Composer, ModelPicker, SettingsPanel, ThemeToggle, ConfirmDialog, Icon), `src/hooks/` (`useSessions`, `useTheme`), `src/pages/ChatPage.tsx`, `src/types/`, `src/utils/`.

## Service layer

UI components are platform-independent; all backend and native-capability access goes through the service boundary in `src/services/`:

- `src/services/types.ts` — `BackendService` (agent/knowledge/model ops) and `PlatformService` (storage, clipboard, file download, print) interfaces. Components import only these plus the `getServices()` singleton (`src/services/index.ts`).
- `src/services/browser/` — `httpApi.ts` (HTTP/API → FastAPI backend, same-origin or `VITE_BACKEND_URL`), `capabilities.ts` (Web APIs: clipboard/downloads/print/storage).
- `src/services/http.ts` — shared fetch + SSE plumbing.

The React app never speaks MCP directly — the Python backend (stdio MCP server + FastAPI) does that.
