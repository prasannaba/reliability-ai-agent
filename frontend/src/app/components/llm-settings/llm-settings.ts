import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChatService } from '../../services/chat';
import { IconComponent } from '../icon/icon';
import {
  LLM_PROVIDERS,
  PROVIDER_DEFAULTS,
  type LlmConfig,
  type LlmProvider,
} from '../../models/llm-config.model';

@Component({
  selector: 'app-llm-settings',
  imports: [FormsModule, IconComponent],
  templateUrl: './llm-settings.html',
  styleUrls: ['./llm-settings.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LlmSettingsComponent {
  private readonly chatService = inject(ChatService);

  readonly providers = LLM_PROVIDERS;
  readonly close = signal<(saved: boolean) => void>(() => undefined);

  provider: LlmProvider = 'custom';
  baseUrl = '';
  apiKey = '';
  model = '';
  temperature = 0.7;
  systemPrompt = '';
  availableModels: string[] = [];
  modelsStatus: 'idle' | 'loading' | 'success' | 'error' = 'idle';
  modelsMessage = 'Models load automatically from the base URL';
  testing = false;
  testOk: boolean | null = null;
  testMessage = '';
  validationError = '';

  open(config: LlmConfig, onClose: (saved: boolean) => void): void {
    this.close.set(onClose);
    this.provider = (config.provider as LlmProvider) || 'custom';
    this.baseUrl = config.baseUrl || PROVIDER_DEFAULTS[this.provider]?.baseUrl || '';
    this.model = config.model || '';
    this.temperature = config.temperature ?? 0.7;
    this.systemPrompt = config.systemPrompt || '';
    this.apiKey = '';
    this.testOk = null;
    this.testMessage = '';
    this.validationError = '';
    void this.loadModels();
  }

  providerHelp(): string {
    return PROVIDER_DEFAULTS[this.provider]?.help || '';
  }

  needsApiKey(): boolean {
    return PROVIDER_DEFAULTS[this.provider]?.needsApiKey ?? false;
  }

  onProviderChange(provider: LlmProvider): void {
    this.provider = provider;
    this.baseUrl = PROVIDER_DEFAULTS[provider]?.baseUrl || '';
    this.model = '';
    this.availableModels = [];
    this.testOk = null;
    this.testMessage = '';
    void this.loadModels();
  }

  resetUrl(): void {
    this.baseUrl = PROVIDER_DEFAULTS[this.provider]?.baseUrl || '';
    void this.loadModels();
  }

  loadModels(): Promise<void> {
    if (!this.baseUrl) {
      this.modelsStatus = 'idle';
      this.modelsMessage = 'Enter a base URL to load models';
      this.availableModels = [];
      return Promise.resolve();
    }
    if (this.provider === 'openai' && !this.apiKey) {
      this.modelsStatus = 'idle';
      this.modelsMessage = 'Enter your API key to load models';
      this.availableModels = [];
      return Promise.resolve();
    }
    this.modelsStatus = 'loading';
    this.modelsMessage = 'Loading models…';
    return new Promise((resolve) => {
      this.chatService
        .testLlmConfig({ provider: this.provider, baseUrl: this.baseUrl, apiKey: this.apiKey || undefined })
        .subscribe({
          next: (result) => {
            this.availableModels = result.models || [];
            if (!this.availableModels.length) {
              this.modelsStatus = 'error';
              this.modelsMessage = result.ok
                ? 'Connected, but no models listed — type the model id manually below.'
                : result.message || 'No models found — is the server running?';
            } else {
              this.modelsStatus = 'success';
              const n = this.availableModels.length;
              this.modelsMessage = `Found ${n} model${n === 1 ? '' : 's'}`;
              if (!this.model || !this.availableModels.includes(this.model)) {
                this.model = this.availableModels[0];
              }
            }
            resolve();
          },
          error: (err) => {
            this.availableModels = [];
            this.modelsStatus = 'error';
            this.modelsMessage = err?.error?.detail || err?.message || 'Failed to load models';
            resolve();
          },
        });
    });
  }

  testConnection(): void {
    if (!this.baseUrl) {
      this.testOk = false;
      this.testMessage = 'Please enter a base URL first';
      return;
    }
    if (this.provider === 'openai' && !this.apiKey) {
      this.testOk = false;
      this.testMessage = 'API key is required for OpenAI';
      return;
    }
    this.testing = true;
    this.testOk = null;
    this.testMessage = 'Testing connection…';
    this.chatService
      .testLlmConfig({ provider: this.provider, baseUrl: this.baseUrl, apiKey: this.apiKey || undefined })
      .subscribe({
        next: (result) => {
          this.testing = false;
          this.testOk = result.ok;
          this.testMessage = result.ok ? 'Connection successful!' : result.message;
          if (result.ok && result.models?.length) {
            this.availableModels = result.models;
            this.modelsStatus = 'success';
            this.modelsMessage = `Found ${result.models.length} model${result.models.length === 1 ? '' : 's'}`;
            if (!this.model || !this.availableModels.includes(this.model)) {
              this.model = this.availableModels[0];
            }
          }
        },
        error: (err) => {
          this.testing = false;
          this.testOk = false;
          this.testMessage = err?.error?.detail || err?.message || 'Connection failed';
        },
      });
  }

  save(): void {
    if (!this.baseUrl) {
      this.validationError = 'Base URL is required';
      return;
    }
    if (this.provider === 'openai' && !this.apiKey) {
      this.validationError = 'API key is required for OpenAI';
      return;
    }
    this.validationError = '';
    this.chatService
      .saveLlmConfig({
        provider: this.provider,
        baseUrl: this.baseUrl,
        apiKey: this.apiKey || undefined,
        model: this.model || undefined,
        temperature: this.temperature,
        systemPrompt: this.systemPrompt,
      })
      .subscribe({
        next: () => this.close()(true),
        error: (err) => {
          this.validationError = err?.error?.detail || err?.message || 'Could not save settings';
        },
      });
  }

  cancel(): void {
    this.close()(false);
  }
}
