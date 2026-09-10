# Reliability Copilot — frontend

Angular 21 chat UI for the local Reliability Copilot. Single page: thread, composer (Enter to send, Shift+Enter for a new line), attachments, provider badge + Chat Settings (Ollama, LM Studio, llama.cpp, LiteRT-LM, Unsloth, OpenAI, custom) with test-connection, model dropdown with refresh + manual id entry, multi-session history with search, per-message copy / edit-and-resend / regenerate, timestamps + model labels + response stats, stop-generating, foldable thinking, Weibull plots, export (Markdown/HTML/PDF), and markdown with MathJax (`\sb{...}` for subscripts so markdown does not eat `_`).

Editor selection/pin/apply features from MDLithe were intentionally not ported — this app has no editor pane.

The UI talks to the FastAPI backend. It does not compute Weibull or search the knowledge base itself.

## Development

Needs Node.js and npm. From `frontend/`:

```powershell
npm install
npm start
```

`npm start` runs `ng serve` on `http://localhost:4200`. `proxy.conf.json` forwards `/api`, `/static`, and `/health` to `http://localhost:8000`, so run the backend first (`cd backend` then `uv run python main.py`).

## Production (served by FastAPI)

From the repo root:

```powershell
.\scripts\build_ui.ps1
```

That runs `npm run build` (production) and copies `dist/frontend/browser` into `backend/static/ui`. Then `uv run python main.py` serves the UI at `http://localhost:8000`.

## Format

Prettier options live in `package.json` (`printWidth` 100, `singleQuote`, Angular HTML parser). Prettier is not an npm dependency; use a one-off run from `frontend/`:

```powershell
npx --yes prettier@3 --write "src/**/*.{ts,html,css,json}" "angular.json" "package.json" "tsconfig.json" "tsconfig.app.json" "proxy.conf.json"
```

Check without writing:

```powershell
npx --yes prettier@3 --check "src/**/*.{ts,html,css,json}" "angular.json" "package.json" "tsconfig.json" "tsconfig.app.json" "proxy.conf.json"
```

Do not format `dist/`, `node_modules/`, or `.angular/`.

## Notes

- Chat uses `POST /api/chat/stream` (`prompt`, `model`, `thinking`). Models come from `GET /api/models` (provider-aware, Ollama `/api/tags` fallback). Provider config lives in `GET/PUT /api/llm/config`, connection probe in `POST /api/llm/test`.
- UI icons are Material Symbols Outlined via Google Fonts (`<app-icon name="…" />`, see `src/app/components/icon/icon.ts`), loaded from CDN like MathJax — offline builds still compile, but glyphs need network at runtime.
- MathJax is loaded in `src/index.html` (not KaTeX). The app has no Angular router.
- `npm run watch` rebuilds in development configuration without the proxy.
