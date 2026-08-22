export interface Message {
  role: 'user' | 'assistant';
  content: string;
  imageUrl?: string;
  thinkingText?: string;
  thinkingSteps?: string[];
  thinkingOpen?: boolean;
  thinkingMs?: number;
}
