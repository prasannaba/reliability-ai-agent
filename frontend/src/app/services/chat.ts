import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import type { LlmConfig, LlmConfigUpdate, LlmTestResult } from '../models/llm-config.model';

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

export interface LlmModelsResponse {
  configured: boolean;
  models: string[];
  current: string | null;
  base: string;
  provider?: string;
  providers?: Record<string, string>;
  error?: string;
}

@Injectable({
  providedIn: 'root',
})
export class ChatService {
  constructor(private http: HttpClient) {}

  listModels(): Observable<LlmModelsResponse> {
    return this.http.get<LlmModelsResponse>('/api/models');
  }

  getLlmConfig(): Observable<LlmConfig> {
    return this.http.get<LlmConfig>('/api/llm/config');
  }

  saveLlmConfig(update: LlmConfigUpdate): Observable<LlmConfig> {
    return this.http.put<LlmConfig>('/api/llm/config', update);
  }

  testLlmConfig(update: LlmConfigUpdate): Observable<LlmTestResult> {
    return this.http.post<LlmTestResult>('/api/llm/test', update);
  }

  knowledgeStatus(): Observable<KnowledgeStatus> {
    return this.http.get<KnowledgeStatus>('/api/knowledge/status');
  }

  uploadDocument(file: File): Observable<{ source: string; indexed: boolean; message: string }> {
    const body = new FormData();
    body.append('file', file);
    return this.http.post<{ source: string; indexed: boolean; message: string }>(
      '/api/knowledge/upload',
      body,
    );
  }

  async streamMessage(
    prompt: string,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
    model?: string,
    thinking = true,
  ): Promise<void> {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ prompt, model, thinking } satisfies ChatRequest),
      signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(`Chat stream failed (${response.status})`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';
      for (const frame of frames) {
        const dataLine = frame
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim())
          .join('');
        if (!dataLine) {
          continue;
        }
        onEvent(JSON.parse(dataLine) as ChatStreamEvent);
      }
    }
  }
}
