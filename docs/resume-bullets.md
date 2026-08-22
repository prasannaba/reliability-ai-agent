# Resume bullets (Reliability Copilot)

Copy and adapt. Do not claim ReliaSoft replacement.

**Domain (lead with this on a reliability hiring screen):**

- Embedded systems / software / firmware reliability engineer: **safety-critical automotive V&V** (airbags, occupant classification / OCM, vehicle stability control, ABS) and **oil & gas design for reliability**.
- Built the analysis loop hiring managers actually live in: life data → defensible Weibull paper → B-life vs warranty, with numbers from tools not from the LLM.

**Product / this repo:**

- Built a **local Reliability Copilot** (Python MCP + FastAPI + Angular): company documents stay on disk; OpenAI-compatible local or cloud LLM is configurable.
- Implemented **Weibull probability paper** in Python (Bernard/Herd-Johnson ranks, η at 63.2%, β reference construction), with **right-censored suspensions**, RRY (default) or MLE, and **bootstrap percentile bounds** on B-life.
- Exposed analysis as **MCP tools** so β, η, MTBF, and B10/B20/B30 are **computed, never invented** by the language model; optional one-page design-review report.
- Private hybrid RAG (Chroma + BM25, incremental embed) over reliability handbooks and team procedures.
- Positioned as a **complement** to commercial life-data software (ReliaSoft / nCode), with MCP as the later integration path.

**Talk track (15 min):** `uv run python demo_copilot.py` → open the PNG → B10 vs 200 h warranty → one KB citation. Then architecture: tools vs LLM, local RAG, why paper not lin-lin scatter.

---

## Where it goes on the resume

Put it as a **project**, not as your job title. Title stays reliability / firmware / V&V. One line in the summary, 3–4 bullets under a project named **Reliability Copilot (local agent)**. Unpublished is fine: “available on request” or private GitHub.

**Summary line (use this on both reliability and AI emails):**

Reliability engineer (automotive safety-critical V&V; oil & gas DfR) building private LLM agents with tool-enforced calculations — Weibull paper, B-life, MCP, on-disk RAG.

**Project block (paste):**

Reliability Copilot — local OpenAI-compatible LLM + MCP tools (Python, FastAPI). Life data → Weibull probability paper (ranks, suspensions, B10/B20 with bounds); β/η/MTBF computed by tools, not the model. Hybrid RAG over team procedures. Demo: B10 vs warranty without inventing numbers.

Optional one-liner for other apps: Local LLM tools (CV ranking, terminal) — same privacy pattern, not the headline.

## Those “AI hiring / AI manager” emails

Most are volume: service delivery, “GenAI lead” with no domain, or a manager seat that is Jira + vendors, not engineering. Reply only if the mail names **industry, product, or reliability/embedded/safety**. Then send the summary line + offer a 15-minute plot demo.

Skip or one-line decline: generic AI manager, “build a chatbot for any client,” crypto, or roles that want people-management of a 20-person AI factory with no technical bar.

If they ask “are you an AI manager?”: you are a **reliability engineer who ships a private copilot**. That is closer to staff/principal IC or “AI for engineering” than to AI people-manager — unless you actually want to manage. Do not retitle yourself AI Manager on the resume to catch those emails; you will get the wrong interviews.
