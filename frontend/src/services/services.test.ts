import { describe, expect, it } from 'vitest';
import { dataUrlToBlob, parseSseFrames, resolveBackendUrl } from './http';
import { _resetServicesForTests, getServices } from './index';

describe('SSE frame parsing', () => {
  it('parses token and done frames', () => {
    const { events, rest } = parseSseFrames(
      'data: {"type":"token","text":"Hello"}\n\ndata: {"type":"done","content":"Hello","image_url":null}\n\n',
    );
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: 'token', text: 'Hello' });
    expect(events[1]).toEqual({ type: 'done', content: 'Hello', image_url: null });
    expect(rest).toBe('');
  });

  it('keeps partial frames in rest', () => {
    const { events, rest } = parseSseFrames('data: {"type":"token","text":"Hi"}\n\ndata: {"type":"tok');
    expect(events).toHaveLength(1);
    expect(rest).toBe('data: {"type":"tok');
  });

  it('skips malformed frames', () => {
    const { events } = parseSseFrames('data: not-json\n\ndata: {"type":"error","message":"x"}\n\n');
    expect(events).toEqual([{ type: 'error', message: 'x' }]);
  });
});

describe('plot URL resolution', () => {
  it('prefixes backend-relative plot paths', () => {
    expect(resolveBackendUrl('http://127.0.0.1:8000', '/static/plot.png')).toBe(
      'http://127.0.0.1:8000/static/plot.png',
    );
    expect(resolveBackendUrl('', '/static/plot.png')).toBe('/static/plot.png');
  });

  it('leaves embedded/absolute image URLs untouched', () => {
    const dataUrl = 'data:image/png;base64,iVBORw0KGgo=';
    expect(resolveBackendUrl('http://127.0.0.1:8000', dataUrl)).toBe(dataUrl);
    expect(resolveBackendUrl('http://127.0.0.1:8000', 'https://x/y.png')).toBe('https://x/y.png');
  });

  it('heals stale-backend file payloads into served static URLs', () => {
    // Bare filename from MCP `file` field.
    expect(resolveBackendUrl('http://127.0.0.1:8000', 'weibull_abc.png')).toBe(
      'http://127.0.0.1:8000/static/weibull_abc.png',
    );
    // Raw Windows filesystem path — unrenderable in a
    // webview, so collapse to the served file of the same name.
    expect(resolveBackendUrl('http://127.0.0.1:8000', 'C:\\Users\\x\\backend\\static\\weibull_abc.png')).toBe(
      'http://127.0.0.1:8000/static/weibull_abc.png',
    );
    // POSIX path likewise.
    expect(resolveBackendUrl('', '/data/app/backend/static/weibull_abc.png')).toBe(
      '/static/weibull_abc.png',
    );
  });

  it('decodes data URLs to blobs', () => {
    const blob = dataUrlToBlob('data:image/png;base64,aGk=');
    expect(blob.type).toBe('image/png');
    expect(blob.size).toBeGreaterThan(0);
  });
});

describe('service selection', () => {
  it('defaults to the browser bundle', async () => {
    _resetServicesForTests();
    const services = await getServices();
    expect(services.backend.kind).toBe('browser');
    expect(services.platform.kind).toBe('browser');
    _resetServicesForTests();
  });
});
