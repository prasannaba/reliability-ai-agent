declare global {
  interface Window {
    MathJax?: {
      typesetClear?: (elements: HTMLElement[]) => void;
      typesetPromise?: (elements: HTMLElement[]) => Promise<void>;
    };
  }
}

/** Re-render MathJax inside a container. */
export function renderMath(container: HTMLElement | null): Promise<void> {
  return new Promise((resolve) => {
    const MathJax = window.MathJax;
    if (MathJax?.typesetPromise) {
      try {
        if (container) {
          MathJax.typesetClear?.([container]);
          MathJax.typesetPromise([container])
            .then(() => resolve())
            .catch(() => resolve());
          return;
        }
      } catch {
        // fall through to delayed resolve
      }
    }
    setTimeout(() => resolve(), 100);
  });
}
