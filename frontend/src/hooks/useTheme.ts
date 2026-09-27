import { useCallback, useEffect, useState } from 'react';
import type { Storage } from '../services/types';

export type ThemeChoice = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'reliability-copilot-theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

function readStoredChoice(storage: Storage): ThemeChoice {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (raw === 'light' || raw === 'dark' || raw === 'system') {
      return raw;
    }
  } catch {
    // storage unavailable — fall through to system
  }
  return 'system';
}

export function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  if (choice === 'light' || choice === 'dark') {
    return choice;
  }
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
  }
  return 'light';
}

function applyTheme(resolved: ResolvedTheme): void {
  document.documentElement.dataset.theme = resolved;
  // Bootstrap 5.3+ built-in dark mode for modals, dropdowns, inputs, buttons.
  document.documentElement.dataset.bsTheme = resolved;
}

/** Theme preference: explicit light/dark, defaulting to the OS (system) theme. */
export function useTheme(storage: Storage) {
  const [choice, setChoiceState] = useState<ThemeChoice>(() => readStoredChoice(storage));
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    resolveTheme(readStoredChoice(storage)),
  );

  useEffect(() => {
    const update = () => {
      const next = resolveTheme(choice);
      setResolved(next);
      applyTheme(next);
    };
    update();
    const media = window.matchMedia(DARK_QUERY);
    const onChange = () => {
      if (choice === 'system') {
        update();
      }
    };
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, [choice]);

  const setChoice = useCallback(
    (next: ThemeChoice) => {
      setChoiceState(next);
      try {
        storage.setItem(STORAGE_KEY, next);
      } catch {
        // ignore persistence failures
      }
    },
    [storage],
  );

  return { choice, resolved, setChoice };
}
