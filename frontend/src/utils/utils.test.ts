import { describe, expect, it } from 'vitest';
import { newMessageId, sessionTitle, type ChatSession } from '../types/chat';
import { patchMarkdownMath } from '../utils/mathMarkdown';

function sessionWith(messages: string[], title = 'Chat 1'): ChatSession {
  return {
    id: 's1',
    title,
    updatedAt: Date.now(),
    messages: messages.map((content, i) => ({
      id: `m${i}`,
      role: i % 2 === 0 ? 'user' : 'assistant',
      content,
      timestamp: Date.now(),
    })),
  };
}

describe('sessionTitle', () => {
  it('keeps custom titles', () => {
    expect(sessionTitle(sessionWith(['hi'], 'My analysis'))).toBe('My analysis');
  });

  it('derives title from first user message', () => {
    expect(sessionTitle(sessionWith(['What is the B10 life?']))).toBe('What is the B10 life?');
  });

  it('truncates long first messages with ellipsis', () => {
    const long = 'x'.repeat(60);
    expect(sessionTitle(sessionWith([long]))).toBe(`${'x'.repeat(48)}…`);
  });

  it('falls back to Untitled chat', () => {
    expect(sessionTitle(sessionWith([]))).toBe('Untitled chat');
  });
});

describe('newMessageId', () => {
  it('generates unique ids', () => {
    const ids = new Set(Array.from({ length: 100 }, () => newMessageId()));
    expect(ids.size).toBe(100);
  });
});

describe('patchMarkdownMath', () => {
  it('leaves plain text alone', () => {
    expect(patchMarkdownMath('Hello world')).toBe('Hello world');
  });

  it('normalises display math to $$', () => {
    expect(patchMarkdownMath('\\[x^2\\]')).toContain('$$');
  });

  it('protects subscripts from markdown emphasis', () => {
    const out = patchMarkdownMath('The value $B_10$ matters');
    expect(out).toContain('\\sb{10}');
    expect(out).not.toContain('_10');
  });
});
