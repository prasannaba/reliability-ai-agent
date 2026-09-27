"""Repair LLM TeX so Markdown and MathJax can render it."""

from __future__ import annotations

import re

DISPLAY_DOLLAR = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
DISPLAY_BRACKET = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
INLINE_PAREN = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
INLINE_DOLLAR = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", re.DOTALL)
EMPTY_PARENS = re.compile(r"(?<=[A-Za-z])\s*\(\s*\)\s*:")


def _skip_escaped(text: str, index: int) -> bool:
    return index > 0 and text[index - 1] == "\\"


def _balance_braces(tex: str) -> str:
    depth = 0
    missing_open = 0
    index = 0
    while index < len(tex):
        char = tex[index]
        if char == "\\" and index + 1 < len(tex):
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            if depth == 0:
                missing_open += 1
            else:
                depth -= 1
        index += 1
    return ("{" * missing_open) + tex + ("}" * depth)


def _escape_percent(tex: str) -> str:
    """Bare % starts a TeX comment and commonly swallows closing braces."""
    return re.sub(r"(?<!\\)%", r"\\%", tex)


def _normalize_sb(text: str) -> str:
    text = re.sub(r"\\sb\s*\{([^{}]*)\}", r"\\sb{\1}", text)
    return re.sub(r"\\sb\s*([A-Za-z0-9]+)", r"\\sb{\1}", text)


def _protect_markdown_subscripts(tex: str) -> str:
    """Use \\sb{...} so Markdown cannot eat `_` before MathJax runs."""
    tex = _normalize_sb(tex)
    tex = re.sub(r"(?<!\\)_\{([^{}]+)\}", r"\\sb{\1}", tex)
    tex = re.sub(r"(?<!\\)_(\d+)", r"\\sb{\1}", tex)
    tex = re.sub(r"(?<!\\)_([A-Za-z])", r"\\sb{\1}", tex)
    return tex


def repair_tex(tex: str) -> str:
    cleaned = tex.strip()
    if not cleaned:
        return ""
    cleaned = _escape_percent(cleaned)
    cleaned = _balance_braces(cleaned)
    cleaned = _protect_markdown_subscripts(cleaned)
    return cleaned.strip()


def _replace_math(match: re.Match[str], wrap: str) -> str:
    inner = repair_tex(match.group(1))
    if not inner:
        return ""
    if wrap == "$$":
        return f"$${inner}$$"
    if wrap == "[]":
        return f"$${inner}$$"
    if wrap == "()":
        return f"\\({inner}\\)"
    return f"${inner}$"


def patch_markdown_math(text: str) -> str:
    """Fix common LLM math mistakes without changing surrounding Markdown."""
    if not text:
        return text

    patched = DISPLAY_DOLLAR.sub(lambda match: _replace_math(match, "$$"), text)
    patched = DISPLAY_BRACKET.sub(lambda match: _replace_math(match, "[]"), patched)
    patched = INLINE_PAREN.sub(lambda match: _replace_math(match, "()"), patched)
    patched = INLINE_DOLLAR.sub(lambda match: _replace_math(match, "$"), patched)
    patched = EMPTY_PARENS.sub(":", patched)
    patched = _normalize_sb(patched)
    patched = re.sub(r"(?<!\$)\b([A-Za-z])\(\$([^$]+)\$\)", r"$\1(\2)$", patched)
    return patched
