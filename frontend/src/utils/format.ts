import type { ChatSession } from '../types/chat';
import { sessionTitle } from '../types/chat';

export function displayTitle(session: ChatSession): string {
  return sessionTitle(session);
}

export function relativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) {
    return 'just now';
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 7) {
    return `${days}d ago`;
  }
  return new Date(timestamp).toLocaleDateString();
}

export function messageTime(timestamp: number): string {
  if (!timestamp) {
    return '';
  }
  return new Date(timestamp).toLocaleTimeString();
}

export function formatStats(seconds: number, chars: number): string {
  return `${seconds.toFixed(1)}s · ~${Math.max(1, Math.round(chars / 4))} tokens`;
}

export function formatModelName(model: string): string {
  return model.length > 28 ? `${model.substring(0, 28)}…` : model;
}

export function previewText(session: ChatSession, max = 120): string {
  const last = session.messages[session.messages.length - 1];
  if (!last) {
    return '';
  }
  const text = last.content.replace(/\s+/g, ' ').trim();
  return text.length > max ? `${text.substring(0, max)}…` : text;
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function slugify(text: string, max = 60): string {
  const slug = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return (slug || 'chat').substring(0, max);
}
