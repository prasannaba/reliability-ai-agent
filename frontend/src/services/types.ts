/**
 * Service boundary types.
 *
 * React UI imports ONLY this file (plus the `getServices()` singleton in
 * `services/index.ts`). The browser implementation lives in
 * `services/browser/` — components never touch `fetch('/api/...')`,
 * `localStorage`, or `window.open` directly.
 */
import type {
  LlmConfig,
  LlmConfigUpdate,
  LlmModelsResponse,
  LlmTestResult,
} from '../types/llm';

export interface ChatRequest {
  prompt: string;
  model?: string;
  thinking?: boolean;
}

export type ChatStreamEvent =
  | { type: 'token'; text: string }
  | { type: 'thought'; text: string }
  | { type: 'tool_start'; name: string }
  | { type: 'tool_end'; name: string }
  | { type: 'image'; url: string }
  | { type: 'done'; content: string; image_url: string | null }
  | { type: 'error'; message: string };

export interface KnowledgeFileStatus {
  source: string;
  chunks: number | null;
  indexed: boolean;
}

export interface KnowledgeStatus {
  embedding_model: string;
  files: KnowledgeFileStatus[];
  chunk_count: number;
}

export interface UploadResult {
  source: string;
  indexed: boolean;
  message: string;
}

/** Active pluggable domain served by the backend (`GET /api/domains`). */
export interface DomainSummary {
  active: string;
  domains: string[];
  title: string;
}

/** One MCP tool exposed by the active domain (`GET /api/mcp/tools`). */
export interface McpToolSummary {
  name: string;
  description: string;
}

export interface McpToolsResponse {
  domain: string;
  count: number;
  tools: McpToolSummary[];
}

/**
 * Agent/backend operations over HTTP against the FastAPI backend
 * (same-origin or remote). The React app never speaks MCP stdio
 * directly — the Python backend does.
 */
export interface BackendService {
  readonly kind: 'browser';
  /** Base URL, '' means same-origin (web dev/prod default). */
  readonly baseUrl: string;
  listModels(signal?: AbortSignal): Promise<LlmModelsResponse>;
  getLlmConfig(signal?: AbortSignal): Promise<LlmConfig>;
  saveLlmConfig(update: LlmConfigUpdate, signal?: AbortSignal): Promise<LlmConfig>;
  testLlmConfig(update: LlmConfigUpdate, signal?: AbortSignal): Promise<LlmTestResult>;
  knowledgeStatus(signal?: AbortSignal): Promise<KnowledgeStatus>;
  uploadDocument(file: File, signal?: AbortSignal): Promise<UploadResult>;
  /** Active domain pack (name, available domains, display title). */
  getDomains(signal?: AbortSignal): Promise<DomainSummary>;
  /** Tool inventory of every connected MCP server for the active domain. */
  listMcpTools(signal?: AbortSignal): Promise<McpToolsResponse>;
  streamMessage(
    prompt: string,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
    model?: string,
    thinking?: boolean,
  ): Promise<void>;
  /** Fetch a backend-hosted file (e.g. plot image) as a Blob. */
  downloadFile(url: string, signal?: AbortSignal): Promise<Blob>;
  /** Make a backend-relative URL absolute (no-op on web same-origin). */
  resolveStaticUrl(url: string): string;
}

/** Synchronous key/value store (localStorage-backed on both targets today). */
export interface Storage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** Browser capabilities used by the UI (storage, clipboard, downloads, print). */
export interface PlatformService {
  readonly kind: 'browser';
  readonly storage: Storage;
  copyText(text: string): Promise<void>;
  downloadBlob(blob: Blob, fileName: string): Promise<void>;
  /** Render printable HTML (PDF flow prints via the browser print dialog). */
  printHtml(title: string, html: string): Promise<void>;
}

export interface Services {
  readonly backend: BackendService;
  readonly platform: PlatformService;
}
