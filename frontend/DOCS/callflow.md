# Frontend ↔ Backend Call Flow and Per‑file Map

Summary
- This document maps each frontend file to its role and shows the exact sequence of calls when a user sends a message in the chat UI.
- Stack: React 19 + TypeScript + Vite. Dev server runs on http://localhost:4200 and proxies `/api`, `/static`, `/health` to the FastAPI backend at http://localhost:8000 (see `vite.config.ts`).
- Chat uses server-sent events: POST `/api/chat/stream` with `{ prompt, model, thinking }`, streamed back as `data: {...}` events (`token`, `thought`, `tool_start`, `tool_end`, `image`, `done`, `error`).
- On load the UI fetches `GET /api/domains` (active domain pack → sidebar badge + hero title) alongside models/config/knowledge; Settings → Domain & tools lists `GET /api/mcp/tools` (name + description per tool).

Per-file map (frontend)
- vite.config.ts
  - Role: Vite dev/build configuration. Dev proxy, pinned `:4200` port, `dist/frontend/browser` output layout (consumed by `scripts/build_ui.*`).
  - Importance: Keeps dev same-origin and the production bundle copy working.

- tsconfig.json
  - Role: TypeScript compiler options (strict).
  - Importance: `npm run build` type-checks before bundling (`tsc && vite build`).

- package.json / package-lock.json
  - Role: Dependencies and npm scripts (`dev`, `build`, `test` via vitest).
  - Importance: Reproducible installs and build/test scripts.

- src/main.tsx
  - Role: Entry point. Mounts `App` with the service layer.
  - Importance: Wires UI to the backend implementation.

- src/App.tsx
  - Role: Root component; renders `ChatPage`.
  - Importance: Minimal bootstrap for the chat UI.

- src/pages/ChatPage.tsx
  - Role: Chat screen: message thread, streaming orchestration, sessions/sidebar wiring, settings modal, export, empty-state hero, footer.
  - Importance: Owns `runCompletion()` (SSE event handling), `sendMessage()`, regenerate, edit-and-resend, plot download.

- src/components/Composer.tsx
  - Role: Prompt input (auto-growing textarea), attach button, model picker, send/stop buttons.
  - Importance: Enter-to-send, file attach for knowledge-base upload.

- src/components/MessageItem.tsx
  - Role: One chat turn: Markdown + MathJax rendering, plot image, thinking panel, copy/edit/regenerate actions.
  - Importance: Per-message rendering and actions.

- src/components/Sidebar.tsx
  - Role: Chat history list (only chats with a user message), new chat, search, provider badge, Settings entry.
  - Importance: Session navigation; empty chats stay out of the list.

- src/components/SettingsPanel.tsx
  - Role: Settings modal — Chat (provider/model/temperature/system prompt/export format), Appearance (theme), Delete history sections.
  - Importance: Single place for LLM endpoint config, theme, and destructive clear-all (with confirm).

- src/components/ModelPicker.tsx
  - Role: Model dropdown with manual id entry and refresh.
  - Importance: Model selection inside the composer.

- src/hooks/useSessions.ts
  - Role: Chat sessions with localStorage persistence (stable schema/keys — do not rename). Always lands on a fresh chat; strips legacy welcome bubbles on load.
  - Importance: Session CRUD, message updates, clear-all.

- src/hooks/useTheme.ts
  - Role: Theme preference (`system`/`light`/`dark`), applies `data-theme` + Bootstrap `data-bs-theme` on `<html>`.
  - Importance: Light/dark mode for app and Bootstrap components.

- src/services/* (http.ts, browser/httpApi.ts, types.ts)
  - Role: `BackendService` interface: models, LLM config, knowledge status/upload, `streamMessage()` SSE client, static-URL resolution.
  - Importance: Central place to change backend URL and streaming protocol.

- src/types/chat.ts, src/types/llm.ts
  - Role: `Message`/`ChatSession` shapes, LLM config/provider types, `WELCOME_MESSAGE` (empty-state hero text — display only, never stored as a message).
  - Importance: Consistent shapes across UI, sessions, and services.

- src/utils/* (format.ts, mathMarkdown.ts, mathjax.ts)
  - Role: Titles/timestamps/stats formatting, `\sb{...}` TeX repair, MathJax re-render.
  - Importance: Display helpers shared by thread and export.

- src/styles.css
  - Role: Global styles + light/dark theme tokens.
  - Importance: App-wide styling; new colors must define both themes.

Concrete call trace (step-by-step) — UI action: user submits a message

1. User types in `Composer` and presses Send (Enter).
   - `ChatPage.sendMessage()` validates non-empty input, appends the user message, clears the box.

2. `ChatPage.runCompletion(prompt)` opens the stream.
   - Creates an empty assistant draft, calls `backend.streamMessage(prompt, onEvent, signal, model, thinking)`.

3. `streamMessage()` — HTTP request (`src/services/browser/httpApi.ts` → `streamSse` in `src/services/http.ts`)
   - Method: POST
   - URL: `/api/chat/stream` (same origin in dev via proxy, backend origin in production)
   - Body (example):
     {
       "prompt": "Fit Weibull to failures 150, 180, 220, 310 with suspensions 800, 800",
       "thinking": true
     }

4. Network transit → Backend receives POST `/api/chat/stream`
   - Backend deterministically retrieves knowledge-base context for the prompt, runs the ReAct agent (LLM + MCP tools for Weibull math/plots), and streams SSE events:
     `{"type":"thought",...}`, `{"type":"tool_start",...}`, `{"type":"token",...}`, `{"type":"image",...}`, `{"type":"done",...}`.

5. `onEvent` in `runCompletion()` applies each event to the draft (tokens, thinking text, tool steps, plot URL) and re-renders via `requestAnimationFrame`, scrolling to bottom.

6. On finish: stats line is stamped, thinking panel collapses, MathJax re-renders.

Sequence summary (compact)
- UI submit → `sendMessage` (adds user message) → `runCompletion` POST `/api/chat/stream` → backend streams SSE (thought/tool/token/image/done) → draft updates per event → final content + stats rendered.

Notes and extension points
- CORS: dev is same-origin via Vite proxy; production UI is served by FastAPI itself (same origin).
- Knowledge upload: attach button → POST `/api/knowledge/upload`, auto-indexed on next search.
- Error schema: `{"type":"error","message":...}` events and non-2xx HTTP; surfaced inline in the thread.

End of document.
