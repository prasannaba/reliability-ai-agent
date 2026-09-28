/** Shared HTTP + SSE plumbing used by every BackendService implementation. */
import type { ChatStreamEvent } from './types';

/** In-memory app token (`Authorization: Bearer`) for mutating API calls.
 *  SECURITY: this is NOT the LLM API key. It lives in memory only — never
 *  write it (or any LLM key) to localStorage/sessionStorage. The LLM key
 *  itself is held by the backend credential manager and never readable here.
 *  Set via VITE_APP_TOKEN at build time or setAppToken() at runtime. */
let appToken = '';

export function setAppToken(token: string): void {
  appToken = (token || '').trim();
}

export function getAppToken(): string {
  return appToken;
}

export function authHeaders(init?: HeadersInit): HeadersInit {
  if (!appToken) {
    return init ?? {};
  }
  const headers = new Headers(init);
  headers.set('Authorization', `Bearer ${appToken}`);
  return headers;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** Join a base URL ('' = same-origin) with an absolute path. */
export function joinUrl(baseUrl: string, path: string): string {
  if (!baseUrl) {
    return path;
  }
  return `${baseUrl.replace(/\/+$/, '')}${path}`;
}

/** True for URLs that must never be prefixed with a backend base URL. */
export function isDirectImageUrl(url: string): boolean {
  return /^(data|blob|https?):/i.test(url);
}

/** Resolve a backend-relative URL (e.g. `/static/plot.png`) against the
 *  backend base. Absolute/data/blob URLs pass through untouched — without
 *  this guard a non-empty base (remote backend) corrupts
 *  embedded base64 plots into unusable `http://hostdata:...` strings.
 *
 *  Stale backends may emit a bare filename or a raw filesystem path
 *  (`C:\...\static\plot.png`, `/data/.../plot.png`) instead of a URL.
 *  Those can never load in a browser, so collapse them to the served
 *  static file of the same name. */
export function resolveBackendUrl(baseUrl: string, url: string): string {
  if (!url) {
    return url;
  }
  if (/^https?:\/\//i.test(url)) {
    // Absolute backend URL on our own host (any loopback spelling) → collapse
    // to a same-origin path so CSP/CORS can never diverge on hostnames.
    // Anything else absolute stays untouched.
    try {
      const collapsed = collapseBackendUrl(baseUrl, new URL(url));
      if (collapsed) {
        return collapsed;
      }
    } catch {
      // Not parseable as an absolute URL — fall through to the cases below.
    }
    return url;
  }
  if (isDirectImageUrl(url)) {
    return url;
  }
  // A Windows drive prefix (`C:\...`, `C:/...`) is a filesystem path, not
  // a URL scheme — fall through to basename healing below.
  if (!/^[A-Za-z]:[\\/]/.test(url) && /^[A-Za-z][A-Za-z0-9+.-]*:/.test(url)) {
    return url; // unknown scheme (e.g. file:) — leave untouched
  }
  if (
    url.startsWith('/static/') ||
    url.startsWith('/api/') ||
    url === '/health' ||
    url.startsWith('/health?')
  ) {
    return joinUrl(baseUrl, url);
  }
  // Anything else is a bare filename or a raw filesystem path, neither of
  // which can load in a webview — collapse to the served file of the same name.
  const name = url.split(/[\\/]/).pop() || url;
  return joinUrl(baseUrl, `/static/${name}`);
}

/** True for loopback hostnames (`localhost`, `127.*`, `::1`). */
export function isLoopbackHost(hostname: string): boolean {
  const h = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  return (
    h === 'localhost' ||
    h === '::1' ||
    /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(h)
  );
}

function defaultPortFor(scheme: string): string {
  return scheme === 'https:' ? '443' : '80';
}

/** Collapse an absolute backend URL to a same-origin path when it addresses
 *  the backend we are already talking to (loopback spellings like
 *  `localhost` vs `127.0.0.1` count as the same host). Without this, a plot
 *  URL baked with one spelling breaks on a page opened with another: the
 *  browser treats it as cross-origin, `img-src 'self'` blocks the image and
 *  CORS blocks the download fetch. Returns null when no collapse applies. */
function collapseBackendUrl(baseUrl: string, url: URL): string | null {
  let ref: URL | null = null;
  try {
    if (baseUrl) {
      ref = new URL(baseUrl);
    } else if (typeof window !== 'undefined' && window.location?.origin) {
      ref = new URL(window.location.origin);
    }
  } catch {
    ref = null;
  }
  if (!ref || url.protocol !== ref.protocol) {
    return null;
  }
  const sameHost =
    url.hostname === ref.hostname ||
    (isLoopbackHost(url.hostname) && isLoopbackHost(ref.hostname));
  const samePort = (url.port || defaultPortFor(url.protocol)) === (ref.port || defaultPortFor(ref.protocol));
  if (!sameHost || !samePort) {
    return null;
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

/** Decode a `data:` URL to a Blob (for plot downloads without a fetch round-trip). */
export function dataUrlToBlob(url: string): Blob {
  const comma = url.indexOf(',');
  const header = url.slice(5, comma);
  const body = url.slice(comma + 1);
  const mime = header.split(';')[0] || 'application/octet-stream';
  if (/;base64$/i.test(header)) {
    const binary = atob(body);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return new Blob([bytes], { type: mime });
  }
  return new Blob([decodeURIComponent(body)], { type: mime });
}

function errorDetail(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === 'string' && detail) {
      return detail;
    }
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) =>
          d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : null,
        )
        .filter(Boolean);
      if (msgs.length) {
        return msgs.join('; ');
      }
    }
  }
  return fallback;
}

export async function requestJson<T>(
  baseUrl: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = authHeaders(init?.headers);
  const response = await fetch(joinUrl(baseUrl, path), { ...init, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      message = errorDetail(await response.json(), message);
    } catch {
      // keep fallback
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

/** Split one SSE buffer into complete events; returns leftovers as `rest`. */
export function parseSseFrames(buffer: string): { events: ChatStreamEvent[]; rest: string } {
  const events: ChatStreamEvent[] = [];
  const frames = buffer.split('\n\n');
  const rest = frames.pop() ?? '';
  for (const frame of frames) {
    const dataLine = frame
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .join('');
    if (!dataLine) {
      continue;
    }
    try {
      events.push(JSON.parse(dataLine) as ChatStreamEvent);
    } catch {
      // Skip malformed frames; the terminal done/error frame carries the result.
    }
  }
  return { events, rest };
}

/** POST an SSE endpoint and forward parsed events. Resolves on stream end. */
export async function streamSse(
  baseUrl: string,
  path: string,
  body: unknown,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(joinUrl(baseUrl, path), {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new ApiError(response.status, `Chat stream failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseFrames(buffer);
    buffer = parsed.rest;
    for (const event of parsed.events) {
      onEvent(event);
    }
  }
  // Flush any trailing frame not terminated by a blank line.
  if (buffer.trim()) {
    const parsed = parseSseFrames(`${buffer}\n\n`);
    for (const event of parsed.events) {
      onEvent(event);
    }
  }
}
