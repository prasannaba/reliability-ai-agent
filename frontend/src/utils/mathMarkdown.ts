/** Repair LLM TeX so Markdown and MathJax can render it. */

function balanceBraces(tex: string): string {
  let depth = 0;
  let missingOpen = 0;
  for (let index = 0; index < tex.length; index += 1) {
    const char = tex[index];
    if (char === "\\" && index + 1 < tex.length) {
      index += 1;
      continue;
    }
    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      if (depth === 0) {
        missingOpen += 1;
      } else {
        depth -= 1;
      }
    }
  }
  return "{".repeat(missingOpen) + tex + "}".repeat(depth);
}

function normalizeSb(text: string): string {
  return text
    .replace(/\\sb\s*\{([^{}]*)\}/g, "\\sb{$1}")
    .replace(/\\sb\s*([A-Za-z0-9]+)/g, "\\sb{$1}");
}

function protectSubscripts(tex: string): string {
  let cleaned = normalizeSb(tex);
  cleaned = cleaned.replace(/(?<!\\)_\{([^{}]+)\}/g, "\\sb{$1}");
  cleaned = cleaned.replace(/(?<!\\)_(\d+)/g, "\\sb{$1}");
  cleaned = cleaned.replace(/(?<!\\)_([A-Za-z])/g, "\\sb{$1}");
  return cleaned;
}

function repairTex(tex: string): string {
  let cleaned = tex.trim();
  if (!cleaned) {
    return "";
  }
  cleaned = cleaned.replace(/(?<!\\)%/g, "\\%");
  cleaned = balanceBraces(cleaned);
  cleaned = protectSubscripts(cleaned);
  return cleaned.trim();
}

function replaceAll(
  source: string,
  pattern: RegExp,
  wrap: "$$" | "[]" | "()" | "$",
): string {
  return source.replace(pattern, (_match, inner: string) => {
    const repaired = repairTex(inner);
    if (!repaired) {
      return "";
    }
    if (wrap === "$$" || wrap === "[]") {
      return `$$${repaired}$$`;
    }
    if (wrap === "()") {
      return `\\(${repaired}\\)`;
    }
    return `$${repaired}$`;
  });
}

export function patchMarkdownMath(text: string): string {
  if (!text) {
    return text;
  }
  let patched = replaceAll(text, /\$\$(.+?)\$\$/gs, "$$");
  patched = replaceAll(patched, /\\\[(.+?)\\\]/gs, "[]");
  patched = replaceAll(patched, /\\\((.+?)\\\)/gs, "()");
  patched = replaceAll(patched, /(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)/gs, "$");
  patched = patched.replace(/(?<=[A-Za-z])\s*\(\s*\)\s*:/g, ":");
  patched = normalizeSb(patched);
  patched = patched.replace(
    /(?<!\$)\b([A-Za-z])\(\$([^$]+)\$\)/g,
    "$$$1($2)$$",
  );
  return patched;
}
