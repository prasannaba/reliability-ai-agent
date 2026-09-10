/** LLM provider presets, mirroring MDLithe ChatSettings + backend PROVIDER_DEFAULTS. */

export type LlmProvider =
  | 'ollama'
  | 'lmstudio'
  | 'llamacpp'
  | 'unsloth'
  | 'openai'
  | 'litert'
  | 'custom';

export interface ProviderPreset {
  baseUrl: string;
  needsApiKey: boolean;
  help: string;
}

export const LLM_PROVIDERS: { value: LlmProvider; label: string }[] = [
  { value: 'ollama', label: 'Ollama' },
  { value: 'lmstudio', label: 'LM Studio' },
  { value: 'llamacpp', label: 'Llama.cpp' },
  { value: 'litert', label: 'LiteRT-LM' },
  { value: 'unsloth', label: 'Unsloth' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'custom', label: 'Custom (OpenAI-compatible)' },
];

export const PROVIDER_DEFAULTS: Record<LlmProvider, ProviderPreset> = {
  ollama: {
    baseUrl: 'http://localhost:11434',
    needsApiKey: false,
    help: 'Ollama runs locally on http://localhost:11434 by default. Make sure Ollama is running — models load automatically.',
  },
  lmstudio: {
    baseUrl: 'http://localhost:1234',
    needsApiKey: false,
    help: 'LM Studio: load a model, then start its server (default http://localhost:1234). Paste the host or the full /v1 URL — both work.',
  },
  llamacpp: {
    baseUrl: 'http://localhost:8080',
    needsApiKey: false,
    help: 'llama.cpp server (llama-server) on http://localhost:8080. Modern builds speak the OpenAI API; single-model servers accept “default”.',
  },
  unsloth: {
    baseUrl: 'http://127.0.0.1:8888',
    needsApiKey: false,
    help: 'Unsloth uses an OpenAI-compatible API, typically on http://127.0.0.1:8888. Models load automatically.',
  },
  openai: {
    baseUrl: 'https://api.openai.com/v1',
    needsApiKey: true,
    help: 'Enter your OpenAI API key. The base URL defaults to https://api.openai.com/v1.',
  },
  litert: {
    baseUrl: 'http://localhost:9379',
    needsApiKey: false,
    help: 'LiteRT-LM: run `litert-lm serve` (default http://localhost:9379), then pick the exact model id from GET /v1/models.',
  },
  custom: {
    baseUrl: 'http://127.0.0.1:8080/v1',
    needsApiKey: false,
    help: 'Any OpenAI-compatible server (vLLM, llama.cpp, Ollama /v1, proxies). Paste the base URL; a pasted /v1/chat/completions endpoint is trimmed automatically.',
  },
};

export interface LlmConfig {
  provider: LlmProvider;
  baseUrl: string;
  openaiBase?: string;
  hasApiKey: boolean;
  model: string | null;
  temperature: number;
  systemPrompt: string;
  configured: boolean;
  providers?: Record<string, string>;
}

export interface LlmConfigUpdate {
  provider?: LlmProvider;
  baseUrl?: string;
  apiKey?: string;
  model?: string;
  temperature?: number;
  systemPrompt?: string;
}

export interface LlmTestResult {
  ok: boolean;
  message: string;
  models: string[];
}
