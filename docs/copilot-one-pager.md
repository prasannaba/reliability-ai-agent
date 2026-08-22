# Reliability Copilot (one-pager)

**Positioning:** A **private reliability copilot** for engineering organizations: natural-language questions in, **defensible Weibull paper + B-life** out, company documents in the loop. ReliaSoft Weibull++, nCode, and Minitab remain the deep solvers. They are **future MCP backends and possible partners**, not competitors to displace.

## Problem

Reliability groups already own Weibull++ and large stores of PDFs and life data. The daily loop is still slow: 40 clicks for a paper plot, then a hunt through procedures to answer “does B10 cover the warranty?” ChatGPT cannot sit on that IP. Spreadsheets do not look like probability paper.

## What this is

- Local or VPC agent (your LLM, your files).
- **Weibull probability paper** (median ranks, η at 63.2%, β construction), not a default scatter.
- MCP tools **compute** β, η, MTBF, B-lives, and optional **bootstrap bounds**. The model must not invent numbers.
- Right-censored **suspensions** on the same plot.
- Knowledge search over the team’s handbook and procedures.
- One-page markdown report for a design review.

## What this is not

- Feature parity with ReliaSoft (no ALT, Weibayes, competing risks in this slice).
- A public chatbot or a license you buy from a landing page.

## Demo

`cd backend && uv sync --all-groups && uv run python demo_copilot.py`

Then chat: mixed failures + suspensions, B10 vs warranty, cite local Weibull notes.

## Expansion if funded

MCP adapters to the solvers and databases you already paid for. Same copilot layer; deeper math stays in those products—or they acquire the layer.

## Contact

Treat this repository as a **pilot seed**, not a storefront.
