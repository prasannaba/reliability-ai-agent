import { useEffect, useState } from 'react';
import Dropdown from 'react-bootstrap/Dropdown';
import Form from 'react-bootstrap/Form';
import { formatModelName } from '../utils/format';
import { Icon } from './Icon';

interface ModelPickerProps {
  models: string[];
  selectedModel: string;
  modelsLoading: boolean;
  onSelect: (model: string) => void;
  onManualCommit: (model: string) => void;
  onRefresh: () => void;
  drop?: 'up' | 'down';
  compact?: boolean;
}

export function ModelPicker(props: ModelPickerProps) {
  const { models, selectedModel, modelsLoading, onSelect, onManualCommit, onRefresh } = props;
  const { drop = 'down', compact = false } = props;
  const [draft, setDraft] = useState(selectedModel);

  useEffect(() => {
    setDraft(selectedModel);
  }, [selectedModel]);

  const commit = () => {
    if (draft !== selectedModel) {
      onManualCommit(draft);
    }
  };

  return (
    <Dropdown className={`model-selector${compact ? ' model-selector-compact' : ''}`} autoClose="outside" drop={drop}>
      <Dropdown.Toggle
        variant="light"
        className="model-btn"
        title={selectedModel || 'Select model'}
      >
        <Icon name="smart_toy" size={16} />
        <span className="model-text">
          {selectedModel ? formatModelName(selectedModel) : 'select model'}
        </span>
        <Icon name="expand_more" size={16} />
      </Dropdown.Toggle>
      <Dropdown.Menu className="model-dropdown" align="end">
        {modelsLoading ? (
          <div className="model-empty">Loading models…</div>
        ) : models.length ? (
          models.map((id) => (
            <Dropdown.Item
              key={id}
              active={selectedModel === id}
              onClick={() => onSelect(id)}
              title={id}
              className="model-option"
            >
              <span className="model-check">
                {selectedModel === id && <Icon name="check" size={14} />}
              </span>
              <span className="model-label">{id}</span>
            </Dropdown.Item>
          ))
        ) : (
          <div className="model-empty">No models found. Check Settings &amp; connection.</div>
        )}
        <div className="model-manual px-2 pt-2">
          <Form.Label className="mb-1">Model id</Form.Label>
          <Form.Control
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                (e.target as HTMLInputElement).blur();
              }
            }}
            placeholder="e.g. llama3.1:8b, or “default”"
          />
        </div>
        <Dropdown.Item as="button" onClick={onRefresh} disabled={modelsLoading} className="model-refresh">
          <Icon name="refresh" size={14} /> Refresh models
        </Dropdown.Item>
      </Dropdown.Menu>
    </Dropdown>
  );
}
