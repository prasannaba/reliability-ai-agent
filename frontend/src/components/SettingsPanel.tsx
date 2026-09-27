import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import Modal from "react-bootstrap/Modal";
import Spinner from "react-bootstrap/Spinner";
import type {
  BackendService,
  DomainSummary,
  McpToolSummary,
} from "../services/types";
import type { ThemeChoice } from "../hooks/useTheme";
import {
  EXPORT_FORMATS,
  LLM_PROVIDERS,
  PROVIDER_DEFAULTS,
  type ExportFormat,
  type LlmConfig,
  type LlmProvider,
} from "../types/llm";
import { ConfirmDialog } from "./ConfirmDialog";
import { Icon } from "./Icon";

interface SettingsPanelProps {
  backend: BackendService;
  show: boolean;
  config: LlmConfig | null;
  selectedModelFallback: string;
  exportFormat: ExportFormat;
  onExportFormatChange: (f: ExportFormat) => void;
  themeChoice: ThemeChoice;
  onThemeChoice: (c: ThemeChoice) => void;
  onClearAll: () => void;
  clearDisabled: boolean;
  onClose: (saved: boolean) => void;
}

const THEME_CHOICES: { value: ThemeChoice; label: string; hint: string }[] = [
  {
    value: "system",
    label: "System",
    hint: "Follow your OS light/dark setting",
  },
  { value: "light", label: "Light", hint: "Always use the light theme" },
  { value: "dark", label: "Dark", hint: "Always use the dark theme" },
];

type ModelsStatus = "idle" | "loading" | "success" | "error";

// Backend default (LLM_TEMPERATURE fallback in main.py); the slider hydrates
// from the saved config on open, so the initial state must match the server.
const DEFAULT_TEMPERATURE = 0.1;

// Blur-driven model reloads are debounced: tabbing through Base URL → API
// key → Model used to fire one /api/llm/test probe per blur.
const LOAD_DEBOUNCE_MS = 500;

export function SettingsPanel({
  backend,
  show,
  config,
  selectedModelFallback,
  exportFormat,
  onExportFormatChange,
  themeChoice,
  onThemeChoice,
  onClearAll,
  clearDisabled,
  onClose,
}: SettingsPanelProps) {
  const [provider, setProvider] = useState<LlmProvider | "">("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState(DEFAULT_TEMPERATURE);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [modelsStatus, setModelsStatus] = useState<ModelsStatus>("idle");
  const [modelsMessage, setModelsMessage] = useState(
    "Models load automatically from the base URL",
  );
  const [testing, setTesting] = useState(false);
  const [testOk, setTestOk] = useState<boolean | null>(null);
  const [testMessage, setTestMessage] = useState("");
  const [validationError, setValidationError] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [domainInfo, setDomainInfo] = useState<DomainSummary | null>(null);
  const [mcpTools, setMcpTools] = useState<McpToolSummary[]>([]);
  const [domainLoading, setDomainLoading] = useState(false);
  const [domainError, setDomainError] = useState("");
  // Separate generations for model listing vs connection test: they share
  // abort refs but must never cancel each other's results (a probe starting
  // used to discard the other's response and leave `testing` stuck on).
  const loadRequestId = useRef(0);
  const testRequestId = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const testAbortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Stable, backend-bound model loader. Previously this lived in a useRef
  // closure that captured the first-render backend forever and forced an
  // eslint-disable; as a useCallback it always uses the current service.
  const loadModels = useCallback(
    async (p: LlmProvider, url: string, key: string): Promise<void> => {
      const id = ++loadRequestId.current;
      abortRef.current?.abort();
      // A fresh listing supersedes any in-flight connection test so a stale
      // test response can never clobber the new provider's model list.
      testRequestId.current++;
      testAbortRef.current?.abort();
      setTesting(false);
      const aborter = new AbortController();
      abortRef.current = aborter;
      if (!url) {
        setAvailableModels([]);
        setModelsStatus("idle");
        setModelsMessage("Enter a base URL to load models");
        return;
      }
      if (p === "openai" && !key) {
        setAvailableModels([]);
        setModelsStatus("idle");
        setModelsMessage("Enter your API key to load models");
        return;
      }
      setModelsStatus("loading");
      setModelsMessage("Loading models…");
      try {
        const result = await backend.testLlmConfig(
          { provider: p, baseUrl: url, apiKey: key || undefined },
          aborter.signal,
        );
        if (loadRequestId.current !== id) {
          return;
        }
        const found = result.models || [];
        setAvailableModels(found);
        if (!found.length) {
          setModelsStatus("error");
          setModelsMessage(
            result.ok
              ? "Connected, but no models listed — type the model id manually below."
              : result.message || "No models found — is the server running?",
          );
        } else {
          setModelsStatus("success");
          setModelsMessage(
            `Found ${found.length} model${found.length === 1 ? "" : "s"}`,
          );
          setModel((prev) =>
            prev && found.includes(prev) ? prev : (found[0] as string),
          );
        }
      } catch (err) {
        if (loadRequestId.current !== id) {
          return;
        }
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        setAvailableModels([]);
        setModelsStatus("error");
        setModelsMessage(
          err instanceof Error ? err.message : "Failed to load models",
        );
      }
    },
    [backend],
  );

  // Debounced variant for blur events so tabbing through the form fires at
  // most one probe. Explicit actions (provider switch, Refresh, reset)
  // call loadModels directly.
  const scheduleLoadModels = useCallback(
    (p: LlmProvider, url: string, key: string): void => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      debounceRef.current = setTimeout(() => {
        debounceRef.current = null;
        void loadModels(p, url, key);
      }, LOAD_DEBOUNCE_MS);
    },
    [loadModels],
  );

  // Abort in-flight probes and drop pending debounces on unmount / close.
  useEffect(
    () => () => {
      abortRef.current?.abort();
      testAbortRef.current?.abort();
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    },
    [],
  );

  // Hydrate each time the panel opens.
  useEffect(() => {
    if (!show) {
      abortRef.current?.abort();
      testAbortRef.current?.abort();
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
      return;
    }
    const p = config?.provider ?? "";
    setProvider(p);
    setBaseUrl(
      config?.baseUrl || (p ? PROVIDER_DEFAULTS[p]?.baseUrl || "" : ""),
    );
    setModel(config?.model || selectedModelFallback || "");
    setTemperature(config?.temperature ?? DEFAULT_TEMPERATURE);
    setSystemPrompt(config?.systemPrompt || "");
    setApiKey("");
    setTestOk(null);
    setTestMessage("");
    setTesting(false);
    setValidationError("");
    setSaving(false);
    setAvailableModels([]);
    if (p) {
      void loadModels(
        p,
        config?.baseUrl || PROVIDER_DEFAULTS[p]?.baseUrl || "",
        "",
      );
    } else {
      setModelsStatus("idle");
      setModelsMessage("Select an LLM provider above to load models.");
    }
    // Hydrate-on-open by design: config/selectedModelFallback are read once
    // per opening so mid-edit parent refreshes never wipe user input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show, loadModels]);

  // Domain pack + MCP tool inventory hydrate each time the panel opens.
  useEffect(() => {
    if (!show) {
      return;
    }
    const aborter = new AbortController();
    setDomainLoading(true);
    setDomainError("");
    void (async () => {
      try {
        const [domains, tools] = await Promise.all([
          backend.getDomains(aborter.signal),
          backend.listMcpTools(aborter.signal),
        ]);
        if (aborter.signal.aborted) {
          return;
        }
        setDomainInfo(domains);
        setMcpTools(tools.tools || []);
      } catch {
        if (!aborter.signal.aborted) {
          setDomainInfo(null);
          setMcpTools([]);
          setDomainError("Could not load the domain pack from the backend.");
        }
      } finally {
        if (!aborter.signal.aborted) {
          setDomainLoading(false);
        }
      }
    })();
    return () => aborter.abort();
  }, [show, backend]);

  // The react-bootstrap Modal handles Escape and focus itself.

  const refreshModels = () => {
    if (!provider) {
      setModelsStatus("idle");
      setModelsMessage("Select an LLM provider above to load models.");
      return;
    }
    // Re-probe even while a previous load is in flight: loadModels aborts
    // the stale request, so Refresh is never stuck disabled.
    void loadModels(provider, baseUrl, apiKey);
  };

  const onProviderChange = (p: LlmProvider | "") => {
    setProvider(p);
    const url = p ? PROVIDER_DEFAULTS[p]?.baseUrl || "" : "";
    setBaseUrl(url);
    setModel("");
    setAvailableModels([]);
    setTestOk(null);
    setTestMessage("");
    if (p) {
      void loadModels(p, url, apiKey);
    } else {
      setModelsStatus("idle");
      setModelsMessage("Select an LLM provider above to load models.");
    }
  };

  const testConnection = async () => {
    if (!provider) {
      setTestOk(false);
      setTestMessage("Please select an LLM provider first");
      return;
    }
    if (!baseUrl) {
      setTestOk(false);
      setTestMessage("Please enter a base URL first");
      return;
    }
    if (provider === "openai" && !apiKey) {
      setTestOk(false);
      setTestMessage("API key is required for OpenAI");
      return;
    }
    const id = ++testRequestId.current;
    testAbortRef.current?.abort();
    // An explicit test supersedes any in-flight auto-listing so its result
    // (including its model list) wins instead of being clobbered.
    loadRequestId.current++;
    abortRef.current?.abort();
    const aborter = new AbortController();
    testAbortRef.current = aborter;
    setTesting(true);
    setTestOk(null);
    setTestMessage("Testing connection…");
    try {
      const result = await backend.testLlmConfig(
        {
          provider,
          baseUrl,
          apiKey: apiKey || undefined,
        },
        aborter.signal,
      );
      if (testRequestId.current !== id) {
        return;
      }
      setTesting(false);
      setTestOk(result.ok);
      setTestMessage(result.ok ? "Connection successful!" : result.message);
      if (result.ok && result.models?.length) {
        setAvailableModels(result.models);
        setModelsStatus("success");
        setModelsMessage(
          `Found ${result.models.length} model${result.models.length === 1 ? "" : "s"}`,
        );
        setModel((prev) =>
          prev && result.models.includes(prev)
            ? prev
            : (result.models[0] as string),
        );
      }
    } catch (err) {
      if (testRequestId.current !== id) {
        return;
      }
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      setTesting(false);
      setTestOk(false);
      setTestMessage(err instanceof Error ? err.message : "Connection failed");
    }
  };

  const save = async () => {
    if (!provider) {
      setValidationError("Please select an LLM provider");
      return;
    }
    if (!baseUrl) {
      setValidationError("Base URL is required");
      return;
    }
    if (provider === "openai" && !apiKey) {
      setValidationError("API key is required for OpenAI");
      return;
    }
    setValidationError("");
    setSaving(true);
    try {
      await backend.saveLlmConfig({
        provider,
        baseUrl,
        apiKey: apiKey || undefined,
        model: model || undefined,
        temperature,
        systemPrompt,
      });
      onClose(true);
    } catch (err) {
      setValidationError(
        err instanceof Error ? err.message : "Could not save settings",
      );
    } finally {
      setSaving(false);
    }
  };

  if (!show) {
    return null;
  }

  const help = provider ? PROVIDER_DEFAULTS[provider]?.help || "" : "";
  const needsKey = provider
    ? (PROVIDER_DEFAULTS[provider]?.needsApiKey ?? false)
    : false;

  return (
    <Modal
      show={show}
      onHide={() => onClose(false)}
      centered
      aria-label="Settings"
      className="settings-modal"
    >
      <Modal.Header closeButton>
        <Modal.Title>Settings</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <div className="settings-content">
          <h2 className="settings-section-title">Chat</h2>
          <Form.Group className="mb-2">
            <Form.Label htmlFor="llm-provider">LLM Provider</Form.Label>
            <Form.Select
              id="llm-provider"
              value={provider}
              onChange={(e) =>
                onProviderChange(e.target.value as LlmProvider | "")
              }
            >
              <option value="">Select a provider…</option>
              {LLM_PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </Form.Select>
            <Form.Text muted>
              {help || "Choose which LLM server to chat with."}
            </Form.Text>
          </Form.Group>

          <Form.Group className="mb-2">
            <div className="d-flex justify-content-between align-items-center">
              <Form.Label htmlFor="llm-base" className="mb-1">
                Base URL
              </Form.Label>
              <Button
                variant="link"
                size="sm"
                className="p-0"
                disabled={!provider}
                onClick={() => {
                  if (!provider) {
                    return;
                  }
                  const url = PROVIDER_DEFAULTS[provider]?.baseUrl || "";
                  setBaseUrl(url);
                  void loadModels(provider, url, apiKey);
                }}
              >
                Reset to default
              </Button>
            </div>
            <Form.Control
              id="llm-base"
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              onBlur={() => {
                if (provider) {
                  scheduleLoadModels(provider, baseUrl, apiKey);
                }
              }}
            />
          </Form.Group>

          <Form.Group className="mb-2">
            <Form.Label htmlFor="llm-key">API Key</Form.Label>
            <Form.Control
              id="llm-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onBlur={() => {
                if (provider) {
                  scheduleLoadModels(provider, baseUrl, apiKey);
                }
              }}
              placeholder={
                needsKey
                  ? "sk-..."
                  : "Optional — local servers usually ignore this"
              }
            />
            <Form.Text muted>
              {needsKey
                ? "Your API key is stored on the backend and never sent anywhere except the LLM provider."
                : "Optional — most local servers ignore this. Set it only if your endpoint requires authentication."}
            </Form.Text>
          </Form.Group>

          <Form.Group className="mb-2">
            <div className="d-flex justify-content-between align-items-center">
              <Form.Label htmlFor="llm-model" className="mb-1">
                Model
              </Form.Label>
              <Button
                variant="link"
                size="sm"
                className="p-0"
                onClick={refreshModels}
                disabled={!provider}
                title={!provider ? "Select a provider first" : "Reload models"}
              >
                <Icon name="refresh" size={14} /> Refresh
              </Button>
            </div>
            <Form.Select
              id="llm-model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={modelsStatus === "loading" || !availableModels.length}
              className="mb-2"
            >
              <option value="">
                {modelsStatus === "loading"
                  ? "Loading models…"
                  : availableModels.length
                    ? "Select a model…"
                    : "No models loaded — type one below"}
              </option>
              {availableModels.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Form.Select>
            <Form.Control
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              aria-label="Model id"
              placeholder="Model id (e.g. from GET /v1/models, or “default”)"
            />
            <Form.Text muted className={`d-block status-${modelsStatus}`}>
              {modelsStatus === "loading" && (
                <Spinner size="sm" className="me-1" />
              )}
              {modelsMessage}
            </Form.Text>
            <div className="d-flex align-items-center gap-2 mt-2">
              <Button
                variant={
                  testOk === true
                    ? "outline-success"
                    : testOk === false
                      ? "outline-danger"
                      : "outline-secondary"
                }
                size="sm"
                onClick={testConnection}
                disabled={testing || !baseUrl || !provider}
              >
                {testing
                  ? "Testing…"
                  : testOk === true
                    ? "✓ Connected"
                    : testOk === false
                      ? "✗ Failed"
                      : "Test connection"}
              </Button>
              {testMessage && (
                <Form.Text
                  muted
                  className={testOk === false ? "error-text" : ""}
                >
                  {testMessage}
                </Form.Text>
              )}
            </div>
          </Form.Group>

          <Form.Group className="mb-2">
            <Form.Label htmlFor="llm-system">
              System Prompt <span className="text-muted">(optional)</span>
            </Form.Label>
            <Form.Control
              id="llm-system"
              as="textarea"
              rows={2}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="e.g. You are a helpful reliability assistant. Answer concisely."
            />
            <Form.Text muted>
              Appended to the active domain&apos;s built-in system prompt.
              Leave empty for the default.
            </Form.Text>
          </Form.Group>

          <Form.Group className="mb-1">
            <Form.Label htmlFor="llm-temp">
              Temperature: {temperature.toFixed(1)}
            </Form.Label>
            <Form.Range
              id="llm-temp"
              min={0}
              max={2}
              step={0.1}
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
            />
            <Form.Text muted>
              Lower values make responses more deterministic, higher values more
              creative.
            </Form.Text>
          </Form.Group>

          <h2 className="settings-section-title">Domain &amp; tools</h2>
          <div className="settings-domain-section">
            {domainLoading && (
              <p className="text-muted mb-1">Loading domain pack…</p>
            )}
            {domainError && (
              <p className="text-muted mb-1">{domainError}</p>
            )}
            {domainInfo && (
              <p className="mb-1">
                <strong>{domainInfo.title}</strong>{" "}
                <span className="text-muted">({domainInfo.active})</span>
              </p>
            )}
            {domainInfo && domainInfo.domains.length > 1 && (
              <Form.Text muted>
                Available packs: {domainInfo.domains.join(", ")}. The active
                pack is chosen by the backend&apos;s ACTIVE_DOMAIN setting.
              </Form.Text>
            )}
            {mcpTools.length > 0 && (
              <ul className="mcp-tools-list" aria-label="MCP tools">
                {mcpTools.map((tool) => (
                  <li key={tool.name} title={tool.description || tool.name}>
                    <code>{tool.name}</code>
                    {tool.description && (
                      <span className="mcp-tool-desc">{tool.description}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="settings-theme-section">
            <Form.Label className="mb-1">Export format</Form.Label>
            <div
              className="export-format-options"
              role="radiogroup"
              aria-label="Export format"
            >
              {EXPORT_FORMATS.map((f) => (
                <Form.Check
                  key={f.value}
                  inline
                  type="radio"
                  id={`export-format-${f.value}`}
                  name="export-format"
                  label={f.label}
                  checked={exportFormat === f.value}
                  onChange={() => onExportFormatChange(f.value)}
                />
              ))}
            </div>
            <Form.Text muted>
              Used when exporting individual chats from the chat list.
            </Form.Text>
          </div>

          <h2 className="settings-section-title">Appearance</h2>
          <div className="settings-theme-section">
            <Form.Label className="mb-1">Theme</Form.Label>
            <div
              className="export-format-options"
              role="radiogroup"
              aria-label="Color theme"
            >
              {THEME_CHOICES.map((t) => (
                <Form.Check
                  key={t.value}
                  inline
                  type="radio"
                  id={`theme-choice-${t.value}`}
                  name="theme-choice"
                  label={t.label}
                  title={t.hint}
                  checked={themeChoice === t.value}
                  onChange={() => onThemeChoice(t.value)}
                />
              ))}
            </div>
          </div>

          <h2 className="settings-section-title settings-section-danger">
            Delete history
          </h2>
          <div className="settings-clear-section">
            <Button
              variant="outline-danger"
              size="sm"
              disabled={clearDisabled}
              onClick={() => setConfirmClear(true)}
              title={
                clearDisabled
                  ? "Nothing to clear yet"
                  : "Delete all chats permanently"
              }
            >
              <Icon name="delete" size={14} /> Clear all chats
            </Button>
            <Form.Text muted>
              Permanently deletes every chat, including all prompts and
              responses.
            </Form.Text>
          </div>

          {validationError && (
            <Alert variant="danger" className="mt-2 mb-0">
              {validationError}
            </Alert>
          )}
        </div>
      </Modal.Body>

      <Modal.Footer>
        <Button variant="secondary" onClick={() => onClose(false)}>
          Cancel
        </Button>
        <Button variant="dark" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </Modal.Footer>
      <ConfirmDialog
        show={confirmClear}
        title="Clear all chats?"
        message="This will permanently delete all chats, including every prompt and response. This action cannot be undone. Do you want to continue?"
        confirmLabel="Clear all"
        onCancel={() => setConfirmClear(false)}
        onConfirm={() => {
          setConfirmClear(false);
          onClearAll();
        }}
      />
    </Modal>
  );
}
