"""15-minute Reliability Copilot demo: tools first, local LLM if it is already up."""

from __future__ import annotations

import asyncio
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from knowledge_base import KNOWLEDGE_BASE_DIR, ReliabilityKnowledgeBase
from life_data_analysis_weibull import plot_weibull_analysis
from reliability_report import build_reliability_report

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

FAILURES = [150, 180, 220, 310, 400, 520, 610, 780]
SUSPENSIONS = [800, 800, 1000]
WARRANTY_HOURS = 200
DEMO_PROMPT = (
    "Fit Weibull to failures 150, 180, 220, 310, 400, 520, 610, 780 "
    "with suspensions 800, 800, 1000. Does B10 cover a 200 hour warranty? "
    "Cite our Weibull notes. Use tools for every number."
)


def _knowledge_cite() -> list[dict]:
    try:
        search = ReliabilityKnowledgeBase().search("Weibull shape parameter beta", max_results=1)
        return search.get("matches") or []
    except Exception:
        handbook = KNOWLEDGE_BASE_DIR / "weibull_analysis.md"
        if handbook.exists():
            return [{"source": "weibull_analysis.md", "content": handbook.read_text(encoding="utf-8")[:280]}]
        return []


def llm_base() -> str:
    return (os.getenv("LLM_API_BASE") or "").strip().rstrip("/")


def llm_is_reachable(timeout_seconds: float = 2.0) -> bool:
    """True when the OpenAI-compatible server from .env answers (e.g. llama.cpp)."""
    base = llm_base()
    if not base:
        return False
    urls = [f"{base}/models"]
    if base.endswith("/v1"):
        urls.append(f"{base[:-3]}/v1/models")
    header = {"Authorization": f"Bearer {os.getenv('LLM_API_KEY', 'dummy')}"}
    for url in dict.fromkeys(urls):
        try:
            request = urllib.request.Request(url, headers=header)
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                if 200 <= response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False


def run_tools_demo() -> dict:
    analysis = plot_weibull_analysis(
        FAILURES,
        title="Demo: Weibull paper (failures + suspensions)",
        censored_times=SUSPENSIONS,
        method="rry",
        confidence=0.9,
    )
    citations = _knowledge_cite()
    report = build_reliability_report(
        analysis,
        question="Does B10 cover a 200-hour warranty on this sample?",
        warranty_hours=WARRANTY_HOURS,
        knowledge_citations=citations,
    )
    report_path = Path(__file__).parent / "static" / "demo_report.md"
    report_path.write_text(report, encoding="utf-8")
    print("1) Tool path (no LLM) — this is the hiring-manager proof")
    print(f"  plot: {analysis['file']}")
    print(f"  method: {analysis['method']}  failures={analysis['n_failures']}  suspensions={analysis['n_censored']}")
    print(f"  beta={analysis['beta']:.3f}  eta={analysis['eta']:.1f} h  MTBF={analysis['mtbf']:.1f} h")
    print(f"  B10={analysis['b10']:.1f} h vs warranty {WARRANTY_HOURS:g} h")
    if citations:
        print(f"  KB: {citations[0].get('source')}")
    print(f"  report: {report_path}")
    return analysis


async def run_llm_turn() -> None:
    from llama_index.core.workflow import Context
    from main import (
        build_agent,
        extract_response_text,
        fetch_llm_models,
        normalize_response_content,
        pick_listed_model,
        preferred_llm_model,
    )
    from mcp_client import ReliabilityMCPClient

    client = ReliabilityMCPClient()
    await client.start()
    try:
        models = fetch_llm_models()
        model = pick_listed_model(models, preferred_llm_model())
        if not model:
            print(f"No models listed at {llm_base()}.")
            return
        agent = await build_agent(client, model)
        print(f"2) LLM path — {model} at {llm_base()}")
        print(f"  prompt: {DEMO_PROMPT}")
        response = await agent.run(user_msg=DEMO_PROMPT, ctx=Context(agent))
        print()
        print(normalize_response_content(extract_response_text(response)))
    finally:
        await client.close()


def main() -> None:
    from main import LLM_UNCONFIGURED

    skip_llm = "--no-llm" in sys.argv or os.getenv("DEMO_SKIP_LLM", "").strip() in {"1", "true", "yes"}
    run_tools_demo()
    print()
    if skip_llm:
        print("LLM skipped (--no-llm / DEMO_SKIP_LLM). Chat UI: uv run python main.py")
        return
    if not llm_base():
        print(LLM_UNCONFIGURED)
        print("You do not need an LLM for the numbers above. For chat: set .env then uv run python main.py")
        return
    if not llm_is_reachable():
        print(f"LLM not reachable at {llm_base()} (start llama.cpp / vLLM / Ollama).")
        print("You do not need it for the numbers above. For the chat UI: uv run python main.py")
        return
    asyncio.run(run_llm_turn())


if __name__ == "__main__":
    main()
