import { useEffect, useRef } from 'react';
import Form from 'react-bootstrap/Form';
import { Icon } from './Icon';
import { ModelPicker } from './ModelPicker';

interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  onFile: (file: File) => void;
  streaming: boolean;
  canSend: boolean;
  disabled: boolean;
  placeholder?: string;
  models: string[];
  selectedModel: string;
  modelsLoading: boolean;
  onSelectModel: (model: string) => void;
  onManualCommitModel: (model: string) => void;
  onRefreshModels: () => void;
}

const ACCEPT = '.md,.txt,.pdf,.doc,.docx,.ppt,.pptx';

export function Composer(props: ComposerProps) {
  const {
    value,
    onChange,
    onSend,
    onStop,
    onFile,
    streaming,
    canSend,
    disabled,
    placeholder = 'Ask about Weibull, B-life, warranty…',
    models,
    selectedModel,
    modelsLoading,
    onSelectModel,
    onManualCommitModel,
    onRefreshModels,
  } = props;
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = boxRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  }, [value]);

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
    >
      <label className="attach-btn" title="Attach a procedure">
        <Icon name="attach_file" size={16} />
        <span className="visually-hidden">Attach</span>
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              onFile(file);
            }
            e.target.value = '';
          }}
        />
      </label>
      <Form.Control
        ref={boxRef}
        as="textarea"
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
      />
      <ModelPicker
        models={models}
        selectedModel={selectedModel}
        modelsLoading={modelsLoading}
        onSelect={onSelectModel}
        onManualCommit={onManualCommitModel}
        onRefresh={onRefreshModels}
        drop="up"
        compact
      />
      {streaming ? (
        <button type="button" className="stop-btn" onClick={onStop} aria-label="Stop generating">
          <Icon name="stop" size={16} />
        </button>
      ) : (
        <button type="submit" className="send-btn" disabled={!canSend} aria-label="Send">
          <Icon name="arrow_upward" size={16} />
        </button>
      )}
    </form>
  );
}
