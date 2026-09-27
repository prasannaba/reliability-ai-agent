import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.common.markdown_math import patch_markdown_math, repair_tex


def test_escapes_percent_inside_math():
    patched = patch_markdown_math(r"A 95% confidence level ($\text{95% CI}$):")
    assert r"\%" in patched
    assert r"\text{95\% CI}" in patched


def test_balances_extra_open_braces():
    assert repair_tex(r"\text{shape {") == r"\text{shape {}}"


def test_drops_empty_math_and_empty_parens():
    patched = patch_markdown_math("confidence level ($  $): next")
    assert "():" not in patched
    assert "confidence level:" in patched


def test_protects_subscripts_from_markdown():
    patched = patch_markdown_math(r"Use $t_{n-1}$ for the interval.")
    assert r"t\sb{n-1}" in patched


def test_b10_uses_sb_macro_not_raw_underscore():
    patched = patch_markdown_math(r"the B10 life (B\sb10) is $B_10$")
    assert r"B\sb{10}" in patched
    assert r"\sb10" not in patched
    assert "$B_{10}$" not in patched


def test_does_not_wrap_function_argument_in_extra_dollars():
    assert "F($B$)" not in patch_markdown_math(r"$F(B)$")
    assert (
        patch_markdown_math("reliability F($B$) of the fleet") == "reliability $F(B)$ of the fleet"
    )


def test_display_math_keeps_b10_and_uses_dollars():
    raw = r"\[P(T \le B_{10}) = 0.10 \Longrightarrow B_{10} = \eta \bigl(\ln 10\bigr)^{1/\beta}.\]"
    patched = patch_markdown_math(raw)
    assert r"P(T \le )" not in patched
    assert r"B\sb{10}" in patched
    assert patched.strip().startswith("$$")
    assert "[" not in patched.split("$$")[1][:2]
