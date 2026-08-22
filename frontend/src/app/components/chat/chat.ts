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
import { Message } from '../../models/message.model';
import { MarkdownModule } from 'ngx-markdown';
import { patchMarkdownMath } from '../../utils/math-markdown';

interface ExportFormat {
  label: string;
  value: 'markdown' | 'html' | 'pdf';
}

declare var MathJax: any;

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [FormsModule, MarkdownModule],
  templateUrl: './chat.html',
  styleUrls: ['./chat.css'],
})
export class ChatComponent implements OnInit, AfterViewInit {
  @ViewChild('messageContainer') private messageContainer!: ElementRef;
  @ViewChild('promptBox') private promptBox?: ElementRef<HTMLTextAreaElement>;

  messages: Message[] = [];
  userInput: string = '';
  isLoading = false;
  knowledgeSummary: string = '';
  exportFormats: ExportFormat[] = [
    { label: 'Markdown', value: 'markdown' },
    { label: 'HTML', value: 'html' },
    { label: 'PDF', value: 'pdf' },
  ];
  selectedExportFormat: ExportFormat['value'] = 'markdown';
  models: string[] = [];
  selectedModel = '';
  modelsHint = '';
  thinkingEnabled = true;
  private thinkingStartedAt = 0;

  constructor(
    private chatService: ChatService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit() {
    this.messages.push({
      role: 'assistant',
      content:
        'Reliability Copilot — ask a life-data or handbook question. Numbers come from tools, not guesses. Attach a procedure on the prompt if you want it in the knowledge base.',
    });
    this.loadThinkingPref();
    this.refreshKnowledgeStatus();
    this.refreshModels();
    setTimeout(() => this.renderMath(), 100);
  }

  ngAfterViewInit() {
    this.scrollToBottom();
  }

  get canSend(): boolean {
    return !!this.userInput.trim() && !this.isLoading && !!this.selectedModel;
  }

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

  shortModelName(id: string): string {
    const slash = id.replace(/\\/g, '/').split('/').pop() || id;
    return slash.length > 48 ? `${slash.slice(0, 45)}…` : slash;
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

    const userMessage: Message = { role: 'user', content: this.userInput };
    this.messages.push(userMessage);
    this.isLoading = true;
    this.thinkingStartedAt = Date.now();
    const currentInput = this.userInput;
    this.userInput = '';
    this.resizePrompt();
    const assistantMessage: Message = {
      role: 'assistant',
      content: '',
      thinkingOpen: this.thinkingEnabled,
    };
    this.messages.push(assistantMessage);
    this.cdr.detectChanges();
    this.scrollToBottom();

    try {
      await this.chatService.streamMessage(
        currentInput,
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
            assistantMessage.content = event.message;
          }
          this.scheduleRender();
        },
        undefined,
        this.selectedModel || undefined,
        this.thinkingEnabled,
      );
    } catch (err) {
      assistantMessage.content =
        'Sorry, something went wrong. Please check the backend connection.';
      console.error(err);
    } finally {
      this.isLoading = false;
      assistantMessage.thinkingMs = Date.now() - this.thinkingStartedAt;
      assistantMessage.thinkingOpen = false;
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

  private refreshModels(): void {
    this.chatService.listModels().subscribe({
      next: (result) => {
        this.models = result.models || [];
        this.selectedModel = result.current || this.models[0] || '';
        this.modelsHint = result.error || '';
      },
      error: () => {
        this.models = [];
        this.selectedModel = '';
        this.modelsHint =
          'Could not load models. Set LLM_API_BASE in the repo-root .env (see .env.example).';
      },
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
    const sections = this.messages
      .filter((message) => message.role === 'user' || message.role === 'assistant')
      .map((message) => {
        const label = message.role === 'assistant' ? 'Assistant' : 'User';
        const lines = [
          `## ${label}`,
          message.content || '',
          message.imageUrl ? `![plot](${message.imageUrl})` : '',
          '',
        ].filter(Boolean);
        return lines.join('\n');
      })
      .join('\n');

    return ['# Chat Export', '', sections.trim()].filter(Boolean).join('\n');
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
