import { useCallback, useEffect, useRef, useState } from "react";
import Form from "react-bootstrap/Form";
import type { ChatStreamEvent, Services } from "../services/types";
import { Composer } from "../components/Composer";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icon";
import { MessageItem } from "../components/MessageItem";
import { SettingsPanel } from "../components/SettingsPanel";
import { Sidebar } from "../components/Sidebar";
import { useSessions } from "../hooks/useSessions";
import { useTheme } from "../hooks/useTheme";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import type { LlmConfig } from "../types/llm";
import type { ExportFormat } from "../types/llm";
import {
  WELCOME_MESSAGE,
  newMessageId,
  type ChatSession,
  type Message,
} from "../types/chat";
import {
  displayTitle,
  escapeHtml,
  formatStats,
  slugify,
} from "../utils/format";
import { patchMarkdownMath } from "../utils/mathMarkdown";
import { renderMath } from "../utils/mathjax";

const THINKING_KEY = "reliability-copilot-thinking";
const EXPORT_FORMAT_KEY = "reliability-copilot-export-format";

const EXAMPLE_PROMPTS = [
  "Fit Weibull to failures 150, 180, 220, 310 with suspensions 800, 800",
  "What is B10 life and how is it calculated?",
  "Who is Prasanna?",
] as const;

function formatToolName(name: string): string {
  return name.replace(/_/g, " ");
}

export function ChatPage({ services }: { services: Services }) {
  const { backend, platform } = services;
  const {
    sessions,
    currentId,
    messages,
    newChat,
    selectSession,
    deleteSession,
    setMessages,
    clearAllChats,
  } = useSessions(platform.storage);
  const { choice: themeChoice, setChoice: setThemeChoice } = useTheme(
    platform.storage,
  );

  const [sidebarOpen, setSidebarOpen] = useState(
    () => typeof window === "undefined" || window.innerWidth >= 860,
  );
  const [userInput, setUserInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [knowledgeSummary, setKnowledgeSummary] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [provider, setProvider] = useState<string | null>(null);
  const [modelsHint, setModelsHint] = useState("");
  const [modelsLoading, setModelsLoading] = useState(false);
  const [domainTitle, setDomainTitle] = useState("");
  const [thinkingEnabled, setThinkingEnabled] = useState(
    () => platform.storage.getItem(THINKING_KEY) !== "0",
  );
  const [showSettings, setShowSettings] = useState(false);
  const [exportFormat, setExportFormat] = useState<ExportFormat>(() => {
    const raw = platform.storage.getItem(EXPORT_FORMAT_KEY);
    if (raw === "markdown" || raw === "html" || raw === "pdf") {
      return raw;
    }
    return "markdown";
  });

  const persistExportFormat = useCallback(
    (format: ExportFormat) => {
      setExportFormat(format);
      platform.storage.setItem(EXPORT_FORMAT_KEY, format);
    },
    [platform],
  );
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [llmConfig, setLlmConfig] = useState<LlmConfig | null>(null);

  const threadRef = useRef<HTMLDivElement>(null);
  const aborterRef = useRef<AbortController | null>(null);
  const renderHandleRef = useRef(0);
  const thinkingStartedAtRef = useRef(0);
  const selectedModelRef = useRef(selectedModel);
  const thinkingEnabledRef = useRef(thinkingEnabled);
  selectedModelRef.current = selectedModel;
  thinkingEnabledRef.current = thinkingEnabled;

  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      const el = threadRef.current;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    }, 0);
  }, []);

  const persistThinking = (v: boolean) => {
    setThinkingEnabled(v);
    platform.storage.setItem(THINKING_KEY, v ? "1" : "0");
  };

  // ---- data loading ----

  const refreshKnowledge = useCallback(async () => {
    try {
      const status = await backend.knowledgeStatus();
      setKnowledgeSummary(
        `${status.files.length} knowledge files, ${status.chunk_count} chunks`,
      );
    } catch {
      setKnowledgeSummary("");
    }
  }, [backend]);

  const refreshModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const result = await backend.listModels();
      setModels(result.models || []);
      setProvider(result.provider ?? null);
      setSelectedModel((prev) => {
        // Backend `current` is always resolved against the fresh list, so it
        // wins after a provider switch. Otherwise keep the previous pick only
        // if it is still listed; never leave a stale model selected.
        if (result.current) {
          return result.current;
        }
        if (prev && result.models.includes(prev)) {
          return prev;
        }
        return result.models[0] || "";
      });
      setModelsHint(result.error || "");
    } catch {
      setModels([]);
      setModelsHint(
        "Could not load models. Open Settings to pick a provider (Ollama, LM Studio, llama.cpp, …) and test the connection.",
      );
    } finally {
      setModelsLoading(false);
    }
  }, [backend]);

  const refreshLlmConfig = useCallback(async () => {
    try {
      const config = await backend.getLlmConfig();
      setLlmConfig(config);
      setProvider(config.provider ?? null);
      if (config.model) {
        setSelectedModel((prev) => prev || config.model || "");
      }
    } catch {
      // keep previous config; models banner will explain
    }
  }, [backend]);

  const refreshDomain = useCallback(async () => {
    try {
      const summary = await backend.getDomains();
      setDomainTitle(summary.title || summary.active || "");
    } catch {
      setDomainTitle("");
    }
  }, [backend]);

  useEffect(() => {
    void refreshKnowledge();
    void refreshDomain();
    void refreshLlmConfig().then(() => refreshModels());
    setTimeout(() => renderMath(threadRef.current), 100);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- streaming ----

  const flushDraft = useCallback(
    (draft: Message) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === draft.id ? { ...draft } : m)),
      );
    },
    [setMessages],
  );

  const scheduleRender = useCallback(
    (draft: Message) => {
      if (renderHandleRef.current) {
        return;
      }
      renderHandleRef.current = requestAnimationFrame(() => {
        renderHandleRef.current = 0;
        flushDraft(draft);
        scrollToBottom();
      });
    },
    [flushDraft, scrollToBottom],
  );

  const appendThinkingText = (draft: Message, chunk: string) => {
    if (!thinkingEnabledRef.current || !chunk) {
      return;
    }
    draft.thinkingText = `${draft.thinkingText || ""}${chunk}`;
    draft.thinkingOpen = true;
  };

  const appendThought = (draft: Message, step: string) => {
    if (!thinkingEnabledRef.current) {
      return;
    }
    const text = step.replace(/\s+/g, " ").trim();
    if (!text) {
      return;
    }
    const steps = draft.thinkingSteps ?? (draft.thinkingSteps = []);
    if (steps[steps.length - 1] === text) {
      return;
    }
    steps.push(text);
    draft.thinkingOpen = true;
  };

  const runCompletion = useCallback(
    async (prompt: string) => {
      const startedAt = Date.now();
      thinkingStartedAtRef.current = startedAt;
      const aborter = new AbortController();
      aborterRef.current = aborter;
      const signal = aborter.signal;
      const draft: Message = {
        id: newMessageId(),
        role: "assistant",
        content: "",
        timestamp: Date.now(),
        model: selectedModelRef.current || undefined,
        thinkingOpen: thinkingEnabledRef.current,
      };
      setMessages((prev) => [...prev, draft]);
      setIsLoading(true);
      setStreaming(true);
      setError(null);
      scrollToBottom();

      const onEvent = (event: ChatStreamEvent) => {
        if (event.type === "token") {
          const first = !draft.content;
          draft.content += event.text;
          if (first) {
            draft.thinkingOpen = false;
          }
        } else if (event.type === "thought") {
          appendThinkingText(draft, event.text);
        } else if (event.type === "tool_start") {
          appendThought(draft, `Using ${formatToolName(event.name)}`);
        } else if (event.type === "tool_end") {
          appendThought(draft, `Finished ${formatToolName(event.name)}`);
        } else if (event.type === "image") {
          // Resolve backend-relative plot paths (remote backends need
          // absolute URLs); data: URLs pass through untouched.
          draft.imageUrl = backend.resolveStaticUrl(event.url);
        } else if (event.type === "done") {
          if (event.content) {
            draft.content = event.content;
          }
          if (event.image_url) {
            draft.imageUrl = backend.resolveStaticUrl(event.image_url);
          }
        } else if (event.type === "error") {
          setError(event.message);
          if (!draft.content) {
            draft.content = event.message;
          }
        }
        scheduleRender(draft);
      };

      try {
        await backend.streamMessage(
          prompt,
          onEvent,
          signal,
          selectedModelRef.current || undefined,
          thinkingEnabledRef.current,
        );
      } catch (err) {
        if (signal.aborted) {
          draft.stats = formatStats(
            (Date.now() - startedAt) / 1000,
            draft.content.length,
          );
        } else {
          const msg =
            "Sorry, something went wrong. Please check the backend connection.";
          setError(msg);
          draft.content = draft.content || msg;
          console.error(err);
        }
      } finally {
        if (renderHandleRef.current) {
          cancelAnimationFrame(renderHandleRef.current);
          renderHandleRef.current = 0;
        }
        setIsLoading(false);
        setStreaming(false);
        aborterRef.current = null;
        const elapsed = (Date.now() - startedAt) / 1000;
        draft.thinkingMs = Date.now() - startedAt;
        draft.thinkingOpen = false;
        if (!draft.stats) {
          draft.stats = formatStats(elapsed, draft.content.length);
        }
        flushDraft(draft);
        scrollToBottom();
        setTimeout(() => renderMath(threadRef.current), 100);
      }
    },
    [setMessages, scheduleRender, flushDraft, scrollToBottom, backend],
  );

  const sendMessage = useCallback(() => {
    const prompt = userInput.trim();
    if (!prompt || isLoading) {
      return;
    }
    setUserInput("");
    setMessages((prev) => [
      ...prev,
      {
        id: newMessageId(),
        role: "user",
        content: prompt,
        timestamp: Date.now(),
      },
    ]);
    void runCompletion(prompt);
  }, [userInput, isLoading, setMessages, runCompletion]);

  const regenerate = useCallback(() => {
    if (isLoading || !messages.length) {
      return;
    }
    let lastUserIdx = -1;
    messages.forEach((m, i) => {
      if (m.role === "user") {
        lastUserIdx = i;
      }
    });
    if (lastUserIdx < 0) {
      return;
    }
    const prompt = messages[lastUserIdx].content;
    setMessages((prev) => prev.slice(0, lastUserIdx + 1));
    void runCompletion(prompt);
  }, [isLoading, messages, setMessages, runCompletion]);

  const stopGenerating = useCallback(() => {
    aborterRef.current?.abort();
  }, []);

  // ---- message actions ----

  const copyMessage = useCallback(
    (msg: Message) => {
      const text = msg.content || "";
      if (!text) {
        return;
      }
      const done = () => {
        setCopiedId(msg.id);
        setTimeout(
          () => setCopiedId((prev) => (prev === msg.id ? null : prev)),
          1500,
        );
      };
      void platform.copyText(text).then(done, done);
    },
    [platform],
  );

  const saveEdit = useCallback(() => {
    if (!editingId) {
      return;
    }
    const index = messages.findIndex((m) => m.id === editingId);
    if (index < 0) {
      setEditingId(null);
      setEditingContent("");
      return;
    }
    const edited = { ...messages[index], content: editingContent };
    if (edited.role === "user") {
      const kept = [...messages.slice(0, index), edited];
      setMessages(() => kept);
      setEditingId(null);
      setEditingContent("");
      void runCompletion(edited.content);
    } else {
      setMessages((prev) => prev.map((m) => (m.id === editingId ? edited : m)));
      setEditingId(null);
      setEditingContent("");
    }
  }, [editingId, editingContent, messages, setMessages, runCompletion]);

  const toggleThinking = useCallback(
    (id: string) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, thinkingOpen: !m.thinkingOpen } : m,
        ),
      );
    },
    [setMessages],
  );

  const downloadPlot = useCallback(
    (imageUrl: string) => {
      const fileName =
        imageUrl.split("/").pop()?.split(/[?#]/)[0] || "weibull-plot.png";
      backend
        .downloadFile(imageUrl)
        .then((blob) => platform.downloadBlob(blob, fileName))
        .catch((err) => console.error(err));
    },
    [backend, platform],
  );

  // ---- sessions / sidebar ----

  const handleSelect = useCallback(
    (id: string) => {
      selectSession(id);
      if (typeof window !== "undefined" && window.innerWidth < 860) {
        setSidebarOpen(false);
      }
      setError(null);
      scrollToBottom();
      setTimeout(() => renderMath(threadRef.current), 50);
    },
    [selectSession, scrollToBottom],
  );

  const [pendingDelete, setPendingDelete] = useState<ChatSession | null>(null);

  const handleDelete = useCallback((s: ChatSession) => {
    setPendingDelete(s);
  }, []);

  const confirmDelete = useCallback(() => {
    if (pendingDelete) {
      deleteSession(pendingDelete.id);
    }
    setPendingDelete(null);
  }, [pendingDelete, deleteSession]);

  const handleNew = useCallback(() => {
    newChat();
    setError(null);
    scrollToBottom();
  }, [newChat, scrollToBottom]);

  // ---- models ----

  const chooseModel = useCallback(
    (model: string) => {
      setSelectedModel(model);
      if (!model) {
        return;
      }
      void backend.saveLlmConfig({ model }).then(
        (config) => setLlmConfig(config),
        () => undefined,
      );
    },
    [backend],
  );

  // ---- upload ----

  const handleFile = useCallback(
    async (file: File) => {
      try {
        const result = await backend.uploadDocument(file);
        setKnowledgeSummary(result.message);
        void refreshKnowledge();
      } catch (err) {
        setKnowledgeSummary("Could not upload that document.");
        console.error(err);
      }
    },
    [backend, refreshKnowledge],
  );

  // ---- export (per chat) ----

  const buildExportMarkdown = useCallback(
    (session: ChatSession | null) => {
      const title = session ? displayTitle(session) : "Chat Export";
      const msgs = session?.messages ?? [];
      const header = [
        `# ${title}`,
        "",
        `- Exported: ${new Date().toLocaleString()}`,
        `- Provider: ${provider ?? "none selected"}`,
        `- Model: ${selectedModel || "unknown"}`,
        `- Messages: ${msgs.length}`,
        "",
        "---",
        "",
      ].join("\n");
      const sections = msgs
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => {
          const time = m.timestamp
            ? new Date(m.timestamp).toLocaleString()
            : "";
          const label =
            m.role === "assistant"
              ? `Assistant (${m.model || selectedModel || "assistant"}) · ${time}`
              : `You · ${time}`;
          return [
            `## ${label}`,
            "",
            m.content || "",
            m.stats ? `\n*${m.stats}*` : "",
            m.imageUrl ? `\n![plot](${m.imageUrl})` : "",
            "",
          ].join("\n");
        })
        .join("\n");
      return `${header}\n${sections.trim()}`.trim();
    },
    [provider, selectedModel],
  );

  const buildExportHtml = useCallback(
    (session: ChatSession | null) => {
      const title = session ? displayTitle(session) : "Chat Export";
      const msgs = (session?.messages ?? []).filter(
        (m) => m.role === "user" || m.role === "assistant",
      );
      const body = msgs
        .map((m) => {
          const time = m.timestamp
            ? new Date(m.timestamp).toLocaleString()
            : "";
          const label =
            m.role === "assistant"
              ? `Assistant (${escapeHtml(m.model || selectedModel || "assistant")}) · ${escapeHtml(time)}`
              : `You · ${escapeHtml(time)}`;
          const contentHtml = m.content
            ? renderToStaticMarkup(
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeSanitize]}
                >
                  {patchMarkdownMath(m.content)}
                </ReactMarkdown>,
              )
            : "";
          const statsHtml = m.stats
            ? `<p><em>${escapeHtml(m.stats)}</em></p>`
            : "";
          const imageHtml = m.imageUrl
            ? `<img src="${escapeHtml(m.imageUrl)}" alt="Generated plot" class="chat-image" />`
            : "";
          return `<div class="turn"><div class="turn-body"><h2>${label}</h2>${contentHtml}${statsHtml}${imageHtml}</div></div>`;
        })
        .join("\n");
      return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(title)}</title><style>
      @page{margin:0}
      body{font-family:Arial,sans-serif;line-height:1.5;padding:16mm;color:#111;background:#fff}
      h1{margin:0 0 16px;font-size:1.15rem}
      h2{font-size:1rem;margin:0 0 8px}
      .turn{margin-bottom:20px;break-inside:avoid-page}
      .turn-body{word-break:break-word;overflow-wrap:anywhere;max-width:100%}
      .chat-image{max-width:100%;border-radius:8px;margin-top:10px;border:1px solid #ddd}
      p{margin:0 0 8px}
      ul{margin:0 0 8px 20px}
      code{background:#f5f5f5;padding:2px 4px;border-radius:4px}
      pre{background:#f5f5f5;padding:12px;border-radius:6px;overflow-x:auto}
      table{border-collapse:collapse;margin:8px 0}
      th,td{border:1px solid #d4d4d4;padding:4px 8px}
      .MathJax{font-size:1em}
      @media print{body{padding:16mm}}
    </style>
      <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"><\/script>
      <script>window.MathJax={tex:{inlineMath:[['$','$'],['\\\\(','\\\\)']],displayMath:[['$$','$$'],['\\\\[','\\\\]']],macros:{sb:['_{#1}',1]}},svg:{fontCache:'global'}};<\/script>
    </head><body><h1>${escapeHtml(title)}</h1>${body}</body></html>`;
    },
    [selectedModel],
  );

  const exportSession = useCallback(
    (session: ChatSession | null, format: ExportFormat) => {
      const name = slugify(session ? displayTitle(session) : "chat-export");
      if (format === "markdown") {
        void platform.downloadBlob(
          new Blob([buildExportMarkdown(session)], {
            type: "text/markdown;charset=utf-8",
          }),
          `${name}.md`,
        );
        return;
      }
      const html = buildExportHtml(session);
      if (format === "html") {
        void platform.downloadBlob(
          new Blob([html], { type: "text/html;charset=utf-8" }),
          `${name}.html`,
        );
        return;
      }
      void platform.printHtml("Reliability Copilot", html);
    },
    [platform, buildExportMarkdown, buildExportHtml],
  );

  const showEmptyHero = messages.length === 0 && !userInput.trim();

  return (
    <div className={`app-shell${sidebarOpen ? "" : " sidebar-collapsed"}`}>
      {sidebarOpen && (
        <Sidebar
          sessions={sessions}
          currentId={currentId}
          onToggle={() => setSidebarOpen(false)}
          onNew={handleNew}
          onSelect={handleSelect}
          onDelete={handleDelete}
          onExport={(s) => exportSession(s, exportFormat)}
          provider={provider ?? "No provider"}
          selectedModel={selectedModel}
          domain={domainTitle}
          knowledgeSummary={knowledgeSummary}
          onOpenSettings={() => setShowSettings(true)}
        />
      )}
      {sidebarOpen && (
        <div
          className="sidebar-scrim"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <div className="main">
        {!sidebarOpen && (
          <button
            type="button"
            className="sidebar-reopen"
            onClick={() => setSidebarOpen(true)}
            title="Show sidebar"
            aria-label="Show sidebar"
          >
            <Icon name="layout_sidebar" size={16} />
          </button>
        )}
        {modelsHint && <p className="models-banner">{modelsHint}</p>}

        <div
          className={`thread${showEmptyHero ? " thread-empty" : ""}`}
          ref={threadRef}
        >
          <div className="thread-inner">
            {showEmptyHero && (
              <div className="empty-hero" aria-hidden={false}>
                <h1 className="empty-hero-title">{domainTitle || "Reliability Copilot"}</h1>
                <p className="empty-hero-text">{WELCOME_MESSAGE}</p>
                <div className="empty-hero-examples">
                  {EXAMPLE_PROMPTS.map((example) => (
                    <button
                      key={example}
                      type="button"
                      className="empty-hero-chip"
                      onClick={() => setUserInput(example)}
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <MessageItem
                key={msg.id}
                msg={msg}
                isLast={i === messages.length - 1}
                isLoading={isLoading}
                thinkingEnabled={thinkingEnabled}
                selectedModel={selectedModel}
                copied={copiedId === msg.id}
                editing={editingId === msg.id}
                editingContent={editingContent}
                onCopy={() => copyMessage(msg)}
                onStartEdit={() => {
                  setEditingId(msg.id);
                  setEditingContent(msg.content);
                }}
                onEditingChange={setEditingContent}
                onSaveEdit={saveEdit}
                onCancelEdit={() => {
                  setEditingId(null);
                  setEditingContent("");
                }}
                onRegenerate={regenerate}
                onToggleThinking={() => toggleThinking(msg.id)}
                onDownloadPlot={downloadPlot}
              />
            ))}
            {error && (
              <div className="chat-error" role="alert">
                <Icon name="warning" size={14} /> {error}
              </div>
            )}
          </div>
        </div>

        <div className="composer-dock">
          <div className="composer-options">
            <Form.Check
              type="checkbox"
              id="thinking-enabled"
              label="Thinking"
              checked={thinkingEnabled}
              onChange={(e) => persistThinking(e.target.checked)}
              title="Show model reasoning in a foldable section"
              className="thinking-opt"
            />
          </div>
          <Composer
            value={userInput}
            onChange={setUserInput}
            onSend={sendMessage}
            onStop={stopGenerating}
            onFile={handleFile}
            streaming={streaming}
            canSend={!!userInput.trim() && !isLoading && !!provider}
            disabled={isLoading || !provider}
            placeholder={
              provider
                ? undefined
                : "Select an LLM provider in Settings to start chatting…"
            }
            models={models}
            selectedModel={selectedModel}
            modelsLoading={modelsLoading}
            onSelectModel={chooseModel}
            onManualCommitModel={chooseModel}
            onRefreshModels={refreshModels}
          />
          <p className="composer-hint">
            {!provider ? (
              <>
                No LLM provider selected —{" "}
                <button
                  type="button"
                  className="composer-hint-link"
                  onClick={() => setShowSettings(true)}
                >
                  open Settings
                </button>{" "}
                to choose one.
              </>
            ) : modelsHint ? (
              modelsHint
            ) : (
              "Enter to send · Shift+Enter for a new line · Attach procedures with the paperclip button"
            )}
          </p>
          <footer className="app-footer">
            © 2026 Prasanna P. Badami · Released under MIT License
          </footer>
        </div>
      </div>

      <SettingsPanel
        backend={backend}
        show={showSettings}
        config={llmConfig}
        selectedModelFallback={selectedModel}
        exportFormat={exportFormat}
        onExportFormatChange={persistExportFormat}
        themeChoice={themeChoice}
        onThemeChoice={setThemeChoice}
        onClearAll={() => {
          clearAllChats();
          setError(null);
          scrollToBottom();
        }}
        clearDisabled={
          !sessions.some((s) => s.messages.some((m) => m.role === "user"))
        }
        onClose={(saved) => {
          setShowSettings(false);
          if (saved) {
            void refreshLlmConfig().then(() => refreshModels());
          }
        }}
      />
      <ConfirmDialog
        show={pendingDelete !== null}
        title={
          pendingDelete
            ? `Delete "${displayTitle(pendingDelete)}"?`
            : "Delete chat?"
        }
        message="This will permanently delete this chat, including its prompts and responses. This action cannot be undone. Do you want to continue?"
        confirmLabel="Delete"
        onCancel={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
      />
    </div>
  );
}

// Re-export for tests.
export { patchMarkdownMath };
