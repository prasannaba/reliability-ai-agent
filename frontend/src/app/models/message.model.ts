export interface Message {
  role: 'user' | 'assistant';
  content: string;
  imageUrl?: string;
}
