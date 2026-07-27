# import asyncio
# import os
import re
import sys
from pathlib import Path

import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# to include plot_weibull_analysis in library path
sys.path.append(str(Path(__file__).parent))

import os

from life_data_analysis_weibull import plot_weibull_analysis
from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.agent.workflow import FunctionAgent, ReActAgent
from llama_index.core.tools import FunctionTool, QueryEngineTool
from llama_index.core.workflow import Context

from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
# from llama_index.embeddings.openai_like import OpenAILikeEmbedding

from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.openai_like import OpenAILike


# Replace with your actual string if you don't want to deal with files
# "***REMOVED***" from prasannabadami2025@gmail.com

os.environ["GOOGLE_API_KEY"] = "***REMOVED***"


def calculate_b_life(beta: float, eta: float, percentage: float) -> int:
    """
    Calculates the B-Life for a given percentage.
    """
    f_t = percentage / 100.0  # F(t), cumulative PDF
    b_life = eta * (-np.log(1 - f_t)) ** (1 / beta)
    return np.round(b_life).astype(int)


def infer_latest_image_url(response_content: str, static_dir: Path | None = None, base_url: str = "http://localhost:8000") -> str | None:
    """Only return an image URL when the current response explicitly references a generated plot file."""
    if not response_content:
        return None

    if static_dir is None:
        static_dir = Path(__file__).parent / "static"

    if not static_dir.exists():
        return None

    explicit_names = re.findall(r"([A-Za-z0-9_.-]+\.png)", response_content)
    for filename in explicit_names:
        candidate = static_dir / filename
        if candidate.exists():
            stat = candidate.stat()
            return f"{base_url.rstrip('/')}/static/{candidate.name}?v={stat.st_mtime_ns}"

    # Do not attach the latest plot for unrelated responses.
    return None


def extract_response_text(response_object: object) -> str:
    """Extract the natural-language assistant response from common agent output shapes."""
    if response_object is None:
        return ""

    if isinstance(response_object, str):
        return response_object.strip()

    if hasattr(response_object, "content") and isinstance(getattr(response_object, "content"), str):
        content = getattr(response_object, "content")
        if content:
            return content.strip()

    if hasattr(response_object, "response"):
        response = getattr(response_object, "response")
        if hasattr(response, "content") and isinstance(getattr(response, "content"), str):
            content = getattr(response, "content")
            if content:
                return content.strip()
        if response is not None:
            return str(response).strip()

    if hasattr(response_object, "output"):
        output = getattr(response_object, "output")
        if hasattr(output, "content") and isinstance(getattr(output, "content"), str):
            content = getattr(output, "content")
            if content:
                return content.strip()
        if output is not None:
            return str(output).strip()

    if hasattr(response_object, "result"):
        result = getattr(response_object, "result")
        if isinstance(result, str):
            return result.strip()
        if hasattr(result, "content") and isinstance(getattr(result, "content"), str):
            return getattr(result, "content").strip()
        if result is not None:
            return str(result).strip()

    return str(response_object).strip()


def normalize_response_content(response_content: str) -> str:
    """Preserve the summary text but add a fallback explanation when only a plot file is returned."""
    if not response_content:
        return ""

    text = str(response_content).strip()
    if not text:
        return ""

    if re.fullmatch(r"(?:[A-Za-z0-9_.-]+\\.png)", text):
        return "I created the Weibull plot for the supplied failure data. The chart is attached below."

    if re.fullmatch(r"(?:[A-Za-z0-9_.-]+\\.png)\s*", text):
        return "I created the Weibull plot for the supplied failure data. The chart is attached below."

    return text


class ChatRequest(BaseModel):
    prompt: str


class ChatResponse(BaseModel):
    content: str
    image_url: str | None = None


class Agent(FastAPI):
    """Agent class that is also a FastAPI application.

    Initializes LLMs, embeddings, knowledge base, and tools in `__init__`.
    """

    def __init__(self):
        super().__init__()

        # -------------------------------------------------------------#
        #                   Angular frontend configuration
        # -------------------------------------------------------------#
        # CORS Middleware: Allows the Angular frontend to communicate with this backend
        self.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:4200"],  # Angular's default development server
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # -------------------------------------------------------------#
        #                   Mount static directory
        # -------------------------------------------------------------#
        # Set location to save the generated plot
        script_dir = Path(__file__).parent
        static_dir = script_dir / "static"
        if not static_dir.exists():
            static_dir.mkdir()
        self.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        # -------------------------------------------------------------#
        # Initialize embeddings, models, knowledge base, and tools
        # -------------------------------------------------------------#

        # -------------------------------------------------------------#
        #                   Setting Embeddings
        # -------------------------------------------------------------#
        # Settings.embed_model = OllamaEmbedding(model_name="embeddinggemma:latest")
        # Settings.embed_model = OllamaEmbedding(model_name="embeddinggemma:300m-qat-q4_0")

        # Settings.embed_model = HuggingFaceEmbedding(model_name="unsloth/bge-small-en-v1.5")
        Settings.embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

        # -------------------------------------------------------------#
        #                   Setting LLM
        # -------------------------------------------------------------#
        # Settings.llm = Ollama(model="gpt-oss:20b-cloud", request_timeout=120)
        # Settings.llm = Ollama(model="granite4:micro-h", request_timeout=120, context_window=4096)
        # Settings.llm = Ollama(
        #     model="gemma-4-E2B-QAT-UD_Q4_K_XL:pro",
        #     temperature=1,
        #     request_timeout=120,
        #     context_window=4096,
        #     keep_alive=True,
        #     thinking='low',
        #     additional_kwargs={
        #         'top_k': 64,
        #         'top_p': 0.95,
        #     }
        # )

        ## Make sure llama-server is running before this file is executed.
        Settings.llm = OpenAILike(
            model="gemma",
            # api_base="http://127.0.0.1:1234/v1",  # LM Studio
            api_base="http://localhost:8080/v1",  # llama-server
            api_key="dummy",
            is_chat_model=True,
            is_function_calling_model=True,
        )

        # -------------------------------------------------------------#
        #   Query Engine Tool: RAG, Knowledge-Base, Vectorize
        # -------------------------------------------------------------#

        knowledge_base_dir = Path(__file__).parent.parent / "Knowledge_Base"

        documents = SimpleDirectoryReader(
            input_files=[
                knowledge_base_dir / "b_life.md",
                knowledge_base_dir / "prasanna.md",
                knowledge_base_dir / "interpreting_results.md",
                knowledge_base_dir / "weibull_analysis.md",
                knowledge_base_dir / "weibull_basics.md",
            ]
        ).load_data()

        index = VectorStoreIndex.from_documents(documents)
        query_engine = index.as_query_engine(similarity_top_k=3)

        # Create Query Engine Tool to access Knowledge Base
        query_engine_tool = QueryEngineTool.from_defaults(
            query_engine=query_engine,
            name="Reliability_Knowledge_Base",
            description=(
                "Provides information about reliability engineering concepts, methods, formulas, "
                "as well as organizational knowledge, profiles, and documentation regarding team members like Prasanna."
            ),
        )

        # -------------------------------------------------------------#
        #                   Function Tools
        # -------------------------------------------------------------#
        function_tool_wa = FunctionTool.from_defaults(fn=plot_weibull_analysis)
        function_tool_blife = FunctionTool.from_defaults(fn=calculate_b_life)

        # -------------------------------------------------------------#
        #                   Create Agent
        # -------------------------------------------------------------#
        function_agent = ReActAgent(
            tools=[query_engine_tool, function_tool_wa, function_tool_blife],
            system_prompt=(
                "You are an expert in Reliability Engineering and Mathematics. "
                "You must call the appropriate tool based on the user's query. "
                "Refer to the Reliability_Knowledge_Base for any conceptual, factual, or biographical questions "
                "regarding the documentation and team."
                "When a plot is created, mention the filename of the plot in your response and also provide a brief textual summary of the analysis (for example: estimated beta, eta, goodness-of-fit, and the practical interpretation of the result)."
                "To answer warranty related queries you will make recommendation by comparing B10, B20 and B30 lives with weibull's other parameters."
                "Guidelines: "
                """- Technical Accuracy: Prioritize first-principles thinking in Physics, Engineering, Mathematics, Probability, Statistics, Calculus, and Algebra.
                - Reliability: Only if Prompt is relevant to Reliability, when discussing Electronics/Software/Firmware, focus on edge cases, safety, and memory management , etc.
                - Embedded Systems Focus: Only if prompt is relevant to Embedded Systems, assume resource-constrained environments unless specified otherwise (e.g., bare-metal C, RTOS).
                - Statistical Rigor: Use frequentist or Bayesian frameworks explicitly when discussing Probability.
                - Formatting: Use LaTeX for all mathematical expressions and standard Markdown for code."""
                "Directly address the user's intent with dense, high-information content. Avoid filler."
            ),
        )

        # -------------------------------------------------------------#
        #                   Set Agent and Context
        # -------------------------------------------------------------#
        # Save references on the instance for endpoint usage
        self.agent = function_agent
        self.ctx = Context(self.agent)

        # register endpoint on this FastAPI instance
        @self.options("/api/chat")
        async def options_chat():
            return {"status": "ok"}

        @self.post("/api/chat", response_model=ChatResponse)
        async def chat_endpoint(request: ChatRequest):
            try:
                response_object = await self.agent.run(user_msg=request.prompt, ctx=self.ctx)
                response_content = extract_response_text(response_object)
                response_content = normalize_response_content(response_content)
                image_url = infer_latest_image_url(response_content, Path(__file__).parent / "static")

                return ChatResponse(content=response_content, image_url=image_url)

            except Exception as e:
                return ChatResponse(content=f"An error occurred: {e}", image_url=None)


class GoogleGenAIAgent(FastAPI):
    """Agent class using Google GenAI models and embeddings.

    Initializes embeddings, LLM, knowledge base, and tools in `__init__`.
    """

    def __init__(self):
        super().__init__()

        # CORS Middleware: Allows the Angular frontend to communicate with this backend
        self.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:4200"],  # Angular's default development server
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Mount static directory
        script_dir = Path(__file__).parent
        static_dir = script_dir / "static"
        if not static_dir.exists():
            static_dir.mkdir()
        self.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        # initialize Google embeddings and LLM
        Settings.embed_model = GoogleGenAIEmbedding(model="embedding-001", api_key=os.environ.get("GOOGLE_API_KEY"))
        Settings.llm = GoogleGenAI(model="gemini-3-flash-preview", api_key=os.environ.get("GOOGLE_API_KEY"))

        knowledge_base_dir = Path(__file__).parent.parent / "Knowledge_Base"

        documents = SimpleDirectoryReader(
            input_files=[
                knowledge_base_dir / "b_life.md",
                knowledge_base_dir / "prasanna.md",
                knowledge_base_dir / "interpreting_results.md",
                knowledge_base_dir / "weibull_analysis.md",
                knowledge_base_dir / "weibull_basics.md",
            ]
        ).load_data()

        index = VectorStoreIndex.from_documents(documents)
        query_engine = index.as_query_engine(similarity_top_k=3)

        query_engine_tool = QueryEngineTool.from_defaults(
            query_engine=query_engine,
            name="Reliability_Knowledge_Base",
            description=(
                "Provides information about reliability engineering concepts, methods, and formulas. "
                "Use this for questions about terms and metrics."
            ),
        )

        function_tool_wa = FunctionTool.from_defaults(fn=plot_weibull_analysis)
        function_tool_blife = FunctionTool.from_defaults(fn=calculate_b_life)

        function_agent = FunctionAgent(
            tools=[query_engine_tool, function_tool_wa, function_tool_blife],
            system_prompt=(
                "You are an expert in Reliability Engineering and Mathematics. "
                "You must call the appropriate tool based on the user's query. "
                "Refer to the Reliability_Knowledge_Base for conceptual questions. "
                "When a plot is created, mention the filename of the plot in your response and also provide a brief textual summary of the analysis (for example: estimated beta, eta, goodness-of-fit, and the practical interpretation of the result)."
                "To answer warranty related queries you will make recommendation by comparing B10, B20 and B30 lives with weibull's other parameters."
            ),
        )

        self.agent = function_agent
        self.ctx = Context(self.agent)

        @self.options("/api/chat")
        async def options_chat():
            return {"status": "ok"}

        @self.post("/api/chat", response_model=ChatResponse)
        async def chat_endpoint(request: ChatRequest):
            try:
                response_object = await self.agent.run(user_msg=request.prompt, ctx=self.ctx)
                response_content = extract_response_text(response_object)
                response_content = normalize_response_content(response_content)
                image_url = infer_latest_image_url(response_content, Path(__file__).parent / "static")

                return ChatResponse(content=response_content, image_url=image_url)

            except Exception as e:
                return ChatResponse(content=f"An error occurred: {e}", image_url=None)


# instantiate the Agent (which is a FastAPI app)
app = Agent()
# app = GoogleGenAIAgent()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
