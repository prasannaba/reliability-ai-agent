import { useEffect, useRef, useState } from "react";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import { displayTitle, previewText, relativeTime } from "../utils/format";
import type { ChatSession } from "../types/chat";
import { Icon } from "./Icon";

interface SidebarProps {
  sessions: ChatSession[];
  currentId: string | null;
  onToggle: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (s: ChatSession) => void;
  onExport: (s: ChatSession) => void;
  provider: string;
  selectedModel: string;
  /** Display title of the backend's active domain pack ('' = unknown). */
  domain: string;
  knowledgeSummary: string;
  onOpenSettings: () => void;
}

export function Sidebar(props: SidebarProps) {
  const {
    sessions,
    currentId,
    onToggle,
    onNew,
    onSelect,
    onDelete,
    onExport,
    provider,
    selectedModel,
    domain,
    knowledgeSummary,
    onOpenSettings,
  } = props;

  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (searchOpen) {
      searchRef.current?.focus();
    }
  }, [searchOpen]);

  const q = query.trim().toLowerCase();
  const parts = q ? q.split(/\s+/) : [];
  const filtered = [...sessions]
    .sort((a, b) => b.updatedAt - a.updatedAt)
    // Never list empty chats ("Untitled chat"): only chats with at least
    // one user message appear. The active empty chat stays open in main.
    .filter((s) =>
      s.messages.some((m) => m.role === "user" && (m.content || "").trim()),
    )
    .filter((s) => {
      if (!parts.length) {
        return true;
      }
      const haystack =
        `${displayTitle(s)} ${s.messages.map((m) => m.content).join(" ")}`.toLowerCase();
      return parts.every((part) => haystack.includes(part));
    });

  return (
    <aside className="sidebar" aria-label="Chat history and settings">
      <div className="sidebar-top">
        <div className="sidebar-top-row">
          <button
            type="button"
            className={`icon-action${searchOpen ? " active" : ""}`}
            onClick={() => setSearchOpen((v) => !v)}
            title="Search chats"
            aria-label="Search chats"
            aria-expanded={searchOpen}
            aria-pressed={searchOpen}
          >
            <Icon name="search" size={16} />
          </button>
          <button
            type="button"
            className="icon-action"
            onClick={onToggle}
            title="Hide sidebar"
            aria-label="Hide sidebar"
          >
            <Icon name="layout_sidebar" size={16} />
          </button>
        </div>
        {searchOpen && (
          <div className="sidebar-search-open">
            <Form.Control
              ref={searchRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search chats…"
              aria-label="Search chats"
            />
          </div>
        )}
        <Button
          variant="light"
          className="new-chat-btn"
          onClick={onNew}
          title="Start a new chat"
        >
          <Icon name="new_chat" size={16} /> New chat
        </Button>
      </div>
      <nav className="sidebar-history" aria-label="Chat history">
        {!filtered.length ? (
          <p className="sidebar-empty">
            {q ? "No matching chats found" : "No chats yet"}
          </p>
        ) : (
          filtered.map((s) => (
            <div
              key={s.id}
              className={`history-row${currentId === s.id ? " active" : ""}`}
            >
              <button
                type="button"
                className="history-main"
                onClick={() => onSelect(s.id)}
                title={previewText(s) || displayTitle(s)}
              >
                <span className="history-title">{displayTitle(s)}</span>
                <span className="history-time">
                  {relativeTime(s.updatedAt)}
                </span>
              </button>
              <button
                type="button"
                className="history-export"
                onClick={(e) => {
                  e.stopPropagation();
                  onExport(s);
                }}
                aria-label={`Export ${displayTitle(s)}`}
                title="Export chat"
              >
                <Icon name="download" size={14} />
              </button>
              <button
                type="button"
                className="history-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(s);
                }}
                aria-label={`Delete ${displayTitle(s)}`}
                title="Delete chat"
              >
                <Icon name="delete" size={14} />
              </button>
            </div>
          ))
        )}
      </nav>
      <div className="sidebar-footer">
        <div className="provider-row">
          {domain && (
            <span className="domain-badge" title={`Active domain pack: ${domain}`}>
              {domain}
            </span>
          )}
          <span className="provider-badge" title={`LLM provider: ${provider}`}>
            {provider}
          </span>
          {selectedModel && (
            <span className="provider-model" title={selectedModel}>
              {selectedModel}
            </span>
          )}
        </div>
        {knowledgeSummary && (
          <p className="knowledge-summary">{knowledgeSummary}</p>
        )}
        <div className="sidebar-footer-btns">
          <Button
            variant="light"
            className="sidebar-btn"
            onClick={onOpenSettings}
            title="Settings (chat, appearance, chats)"
            aria-label="Open settings"
          >
            <Icon name="settings" size={14} /> Settings
          </Button>
        </div>
      </div>
    </aside>
  );
}
