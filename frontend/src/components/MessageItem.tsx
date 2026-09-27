import { useEffect, useMemo, useState } from 'react';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import type { Message } from '../types/chat';
import { patchMarkdownMath } from '../utils/mathMarkdown';
import { formatModelName, messageTime } from '../utils/format';
import { Icon } from './Icon';

interface MessageItemProps {
  msg: Message;
  isLast: boolean;
  isLoading: boolean;
  thinkingEnabled: boolean;
  selectedModel: string;
  copied: boolean;
  editing: boolean;
  editingContent: string;
  onCopy: () => void;
  onStartEdit: () => void;
  onEditingChange: (v: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onRegenerate: () => void;
  onToggleThinking: () => void;
  onDownloadPlot: (url: string) => void;
}

export function MessageItem(props: MessageItemProps) {
  const {
    msg,
    isLast,
    isLoading,
    thinkingEnabled,
    selectedModel,
    copied,
    editing,
    editingContent,
    onCopy,
    onStartEdit,
    onEditingChange,
    onSaveEdit,
    onCancelEdit,
    onRegenerate,
    onToggleThinking,
    onDownloadPlot,
  } = props;

  const rendered = useMemo(() => patchMarkdownMath(msg.content || ''), [msg.content]);
  const [imgBroken, setImgBroken] = useState(false);
  // Reset the broken-image fallback whenever a (new) plot arrives, e.g. on
  // regenerate or when streaming swaps a /static URL for the final payload.
  useEffect(() => {
    setImgBroken(false);
  }, [msg.imageUrl]);
  const hasThinking =
    (isLoading && isLast && msg.role === 'assistant') ||
    !!msg.thinkingText?.trim() ||
    !!msg.thinkingSteps?.length;
  const running = isLoading && isLast;
  const thinkingTitle = running
    ? 'Thinking'
    : `Thought · ${Math.max(1, Math.round((msg.thinkingMs ?? 0) / 1000))}s`;

  return (
    <article
      className={`turn turn-${msg.role === 'user' ? 'user' : 'assistant'}`}
    >
      {msg.role === 'assistant' && (
        <div className="avatar" aria-hidden="true">
          RC
        </div>
      )}
      <div className="turn-main">
        <div className="turn-header">
          {msg.role === 'assistant' ? (
            <>
              <span className="turn-label">Copilot</span>
              {(msg.model || selectedModel) && (
                <span className="model-pill" title={msg.model || selectedModel}>
                  {formatModelName(msg.model || selectedModel)}
                </span>
              )}
            </>
          ) : (
            <span className="turn-label">You</span>
          )}
          {msg.timestamp ? <span className="turn-time">{messageTime(msg.timestamp)}</span> : null}
          <span className="msg-actions">
            <button type="button" className="msg-action" onClick={onCopy} title="Copy message" aria-label="Copy message">
              <Icon name={copied ? 'check' : 'content_copy'} size={14} />
            </button>
            {msg.role === 'user' && (
              <button
                type="button"
                className="msg-action"
                onClick={onStartEdit}
                title="Edit and resend"
                aria-label="Edit message and resend"
              >
                <Icon name="edit" size={14} />
              </button>
            )}
            {msg.role === 'assistant' && msg.content && (
              <button
                type="button"
                className="msg-action"
                onClick={onRegenerate}
                disabled={isLoading}
                title="Regenerate response"
                aria-label="Regenerate response"
              >
                <Icon name="refresh" size={14} />
              </button>
            )}
          </span>
        </div>
        <div className="turn-body">
          {thinkingEnabled && msg.role === 'assistant' && hasThinking && (
            <div className="thinking">
              <button type="button" className="thinking-toggle" onClick={onToggleThinking}>
                <Icon
                  name="chevron_right"
                  size={14}
                  className={`thinking-icon${msg.thinkingOpen ? ' open' : ''}`}
                />
                <span>{thinkingTitle}</span>
                {running && <span className="thinking-pulse" />}
              </button>
              {msg.thinkingOpen && (
                <div className="thinking-panel">
                  {msg.thinkingText && <pre className="thinking-text">{msg.thinkingText}</pre>}
                  {!!msg.thinkingSteps?.length && (
                    <ol className="thinking-log">
                      {msg.thinkingSteps.map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ol>
                  )}
                </div>
              )}
            </div>
          )}
          {editing ? (
            <>
              <Form.Control
                as="textarea"
                rows={3}
                className="edit-input"
                value={editingContent}
                onChange={(e) => onEditingChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    onCancelEdit();
                  }
                }}
              />
              <div className="edit-actions">
                <Button size="sm" variant="dark" onClick={onSaveEdit}>
                  Save
                </Button>
                <Button size="sm" variant="light" onClick={onCancelEdit}>
                  Cancel
                </Button>
              </div>
            </>
          ) : msg.role === 'user' ? (
            <p className="user-prompt">{msg.content}</p>
          ) : (
            <>
              {msg.imageUrl && !imgBroken && (
                <>
                  <img
                    src={msg.imageUrl}
                    alt="Generated plot"
                    className="chat-image"
                    loading="lazy"
                    onError={() => setImgBroken(true)}
                  />
                  <button type="button" className="download-plot" onClick={() => onDownloadPlot(msg.imageUrl!)}>
                    Download plot
                  </button>
                </>
              )}
              {msg.imageUrl && imgBroken && (
                <>
                  <p className="plot-missing" role="note">
                    The plot image could not be displayed inline — it may still download correctly.
                  </p>
                  <button type="button" className="download-plot" onClick={() => onDownloadPlot(msg.imageUrl!)}>
                    Download plot
                  </button>
                </>
              )}
              {msg.content && (
                <div className="assistant-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
                    {rendered}
                  </ReactMarkdown>
                </div>
              )}
            </>
          )}
          {!msg.content && msg.role === 'assistant' && isLoading && isLast && (
            <div className="typing-indicator" aria-label="Assistant is thinking">
              <span />
              <span />
              <span />
            </div>
          )}
          {msg.role === 'assistant' && msg.stats && <div className="msg-stats">{msg.stats}</div>}
        </div>
      </div>
    </article>
  );
}
