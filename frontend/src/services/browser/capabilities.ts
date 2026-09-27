/** Web APIs (browser): storage, clipboard, download, print. No native plugins. */
import type { PlatformService, Storage } from '../types';

/** localStorage with in-memory fallback (private-mode / unavailable storage). */
export function localStorageBacked(): Storage {
  const memory = new Map<string, string>();
  const probe = (() => {
    try {
      return typeof localStorage !== 'undefined';
    } catch {
      return false;
    }
  })();
  return {
    getItem: (key: string) => {
      if (probe) {
        try {
          return localStorage.getItem(key);
        } catch {
          // fall through to memory
        }
      }
      return memory.has(key) ? (memory.get(key) as string) : null;
    },
    setItem: (key: string, value: string) => {
      if (probe) {
        try {
          localStorage.setItem(key, value);
          return;
        } catch {
          // fall through to memory
        }
      }
      memory.set(key, value);
    },
    removeItem: (key: string) => {
      if (probe) {
        try {
          localStorage.removeItem(key);
        } catch {
          // ignore
        }
      }
      memory.delete(key);
    },
  };
}

async function anchorDownloadBlob(blob: Blob, fileName: string): Promise<void> {
  const url = window.URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
  } finally {
    window.URL.revokeObjectURL(url);
  }
}

export async function copyTextWithFallback(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // fall through to legacy path
    }
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
  } finally {
    document.body.removeChild(ta);
  }
}

export { anchorDownloadBlob };

export function createBrowserCapabilities(): PlatformService {
  return {
    kind: 'browser',
    storage: localStorageBacked(),
    copyText: (text: string) => copyTextWithFallback(text),
    downloadBlob: (blob: Blob, fileName: string) => anchorDownloadBlob(blob, fileName),
    printHtml: async (title: string, html: string) => {
      const printWindow = window.open('', '_blank', 'width=1200,height=900');
      if (!printWindow) {
        // Popups blocked — fall back to downloading the document.
        await anchorDownloadBlob(new Blob([html], { type: 'text/html;charset=utf-8' }), `${title}.html`);
        return;
      }
      printWindow.document.write(html);
      printWindow.document.close();
      printWindow.document.title = title;
      setTimeout(() => {
        printWindow.focus();
        printWindow.print();
      }, 500);
    },
  };
}
