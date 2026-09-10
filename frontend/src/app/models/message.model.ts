export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  model?: string;
  /** Rendered stats line, e.g. "12.3s · ~328 tokens" (MDLithe-style). */
  stats?: string;
  imageUrl?: string;
  thinkingText?: string;
  thinkingSteps?: string[];
  thinkingOpen?: boolean;
  thinkingMs?: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
}

export function newMessageId(): string {
  return `${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`;
}

export function sessionTitle(session: ChatSession): string {
  if (!/^Chat \d+$/.test(session.title)) {
    return session.title;
  }
  const firstUser = session.messages.find((m) => m.role === 'user');
  const full = (firstUser?.content ?? '').replace(/\s+/g, ' ').trim();
  if (full) {
    return full.length > 48 ? `${full.substring(0, 48)}…` : full;
  }
  return 'Untitled chat';
}
