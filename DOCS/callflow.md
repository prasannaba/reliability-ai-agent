# Frontend ↔ Backend Call Flow and Per‑file Map

Summary
- This document maps each frontend file to its role and shows the exact sequence of calls when a user sends a message in the chat UI.
- Endpoint used by frontend: POST http://localhost:8000/api/chat
- Request/response JSON shapes are shown below with examples.

Per-file map (frontend)
- angular.json
  - Role: Angular CLI build/serve configuration. Defines build/serve targets and assets.
  - Importance: Controls production/dev builds and output hashing.

- tsconfig.json / tsconfig.app.json
  - Role: TypeScript compiler options (project-level and app-level).
  - Importance: Ensure correct compilation of Angular standalone components.

- package.json / package-lock.json
  - Role: Dependencies and npm scripts.
  - Importance: Reproducible installs and build/test scripts.

- src/main.ts
  - Role: Bootstraps the Angular standalone application.
  - Importance: Entry point that loads AppComponent and appConfig.

- src/app/app.ts (AppComponent)
  - Role: Root component; mounts ChatComponent.
  - Importance: Minimal bootstrap for the chat UI.

- src/app/app.config.ts
  - Role: Provides router, HTTP client and markdown provider.
  - Importance: Registers global providers used by ChatService and components.

- src/app/app.routes.ts
  - Role: Router configuration (empty here).
  - Importance: Add routes if app expands beyond chat.

- src/app/components/chat/*
  - chat.ts (ChatComponent)
    - Role: UI logic, message list, form handling, scrolling.
    - Importance: Adds user messages to messages[], calls ChatService.sendMessage(), processes responses, handles loading state and errors.
  - chat.html
    - Role: Template for the chat UI — message rendering, input form, loading indicator.
    - Importance: Uses Markdown rendering for message content and shows generated images.
  - chat.css
    - Role: Styles for chat UI.
    - Importance: Visual layout and typing indicator.

- src/app/models/message.model.ts
  - Role: Type definition for messages used by the UI.
  - Importance: Ensures consistent shape for messages (role, content, imageUrl).

- src/app/services/chat.ts (ChatService)
  - Role: Encapsulates HTTP communication to backend endpoint (apiUrl).
  - Importance: Central place to change backend URL, add interceptors, transform payloads.

- src/styles.css
  - Role: Global styles.
  - Importance: App-wide styling.

Concrete call trace (step-by-step) — UI action: user submits a message

1. User types a query in the Chat input and presses "Send" (chat.html form submit).
   - Component: ChatComponent.sendMessage()

2. ChatComponent.sendMessage() (frontend)
   - Validates non-empty userInput.
   - Creates a user message object: { role: 'user', content: "<user text>" } and pushes to this.messages.
   - Sets isLoading = true, clears userInput to give immediate UI feedback.
   - scrollToBottom() to show the new message.

3. ChatComponent calls ChatService.sendMessage(prompt)
   - Service: src/app/services/chat.ts

4. ChatService.sendMessage(prompt) — HTTP request
   - Method: POST
   - URL: http://localhost:8000/api/chat
   - Headers: application/json (HttpClient default)
   - Body (example):
     {
       "prompt": "How do I compute Weibull shape parameter from failure times?"
     }
   - Returns Observable<ChatResponse>

5. Network transit → Backend receives POST /api/chat
   - Typical backend middleware: body parser, auth (if any), logging.
   - Backend handler responsibilities:
     - Validate request JSON (presence of prompt).
     - Run business logic: call language model, compute reliability metrics, generate plots (optionally save plot and produce image URL), and prepare assistant text answer.
     - Construct response JSON with fields `content` and `image_url` (nullable).
   - Example backend response (success):
     {
       "content": "You can estimate the Weibull shape parameter using MLE. Steps:\n1. ...\n2. ...\n",
       "image_url": "http://localhost:8000/static/plots/weibull_fit.png"
     }
   - Example backend response (no image):
     {
       "content": "Here is the calculation summary ...",
       "image_url": null
     }
   - On error, backend returns appropriate HTTP status (e.g., 400/500) and JSON error body:
     {
       "error": "Invalid input"
     }

6. Frontend receives Observable result (ChatComponent.subscribe)
   - On next (200 OK with ChatResponse):
     - Create assistant message:
       {
         role: 'assistant',
         content: response.content,
         imageUrl: response.image_url || undefined
       }
     - Push assistant message into this.messages.
     - Set isLoading = false and scrollToBottom().
   - On error (network or non-2xx):
     - Push assistant error message with friendly text ("Sorry, something went wrong...").
     - Set isLoading = false; log error to console.

7. UI rendering
   - Template uses <markdown> to render message.content (supports markdown).
   - If message.imageUrl exists, template shows <img [src]="msg.imageUrl"> below content.
   - chat.css ensures images are sized/responsive and messages styled.

Sequence summary (compact)
- UI submit → ChatComponent (adds user message, loading) → ChatService POST /api/chat → Backend controller processes prompt → Backend returns { content, image_url } → ChatComponent adds assistant message (content + image) and clears loading → UI updates.

Notes and extension points
- CORS: If backend is on different origin, ensure backend adds CORS header or use a proxy.
- Auth: include Authorization header via HttpInterceptor if authentication required.
- Streaming: For streaming model outputs, extend ChatService to use EventSource or fetch stream and update ChatComponent incrementally.
- Retry/timeouts: Consider RxJS operators (retry, timeout) in ChatService for resilient calls.
- Error schema: Standardize backend error shape to include code/message for structured handling.

Example request/response snippets (copy‑paste)
- Request:
  POST http://localhost:8000/api/chat
  Content-Type: application/json

  {
    "prompt": "Fit a Weibull distribution to these failure times: [12, 34, 56]"
  }

- Success response:
  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "content": "Estimated shape k = 1.84, scale λ = 45.2.\nPlot attached.",
    "image_url": "http://localhost:8000/static/plots/fit_2025-12-01.png"
  }

- Error response:
  HTTP/1.1 500 Internal Server Error
  Content-Type: application/json

  {
    "error": "Model inference failed"
  }

End of document.
