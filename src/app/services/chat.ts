import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

// --- Interfaces for type safety ---
export interface ChatRequest {
  prompt: string;
}

export interface ChatResponse {
  content: string;
  image_url: string | null;
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private apiUrl = 'http://localhost:8000/api/chat';

  constructor(private http: HttpClient) { }

  sendMessage(prompt: string): Observable<ChatResponse> {
    const request: ChatRequest = { prompt };
    return this.http.post<ChatResponse>(this.apiUrl, request);
  }
}