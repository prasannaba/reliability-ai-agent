import { useCallback, useEffect, useRef, useState } from "react";
import {
  WELCOME_MESSAGE,
  newMessageId,
  type ChatSession,
  type Message,
} from "../types/chat";
import type { Storage } from "../services/types";

const SESSIONS_KEY = "reliability-copilot-sessions";
const CURRENT_KEY = "reliability-copilot-current";

function isEmptySession(session: ChatSession): boolean {
  return !session.messages.some((m) => (m.content || "").trim());
}

function stripWelcomeMessages(sessions: ChatSession[]): ChatSession[] {
  return sessions.map((s) => ({
    ...s,
    messages: s.messages.filter((m) => m.content !== WELCOME_MESSAGE),
  }));
}

function loadInitial(storage: Storage): {
  sessions: ChatSession[];
  currentId: string | null;
  counter: number;
} {
  try {
    const raw = storage.getItem(SESSIONS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as ChatSession[];
      if (Array.isArray(parsed) && parsed.length) {
        // Migrate stored chats: the old welcome bubble was persisted as a
        // real assistant message — strip it so it no longer renders.
        const migrated = stripWelcomeMessages(parsed).slice(0, 50);
        // Always land on a fresh chat, not the previous one. Reuse the
        // newest session when it is still empty to avoid piling up an
        // extra empty chat on every reload.
        if (migrated.length && isEmptySession(migrated[0])) {
          return {
            sessions: migrated,
            currentId: migrated[0].id,
            counter: migrated.length,
          };
        }
        const session = freshSession(migrated.length + 1);
        return {
          sessions: [session, ...migrated].slice(0, 50),
          currentId: session.id,
          counter: migrated.length + 1,
        };
      }
    }
  } catch {
    // fall through to fresh session
  }
  const session = freshSession(1);
  return { sessions: [session], currentId: session.id, counter: 1 };
}

function freshSession(counter: number): ChatSession {
  return {
    id: newMessageId(),
    title: `Chat ${counter}`,
    messages: [],
    updatedAt: Date.now(),
  };
}

function persist(
  storage: Storage,
  sessions: ChatSession[],
  currentId: string | null,
): void {
  try {
    storage.setItem(SESSIONS_KEY, JSON.stringify(sessions.slice(0, 50)));
    if (currentId) {
      storage.setItem(CURRENT_KEY, currentId);
    }
  } catch {
    // storage full / unavailable — chat still works in memory
  }
}

/** Chat sessions with persistence (stable localStorage schema/keys — do not rename). */
export function useSessions(storage: Storage) {
  const [initial] = useState(() => loadInitial(storage));
  const [sessions, setSessions] = useState<ChatSession[]>(initial.sessions);
  const [currentId, setCurrentId] = useState<string | null>(initial.currentId);
  const [counter, setCounter] = useState(initial.counter);
  const currentIdRef = useRef(currentId);
  currentIdRef.current = currentId;

  const current = sessions.find((s) => s.id === currentId) ?? null;

  // Persist on every change (not inside updaters, which must stay pure).
  useEffect(() => {
    persist(storage, sessions, currentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions, currentId]);

  const commit = useCallback((next: ChatSession[], nextId: string | null) => {
    setSessions(next);
    setCurrentId(nextId);
    // Persistence is handled by the effect above.
  }, []);

  const newChat = useCallback(() => {
    const nextCounter = counter + 1;
    setCounter(nextCounter);
    const session = freshSession(nextCounter);
    const next = [session, ...sessions];
    commit(next, session.id);
    return session.id;
  }, [counter, sessions, commit]);

  const selectSession = useCallback(
    (id: string) => {
      if (sessions.some((s) => s.id === id)) {
        commit(sessions, id);
      }
    },
    [sessions, commit],
  );

  const deleteSession = useCallback(
    (id: string) => {
      const next = sessions.filter((s) => s.id !== id);
      if (currentId === id) {
        // Always create a new fresh chat when deleting the current chat
        const session = freshSession(counter + 1);
        setCounter(counter + 1);
        commit([session, ...next], session.id);
      } else {
        commit(next, currentId);
      }
    },
    [sessions, currentId, counter, commit],
  );

  /** Update messages of the current session (touch updatedAt).
   *
   * Uses a functional setSessions update so rapid successive calls (user
   * push → assistant push → per-token flushes during streaming) never lose
   * each other, even when the calling closure captured a stale render.
   */
  const setMessages = useCallback((updater: (prev: Message[]) => Message[]) => {
    setSessions((prevSessions) =>
      prevSessions.map((s) =>
        s.id === currentIdRef.current
          ? { ...s, messages: updater(s.messages), updatedAt: Date.now() }
          : s,
      ),
    );
  }, []);

  const clearChat = useCallback(() => {
    setMessages(() => []);
  }, [setMessages]);

  /** Delete every session and start over with a single fresh chat. */
  const clearAllChats = useCallback(() => {
    const session = freshSession(counter + 1);
    setCounter(counter + 1);
    commit([session], session.id);
  }, [counter, commit]);

  return {
    sessions,
    currentId,
    current,
    messages: current?.messages ?? [],
    newChat,
    selectSession,
    deleteSession,
    setMessages,
    clearChat,
    clearAllChats,
  };
}
