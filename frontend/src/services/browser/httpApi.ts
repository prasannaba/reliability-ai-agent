/** HTTP/API → Remote backend (browser). Same FastAPI contract, base URL configurable. */
import type {
  LlmConfig,
  LlmConfigUpdate,
  LlmModelsResponse,
  LlmTestResult,
} from '../../types/llm';
import type {
  BackendService,
  ChatStreamEvent,
  DomainSummary,
  KnowledgeStatus,
  McpToolsResponse,
  UploadResult,
} from '../types';
import { ApiError, dataUrlToBlob, isDirectImageUrl, requestJson, resolveBackendUrl, streamSse } from '../http';

export interface HttpApiOptions {
  /** '' = same-origin (dev proxy / served UI). Set VITE_BACKEND_URL for remote. */
  baseUrl?: string;
}

export function createHttpApi(options: HttpApiOptions = {}): BackendService {
  const baseUrl = options.baseUrl ?? '';
  const req = <T>(path: string, init?: RequestInit) => requestJson<T>(baseUrl, path, init);

  return {
    kind: 'browser',
    baseUrl,

    listModels: (signal?: AbortSignal) => req<LlmModelsResponse>('/api/models', { signal }),

    getLlmConfig: (signal?: AbortSignal) => req<LlmConfig>('/api/llm/config', { signal }),

    saveLlmConfig: (update: LlmConfigUpdate, signal?: AbortSignal) =>
      req<LlmConfig>('/api/llm/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
        signal,
      }),

    testLlmConfig: (update: LlmConfigUpdate, signal?: AbortSignal) =>
      req<LlmTestResult>('/api/llm/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
        signal,
      }),

    knowledgeStatus: (signal?: AbortSignal) =>
      req<KnowledgeStatus>('/api/knowledge/status', { signal }),

    uploadDocument: (file: File, signal?: AbortSignal) => {
      const body = new FormData();
      body.append('file', file);
      return req<UploadResult>('/api/knowledge/upload', { method: 'POST', body, signal });
    },

    getDomains: (signal?: AbortSignal) =>
      req<DomainSummary>('/api/domains', { signal }),

    listMcpTools: (signal?: AbortSignal) =>
      req<McpToolsResponse>('/api/mcp/tools', { signal }),

    streamMessage: (
      prompt: string,
      onEvent: (event: ChatStreamEvent) => void,
      signal?: AbortSignal,
      model?: string,
      thinking = true,
    ) => streamSse(baseUrl, '/api/chat/stream', { prompt, model, thinking }, onEvent, signal),

    downloadFile: async (url: string, signal?: AbortSignal) => {
      if (isDirectImageUrl(url) && url.startsWith('data:')) {
        return dataUrlToBlob(url);
      }
      // Normalized (not raw joinUrl): heals bare filenames/filesystem
      // paths from stale backends into fetchable /static/ URLs.
      const response = await fetch(resolveBackendUrl(baseUrl, url), { signal });
      if (!response.ok) {
        throw new ApiError(response.status, `Download failed (${response.status})`);
      }
      return response.blob();
    },

    resolveStaticUrl: (url: string) => resolveBackendUrl(baseUrl, url),
  };
}
