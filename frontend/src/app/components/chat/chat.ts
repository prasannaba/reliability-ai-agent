import {
  Component,
  ViewChild,
  ElementRef,
  AfterViewInit,
  ChangeDetectorRef,
  OnInit,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChatService } from '../../services/chat';
import {
  ChatSession,
  Message,
  newMessageId,
  sessionTitle,
} from '../../models/message.model';
import type { LlmConfig } from '../../models/llm-config.model';
import { MarkdownModule } from 'ngx-markdown';
import { patchMarkdownMath } from '../../utils/math-markdown';
import { LlmSettingsComponent } from '../llm-settings/llm-settings';
import { IconComponent } from '../icon/icon';

interface ExportFormat {
  label: string;
  value: 'markdown' | 'html' | 'pdf';
}

declare var MathJax: any;

const SESSIONS_KEY = 'reliability-copilot-sessions';
const CURRENT_KEY = 'reliability-copilot-current';
const WELCOME =
  'Reliability Copilot — ask a life-data or handbook question. Numbers come from tools, not guesses. Attach a procedure on the prompt if you want it in the knowledge base.';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [FormsModule, MarkdownModule, LlmSettingsComponent, IconComponent],
  templateUrl: './chat.html',
  styleUrls: ['./chat.css'],
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(document:keydown.escape)': 'closeModelList()',
  },
})
export class ChatComponent implements OnInit, AfterViewInit {
  @ViewChild('messageContainer') private messageContainer!: ElementRef;
  @ViewChild('promptBox') private promptBox?: ElementRef<HTMLTextAreaElement>;
  @ViewChild('modelSelector') private modelSelector?: ElementRef;
  @ViewChild('exportMenu') private exportMenu?: ElementRef;
  @ViewChild(LlmSettingsComponent) private settingsDialog!: LlmSettingsComponent;

  sessions: ChatSession[] = [];
  currentId: string | null = null;
  messages: Message[] = [];
  userInput: string = '';
  isLoading = false;
  streaming = false;
  error: string | null = null;
  knowledgeSummary: string = '';
  exportFormats: ExportFormat[] = [
    { label: 'Markdown', value: 'markdown' },
    { label: 'HTML', value: 'html' },
    { label: 'PDF', value: 'pdf' },
  ];
  selectedExportFormat: ExportFormat['value'] = 'markdown';
  models: string[] = [];
  selectedModel = '';
  provider = 'custom';
  modelsHint = '';
  modelsLoading = false;
  modelListOpen = false;
  thinkingEnabled = true;
  showSettings = false;
  sidebarOpen = true;
  historyQuery = '';
  exportMenuOpen = false;
  editingId: string | null = null;
  editingContent = '';
  copiedId: string | null = null;

  private llmConfig: LlmConfig | null = null;
  private thinkingStartedAt = 0;
  private aborter: AbortController | null = null;
  private chatCounter = 0;

  constructor(
    private chatService: ChatService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit() {
    if (typeof window !== 'undefined' && window.innerWidth < 860) {
      this.sidebarOpen = false;
    }
    this.loadThinkingPref();
    this.loadSessions();
    this.refreshKnowledgeStatus();
    this.refreshLlmConfig(() => this.refreshModels());
    setTimeout(() => this.renderMath(), 100);
  }

  ngAfterViewInit() {
    this.scrollToBottom();
  }

  // ---- sessions (MDLithe-style, localStorage) ----

  get currentSession(): ChatSession | undefined {
    return this.sessions.find((s) => s.id === this.currentId);
  }

  get currentTitle(): string {
    const s = this.currentSession;
    return s ? sessionTitle(s) : 'New chat';
  }

  private loadSessions(): void {
    try {
      const raw = localStorage.getItem(SESSIONS_KEY);
      const current = localStorage.getItem(CURRENT_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as ChatSession[];
        if (Array.isArray(parsed) && parsed.length) {
          this.sessions = parsed;
          this.chatCounter = parsed.length;
          this.currentId = current && parsed.some((s) => s.id === current) ? current : parsed[0].id;
          this.messages = this.currentSession?.messages ?? [];
          return;
        }
      }
    } catch {
      // fall through to fresh session
    }
    this.newChat(false);
  }

  private persistSessions(): void {
    try {
      localStorage.setItem(SESSIONS_KEY, JSON.stringify(this.sessions.slice(0, 50)));
      if (this.currentId) {
        localStorage.setItem(CURRENT_KEY, this.currentId);
      }
    } catch {
      // storage full / unavailable — chat still works in memory
    }
  }

  private syncMessages(): void {
    const session = this.currentSession;
    if (session) {
      session.messages = this.messages;
      session.updatedAt = Date.now();
      this.persistSessions();
    }
  }

  newChat(select = true): void {
    this.chatCounter += 1;
    const session: ChatSession = {
      id: newMessageId(),
      title: `Chat ${this.chatCounter}`,
      messages: [
        {
          id: newMessageId(),
          role: 'assistant',
          content: WELCOME,
          timestamp: Date.now(),
        },
      ],
      updatedAt: Date.now(),
    };
    this.sessions = [session, ...this.sessions];
    if (select) {
      this.currentId = session.id;
      this.messages = session.messages;
    } else if (!this.currentId) {
      this.currentId = session.id;
      this.messages = session.messages;
    }
    this.error = null;
    this.persistSessions();
    this.cdr.detectChanges();
    this.scrollToBottom();
  }

  selectSession(id: string): void {
    const session = this.sessions.find((s) => s.id === id);
    if (!session) {
      return;
    }
    this.currentId = id;
    this.messages = session.messages;
    this.error = null;
    this.persistSessions();
    if (typeof window !== 'undefined' && window.innerWidth < 860) {
      this.sidebarOpen = false;
    }
    this.cdr.detectChanges();
    this.scrollToBottom();
    setTimeout(() => this.renderMath(), 50);
  }

  deleteSession(id: string): void {
    this.sessions = this.sessions.filter((s) => s.id !== id);
    if (this.currentId === id) {
      if (!this.sessions.length) {
        this.newChat(false);
        this.currentId = this.sessions[0].id;
        this.messages = this.sessions[0].messages;
      } else {
        this.currentId = this.sessions[0].id;
        this.messages = this.sessions[0].messages;
      }
    }
    this.persistSessions();
    this.cdr.detectChanges();
  }

  clearChat(): void {
    this.messages = [
      { id: newMessageId(), role: 'assistant', content: WELCOME, timestamp: Date.now() },
    ];
    this.error = null;
    this.syncMessages();
    this.cdr.detectChanges();
    this.scrollToBottom();
  }

  // ---- sidebar: history + settings (ChatGPT-style) ----

  toggleSidebar(): void {
    this.sidebarOpen = !this.sidebarOpen;
  }

  filteredSessions(): ChatSession[] {
    const q = this.historyQuery.trim().toLowerCase();
    const all = [...this.sessions].sort((a, b) => b.updatedAt - a.updatedAt);
    if (!q) {
      return all;
    }
    const parts = q.split(/\s+/);
    return all.filter((s) => {
      const haystack =
        `${sessionTitle(s)} ${s.messages.map((m) => m.content).join(' ')}`.toLowerCase();
      return parts.every((part) => haystack.includes(part));
    });
  }

  displayTitle(session: ChatSession): string {
    return sessionTitle(session);
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

  confirmDeleteSession(session: ChatSession, event: Event): void {
    event.stopPropagation();
    if (window.confirm(`Delete "${sessionTitle(session)}"?`)) {
      this.deleteSession(session.id);
    }
  }

  // ---- settings ----

  openSettings(): void {
    this.showSettings = true;
    this.cdr.detectChanges();
    const fallback: LlmConfig = {
      provider: (this.provider as LlmConfig['provider']) || 'custom',
      baseUrl: '',
      hasApiKey: false,
      model: this.selectedModel || null,
      temperature: 0.7,
      systemPrompt: '',
      configured: false,
    };
    setTimeout(() =>
      this.settingsDialog.open(this.llmConfig || fallback, (saved) => {
        this.showSettings = false;
        if (saved) {
          this.refreshLlmConfig(() => this.refreshModels());
        }
        this.cdr.detectChanges();
      }),
    );
  }

  private refreshLlmConfig(done?: () => void): void {
    this.chatService.getLlmConfig().subscribe({
      next: (config) => {
        this.llmConfig = config;
        this.provider = config.provider || 'custom';
        if (config.model && !this.selectedModel) {
          this.selectedModel = config.model;
        }
        done?.();
        this.cdr.detectChanges();
      },
      error: () => done?.(),
    });
  }

  // ---- models (MDLithe-style dropdown with refresh + manual entry) ----

  toggleModelList(): void {
    this.modelListOpen = !this.modelListOpen;
    if (this.modelListOpen) {
      this.exportMenuOpen = false;
    }
  }

  onDocumentClick(event: MouseEvent): void {
    const target = event.target as Node;
    if (this.modelListOpen) {
      const el = this.modelSelector?.nativeElement as HTMLElement | undefined;
      if (el && !el.contains(target)) {
        this.modelListOpen = false;
      }
    }
    if (this.exportMenuOpen) {
      const el = this.exportMenu?.nativeElement as HTMLElement | undefined;
      if (el && !el.contains(target)) {
        this.exportMenuOpen = false;
      }
    }
    if (this.modelListOpen || this.exportMenuOpen) {
      this.cdr.detectChanges();
    }
  }

  closeModelList(): void {
    this.modelListOpen = false;
    this.exportMenuOpen = false;
  }

  toggleExportMenu(): void {
    this.exportMenuOpen = !this.exportMenuOpen;
    if (this.exportMenuOpen) {
      this.modelListOpen = false;
    }
  }

  chooseModel(model: string): void {
    this.selectedModel = model;
    this.modelListOpen = false;
    this.persistModelChoice();
  }

  onModelManualChange(): void {
    this.persistModelChoice();
  }

  private persistModelChoice(): void {
    if (!this.selectedModel) {
      return;
    }
    this.chatService.saveLlmConfig({ model: this.selectedModel }).subscribe({
      next: (config) => {
        this.llmConfig = config;
      },
      error: () => undefined,
    });
  }

  refreshModels(): void {
    this.modelsLoading = true;
    this.chatService.listModels().subscribe({
      next: (result) => {
        this.modelsLoading = false;
        this.models = result.models || [];
        this.provider = result.provider || this.provider;
        if (result.current && !this.selectedModel) {
          this.selectedModel = result.current;
        } else if (this.llmConfig?.model && !this.selectedModel) {
          this.selectedModel = this.llmConfig.model;
        } else if (this.selectedModel && this.models.length && !this.models.includes(this.selectedModel)) {
          // Keep manual entries (single-model servers like "default");
          // only fall back when the list is non-empty and ours is absent
          // and no explicit preference exists.
        } else if (!this.selectedModel) {
          this.selectedModel = this.models[0] || '';
        }
        this.modelsHint = result.error || '';
        this.cdr.detectChanges();
      },
      error: () => {
        this.modelsLoading = false;
        this.models = [];
        this.selectedModel = '';
        this.modelsHint =
          'Could not load models. Open Settings to pick a provider (Ollama, LM Studio, llama.cpp, …) and test the connection.';
        this.cdr.detectChanges();
      },
    });
  }

  formatModelName(model: string): string {
    return model.length > 28 ? `${model.substring(0, 28)}…` : model;
  }

  shortModelName(id: string): string {
    const slash = id.replace(/\\/g, '/').split('/').pop() || id;
    return slash.length > 48 ? `${slash.slice(0, 45)}…` : slash;
  }

  providerLabel(): string {
    return this.provider || 'custom';
  }

  // ---- message actions (MDLithe-style) ----

  get canSend(): boolean {
    return !!this.userInput.trim() && !this.isLoading;
  }

  copyMessage(msg: Message): void {
    const text = msg.content || '';
    if (!text) {
      return;
    }
    const done = () => {
      this.copiedId = msg.id;
      this.cdr.detectChanges();
      setTimeout(() => {
        this.copiedId = null;
        this.cdr.detectChanges();
      }, 1500);
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => done());
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
      } catch {
        // clipboard unavailable
      }
      document.body.removeChild(ta);
      done();
    }
  }

  startEdit(msg: Message): void {
    this.editingId = msg.id;
    this.editingContent = msg.content;
  }

  cancelEdit(): void {
    this.editingId = null;
    this.editingContent = '';
  }

  saveEdit(): void {
    if (!this.editingId) {
      return;
    }
    const index = this.messages.findIndex((m) => m.id === this.editingId);
    if (index < 0) {
      this.cancelEdit();
      return;
    }
    const edited = this.messages[index];
    edited.content = this.editingContent;
    // Editing a user message drops later replies and re-runs the assistant.
    if (edited.role === 'user') {
      this.messages = this.messages.slice(0, index + 1);
      this.syncMessages();
      this.cancelEdit();
      void this.runCompletion(this.messages[index].content, true);
    } else {
      this.syncMessages();
      this.cancelEdit();
      this.cdr.detectChanges();
    }
  }

  regenerate(): void {
    if (this.isLoading || !this.messages.length) {
      return;
    }
    let lastUserIdx = -1;
    this.messages.forEach((m, i) => {
      if (m.role === 'user') {
        lastUserIdx = i;
      }
    });
    if (lastUserIdx < 0) {
      return;
    }
    const prompt = this.messages[lastUserIdx].content;
    this.messages = this.messages.slice(0, lastUserIdx + 1);
    this.syncMessages();
    void this.runCompletion(prompt, true);
  }

  stopGenerating(): void {
    this.aborter?.abort();
  }

  formatStats(seconds: number, chars: number): string {
    return `${seconds.toFixed(1)}s · ~${Math.max(1, Math.round(chars / 4))} tokens`;
  }

  messageTime(timestamp: number): string {
    if (!timestamp) {
      return '';
    }
    return new Date(timestamp).toLocaleTimeString();
  }

  // ---- send / stream ----

  displayContent(content: string): string {
    return patchMarkdownMath(content || '');
  }

  hasThinking(msg: Message, index: number): boolean {
    if (this.isLoading && index === this.messages.length - 1 && msg.role === 'assistant') {
      return true;
    }
    return !!msg.thinkingText?.trim() || !!msg.thinkingSteps?.length;
  }

  thinkingTitle(msg: Message, index: number): string {
    const running = this.isLoading && index === this.messages.length - 1;
    if (running) {
      return 'Thinking';
    }
    const seconds = Math.max(1, Math.round((msg.thinkingMs ?? 0) / 1000));
    return `Thought · ${seconds}s`;
  }

  toggleThinking(msg: Message): void {
    msg.thinkingOpen = !msg.thinkingOpen;
  }

  persistThinkingPref(): void {
    localStorage.setItem('reliability-copilot-thinking', this.thinkingEnabled ? '1' : '0');
  }

  private loadThinkingPref(): void {
    this.thinkingEnabled = localStorage.getItem('reliability-copilot-thinking') !== '0';
  }

  private appendThinkingText(msg: Message, chunk: string): void {
    if (!this.thinkingEnabled || !chunk) {
      return;
    }
    msg.thinkingText = `${msg.thinkingText || ''}${chunk}`;
    msg.thinkingOpen = true;
  }

  private appendThought(msg: Message, step: string): void {
    if (!this.thinkingEnabled) {
      return;
    }
    const text = step.replace(/\s+/g, ' ').trim();
    if (!text) {
      return;
    }
    const steps = msg.thinkingSteps ?? (msg.thinkingSteps = []);
    if (steps[steps.length - 1] === text) {
      return;
    }
    steps.push(text);
    msg.thinkingOpen = true;
  }

  private formatToolName(name: string): string {
    return name.replace(/_/g, ' ');
  }

  onPromptKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void this.sendMessage();
    }
  }

  resizePrompt(): void {
    const el = this.promptBox?.nativeElement;
    if (!el) {
      return;
    }
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  async sendMessage() {
    if (!this.userInput.trim() || this.isLoading) {
      return;
    }
    const prompt = this.userInput;
    this.userInput = '';
    this.resizePrompt();
    const userMessage: Message = {
      id: newMessageId(),
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
    };
    this.messages.push(userMessage);
    this.syncMessages();
    await this.runCompletion(prompt, false);
  }

  private async runCompletion(prompt: string, isRerun: boolean) {
    void isRerun;
    void prompt;
    const activePrompt = this.messages.filter((m) => m.role === 'user').pop()?.content ?? prompt;
    this.isLoading = true;
    this.streaming = true;
    this.error = null;
    this.thinkingStartedAt = Date.now();
    this.aborter = new AbortController();
    const signal = this.aborter.signal;
    const assistantMessage: Message = {
      id: newMessageId(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      model: this.selectedModel || undefined,
      thinkingOpen: this.thinkingEnabled,
    };
    this.messages.push(assistantMessage);
    this.cdr.detectChanges();
    this.scrollToBottom();

    try {
      await this.chatService.streamMessage(
        activePrompt,
        (event) => {
          if (event.type === 'token') {
            const first = !assistantMessage.content;
            assistantMessage.content += event.text;
            if (first) {
              assistantMessage.thinkingOpen = false;
            }
          } else if (event.type === 'thought') {
            this.appendThinkingText(assistantMessage, event.text);
          } else if (event.type === 'tool_start') {
            this.appendThought(assistantMessage, `Using ${this.formatToolName(event.name)}`);
          } else if (event.type === 'tool_end') {
            this.appendThought(assistantMessage, `Finished ${this.formatToolName(event.name)}`);
          } else if (event.type === 'image') {
            assistantMessage.imageUrl = event.url;
          } else if (event.type === 'done') {
            if (event.content) {
              assistantMessage.content = event.content;
            }
            if (event.image_url) {
              assistantMessage.imageUrl = event.image_url;
            }
          } else if (event.type === 'error') {
            this.error = event.message;
            if (!assistantMessage.content) {
              assistantMessage.content = event.message;
            }
          }
          this.scheduleRender();
        },
        signal,
        this.selectedModel || undefined,
        this.thinkingEnabled,
      );
    } catch (err) {
      if (signal.aborted) {
        assistantMessage.stats = this.formatStats(
          (Date.now() - this.thinkingStartedAt) / 1000,
          assistantMessage.content.length,
        );
      } else {
        this.error = 'Sorry, something went wrong. Please check the backend connection.';
        assistantMessage.content =
          assistantMessage.content || 'Sorry, something went wrong. Please check the backend connection.';
        console.error(err);
      }
    } finally {
      this.isLoading = false;
      this.streaming = false;
      this.aborter = null;
      const elapsed = (Date.now() - this.thinkingStartedAt) / 1000;
      assistantMessage.thinkingMs = Date.now() - this.thinkingStartedAt;
      assistantMessage.thinkingOpen = false;
      if (!assistantMessage.stats) {
        assistantMessage.stats = this.formatStats(elapsed, assistantMessage.content.length);
      }
      assistantMessage.timestamp = assistantMessage.timestamp || Date.now();
      this.syncMessages();
      this.cdr.detectChanges();
      this.scrollToBottom();
      setTimeout(() => this.renderMath(), 100);
    }
  }

  downloadPlot(imageUrl: string): void {
    const fileName = imageUrl.split('/').pop() || 'weibull-plot.png';
    fetch(imageUrl)
      .then((response) => response.blob())
      .then((blob) => this.downloadBlob(blob, fileName))
      .catch((err) => console.error(err));
  }

  onDocumentSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    this.chatService.uploadDocument(file).subscribe({
      next: (result) => {
        this.knowledgeSummary = `${result.source} saved. It will be indexed on the next knowledge search.`;
        this.refreshKnowledgeStatus();
        input.value = '';
      },
      error: (err) => {
        this.knowledgeSummary = 'Could not upload that document.';
        console.error(err);
        input.value = '';
      },
    });
  }

  exportAs(format: ExportFormat['value']): void {
    this.selectedExportFormat = format;
    this.exportMenuOpen = false;
    this.exportChat();
  }

  exportChat(): void {
    const markdown = this.buildExportMarkdown();

    if (this.selectedExportFormat === 'markdown') {
      this.downloadBlob(
        new Blob([markdown], { type: 'text/markdown;charset=utf-8' }),
        'chat-export.md',
      );
      return;
    }

    void this.renderMath().then(() => {
      const html = this.buildExportHtml();

      if (this.selectedExportFormat === 'html') {
        this.downloadBlob(
          new Blob([html], { type: 'text/html;charset=utf-8' }),
          'chat-export.html',
        );
        return;
      }

      const printWindow = window.open('', '_blank', 'width=1200,height=900');
      if (!printWindow) {
        return;
      }
      printWindow.document.write(html);
      printWindow.document.close();
      printWindow.document.title = 'Reliability Copilot';
      setTimeout(() => {
        printWindow.focus();
        printWindow.print();
      }, 500);
    });
  }

  private refreshKnowledgeStatus(): void {
    this.chatService.knowledgeStatus().subscribe({
      next: (status) => {
        this.knowledgeSummary = `${status.files.length} knowledge files, ${status.chunk_count} chunks`;
      },
      error: () => {
        this.knowledgeSummary = '';
      },
    });
  }

  private renderHandle = 0;

  private scheduleRender(): void {
    if (this.renderHandle) {
      return;
    }
    this.renderHandle = requestAnimationFrame(() => {
      this.renderHandle = 0;
      this.cdr.detectChanges();
      this.scrollToBottom();
    });
  }

  private buildExportMarkdown(): string {
    const session = this.currentSession;
    const title = session ? sessionTitle(session) : 'Chat Export';
    const header = [
      `# ${title}`,
      '',
      `- Exported: ${new Date().toLocaleString()}`,
      `- Provider: ${this.providerLabel()}`,
      `- Model: ${this.selectedModel || 'unknown'}`,
      `- Messages: ${this.messages.length}`,
      '',
      '---',
      '',
    ].join('\n');
    const sections = this.messages
      .filter((message) => message.role === 'user' || message.role === 'assistant')
      .map((message) => {
        const time = message.timestamp ? new Date(message.timestamp).toLocaleString() : '';
        const label =
          message.role === 'assistant'
            ? `Assistant (${message.model || this.selectedModel || 'assistant'}) · ${time}`
            : `You · ${time}`;
        const lines = [
          `## ${label}`,
          '',
          message.content || '',
          message.stats ? `\n*${message.stats}*` : '',
          message.imageUrl ? `\n![plot](${message.imageUrl})` : '',
          '',
        ].join('\n');
        return lines;
      })
      .join('\n');
    return `${header}\n${sections.trim()}`.trim();
  }

  private buildExportHtml(): string {
    const clone = this.messageContainer?.nativeElement?.cloneNode(true) as HTMLElement | null;
    const contentHTML = clone ? clone.innerHTML : '';

    return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Reliability Copilot</title><style>
      @page{margin:0}
      body{font-family:Arial,sans-serif;line-height:1.5;padding:16mm;color:#111;background:#fff}
      h1{margin:0 0 16px;font-size:1.15rem}
      .turn{display:flex;gap:12px;margin-bottom:20px;break-inside:avoid-page}
      .turn-user .turn-body{background:#e8e8ea;border-radius:18px;padding:10px 14px}
      .turn-body{word-break:break-word;overflow-wrap:anywhere;max-width:100%}
      .chat-image{max-width:100%;border-radius:8px;margin-top:10px;border:1px solid #ddd}
      p{margin:0 0 8px}
      ul{margin:0 0 8px 20px}
      code{background:#f5f5f5;padding:2px 4px;border-radius:4px}
      pre{background:#f5f5f5;padding:12px;border-radius:6px;overflow-x:auto}
      .MathJax{font-size:1em}
      .thinking{margin:0 0 12px;width:100%}
      .thinking-toggle{display:inline-flex;align-items:center;gap:8px;border:none;background:none;padding:0;font-size:0.92rem;color:#6b6b6b}
      .thinking-icon{width:16px;height:16px;max-width:16px;max-height:16px;flex-shrink:0;display:block}
      .thinking-icon.open{transform:rotate(90deg)}
      .thinking-pulse{display:none}
      .thinking-panel{margin-top:8px;background:#f0f0f2;border-radius:8px;border-left:2px solid #d0d0d4}
      .thinking-text{margin:0;padding:10px 12px;font-size:0.88rem;white-space:pre-wrap;font-family:inherit}
      .thinking-log{margin:0;padding:10px 12px 10px 26px;font-size:0.88rem}
      @media print{body{padding:16mm}}
    </style>
      <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
      <script>window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']],displayMath:[['$$','$$'],['\\[','\\]']],macros:{sb:['_{#1}',1]}},svg:{fontCache:'global'}};</script>
    </head><body><h1>Reliability Copilot</h1>${contentHTML}</body></html>`;
  }

  private downloadBlob(blob: Blob, fileName: string): void {
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
    window.URL.revokeObjectURL(url);
  }

  private renderMath(): Promise<void> {
    return new Promise((resolve) => {
      if (typeof MathJax !== 'undefined' && MathJax.typesetPromise) {
        try {
          const target = this.messageContainer?.nativeElement;
          if (target) {
            MathJax.typesetClear?.([target]);
            MathJax.typesetPromise?.([target])
              .then(() => resolve())
              .catch((err: any) => {
                console.log('MathJax error:', err);
                resolve();
              });
            return;
          }
        } catch (err) {
          console.log('MathJax rendering:', err);
        }
      }
      setTimeout(() => resolve(), 100);
    });
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      try {
        this.messageContainer.nativeElement.scrollTop =
          this.messageContainer.nativeElement.scrollHeight;
      } catch (err) {
        console.error('Could not scroll to bottom:', err);
      }
    }, 0);
  }
}
