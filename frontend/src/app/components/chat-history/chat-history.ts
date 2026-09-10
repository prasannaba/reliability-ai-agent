import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { sessionTitle, type ChatSession } from '../../models/message.model';

@Component({
  selector: 'app-chat-history',
  imports: [FormsModule],
  templateUrl: './chat-history.html',
  styleUrls: ['./chat-history.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatHistoryComponent {
  readonly query = signal('');
  readonly selectedIndex = signal(0);
  readonly sessions = signal<ChatSession[]>([]);
  readonly currentId = signal<string | null>(null);
  readonly onSelect = signal<(id: string) => void>(() => undefined);
  readonly onNew = signal<() => void>(() => undefined);
  readonly onDelete = signal<(id: string) => void>(() => undefined);
  readonly onClose = signal<() => void>(() => undefined);

  readonly filtered = computed(() => {
    const q = this.query().trim().toLowerCase();
    const all = [...this.sessions()].sort((a, b) => b.updatedAt - a.updatedAt);
    if (!q) {
      return all;
    }
    const parts = q.split(/\s+/);
    return all.filter((s) => {
      const haystack =
        `${sessionTitle(s)} ${s.messages.map((m) => m.content).join(' ')}`.toLowerCase();
      return parts.every((part) => haystack.includes(part));
    });
  });

  open(
    sessions: ChatSession[],
    currentId: string | null,
    handlers: {
      onSelect: (id: string) => void;
      onNew: () => void;
      onDelete: (id: string) => void;
      onClose: () => void;
    },
  ): void {
    this.sessions.set(sessions);
    this.currentId.set(currentId);
    this.query.set('');
    this.selectedIndex.set(0);
    this.onSelect.set(handlers.onSelect);
    this.onNew.set(handlers.onNew);
    this.onDelete.set(handlers.onDelete);
    this.onClose.set(handlers.onClose);
  }

  displayTitle(session: ChatSession): string {
    return sessionTitle(session);
  }

  preview(session: ChatSession): string {
    const last = session.messages[session.messages.length - 1];
    if (!last) {
      return '';
    }
    const text = last.content.replace(/\s+/g, ' ').trim();
    return text.length > 120 ? `${text.substring(0, 120)}…` : text;
  }

  relativeTime(timestamp: number): string {
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

  choose(index: number): void {
    if (index === 0) {
      this.onNew()();
      this.onClose()();
      return;
    }
    const session = this.filtered()[index - 1];
    if (session) {
      this.onSelect()(session.id);
      this.onClose()();
    }
  }

  remove(session: ChatSession, event: Event): void {
    event.stopPropagation();
    if (window.confirm(`Delete "${this.displayTitle(session)}"?`)) {
      this.onDelete()(session.id);
    }
  }

  onKeydown(event: KeyboardEvent): void {
    const rows = this.filtered().length + 1;
    if (event.key === 'Escape') {
      event.preventDefault();
      this.onClose()();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.selectedIndex.update((i) => Math.min(i + 1, rows - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.selectedIndex.update((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      this.choose(this.selectedIndex());
    }
  }
}
