import { Component, ViewChild, ElementRef, AfterViewInit, ChangeDetectorRef, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService } from '../../services/chat';
import { Message } from '../../models/message.model';
import { MarkdownModule } from 'ngx-markdown';

interface ExportFormat { label: string; value: 'markdown' | 'html' | 'pdf'; }

declare var MathJax: any;

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, MarkdownModule],
  templateUrl: './chat.html',
  styleUrls: ['./chat.css']
})
export class ChatComponent implements OnInit, AfterViewInit {
  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  messages: Message[] = [];
  userInput: string = '';
  isLoading: boolean = false;
  exportFormats: ExportFormat[] = [
    { label: 'Markdown', value: 'markdown' },
    { label: 'HTML', value: 'html' },
    { label: 'PDF', value: 'pdf' }
  ];
  selectedExportFormat: ExportFormat['value'] = 'markdown';

  constructor(
    private chatService: ChatService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit() {
    this.messages.push({
      role: 'assistant',
      content: 'Hello! How can I help you with your reliability analysis today?'
    });
    // Render initial math
    setTimeout(() => this.renderMath(), 100);
  }

  ngAfterViewInit() {
    this.scrollToBottom();
  }

  sendMessage() {
    if (!this.userInput.trim()) {
      return;
    }

    // Add user message to chat
    const userMessage: Message = { role: 'user', content: this.userInput };
    this.messages.push(userMessage);
    this.isLoading = true;
    const currentInput = this.userInput;
    this.userInput = ''; // Clear input immediately
    this.cdr.detectChanges();
    this.scrollToBottom();

    // Call service and handle response
    this.chatService.sendMessage(currentInput).subscribe({
      next: (response) => {
        const assistantMessage: Message = {
          role: 'assistant',
          content: response.content,
          imageUrl: response.image_url || undefined
        };
        this.messages.push(assistantMessage);
        this.isLoading = false;
        this.cdr.detectChanges();
        this.scrollToBottom();
        // Trigger MathJax rendering after content is added to DOM
        setTimeout(() => this.renderMath(), 100);
      },
      error: (err) => {
        const errorMessage: Message = {
          role: 'assistant',
          content: 'Sorry, something went wrong. Please check the backend connection.'
        };
        this.messages.push(errorMessage);
        this.isLoading = false;
        this.scrollToBottom();
        console.error(err);
      }
    });
  }

  exportChat(): void {
    const markdown = this.buildExportMarkdown();

    if (this.selectedExportFormat === 'markdown') {
      this.downloadBlob(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }), 'chat-export.md');
      return;
    }

    void this.renderMath().then(() => {
      const html = this.buildExportHtml();

      if (this.selectedExportFormat === 'html') {
        this.downloadBlob(new Blob([html], { type: 'text/html;charset=utf-8' }), 'chat-export.html');
        return;
      }

      const printWindow = window.open('', '_blank', 'width=1200,height=900');
      if (!printWindow) {
        return;
      }
      printWindow.document.write(html);
      printWindow.document.close();
      setTimeout(() => {
        printWindow.focus();
        printWindow.print();
      }, 500);
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
          ''
        ].filter(Boolean);
        return lines.join('\n');
      })
      .join('\n');

    return ['# Chat Export', '', sections.trim()].filter(Boolean).join('\n');
  }

  private buildExportHtml(): string {
    const clone = this.messageContainer?.nativeElement?.cloneNode(true) as HTMLElement | null;
    const contentHTML = clone ? clone.innerHTML : '';

    return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>
      body{font-family:Arial,sans-serif;line-height:1.5;padding:24px;color:#111;background:#fff}
      h1{margin-bottom:16px}
      .message{display:flex;max-width:100%;margin-bottom:12px}
      .message-user{justify-content:flex-end}
      .message-user .message-content{background:#007bff;color:#fff}
      .message-assistant{justify-content:flex-start}
      .message-assistant .message-content{background:#e9ecef;color:#111}
      .message-content{padding:10px 15px;border-radius:18px;word-break:break-word;overflow-wrap:anywhere;max-width:100%}
      .chat-image{max-width:100%;border-radius:8px;margin-top:10px;border:1px solid #ddd}
      p{margin:0 0 8px}
      ul{margin:0 0 8px 20px}
      code{background:#f5f5f5;padding:2px 4px;border-radius:4px}
      pre{background:#f5f5f5;padding:12px;border-radius:6px;overflow-x:auto}
      .MathJax{font-size:1em}
      @media print{body{padding:0}.message{break-inside:avoid-page}}</style>
      <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
      <script>window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']],displayMath:[['$$','$$'],['\\[','\\]']]},svg:{fontCache:'global'}};</script>
    </head><body><h1>Chat Export</h1>${contentHTML}</body></html>`;
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
    // Use a timeout to ensure the DOM has updated before scrolling
    setTimeout(() => {
      try {
        this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
      } catch (err) {
        console.error('Could not scroll to bottom:', err);
      }
    }, 0);
  }
}