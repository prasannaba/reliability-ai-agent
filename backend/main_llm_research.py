# import asyncio
# import os
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
from llama_index.embeddings.openai_like import OpenAILikeEmbedding

from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.llama_cpp import LlamaCPP
from llama_index.llms.openai_like import OpenAILike

from openai import OpenAI

# from llama_index.llms.lmstudio import LMStudio
# from llama_index.core.agent import ReActAgent 


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
            allow_origins=[
                "http://localhost:4200"
            ],  # Angular's default development server
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

        Settings.embed_model = HuggingFaceEmbedding(
            # model_name="BAAI/bge-small-en-v1.5",
            # model_name="google/embeddinggemma-300m",
            model_name = "sentence-transformers/all-MiniLM-L6-v2",
        )

        # Settings.embed_model = OpenAILikeEmbedding(
        #     model_name="gemma-4-E2B-it-qat-UD-Q4_K_XL",
        #     api_base="http://localhost:8012/v1",
        #     api_key="dummy",            
        # )

        # -------------------------------------------------------------#
        #                   Setting LLM
        # -------------------------------------------------------------#
        # Settings.llm = Ollama(model="gemma4:31b-cloud", request_timeout=120)
        # Settings.llm = Ollama(model="gpt-oss:20b-cloud", request_timeout=120)
        # Settings.llm = Ollama(
        #     model="granite4:micro-h", request_timeout=120, context_window=10000
        # )

        # model_path = Path.home() / ".lmstudio/models/lmstudio-community/gemma-4-E2B-it-qat-UD-Q4_K_XL/gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf"
        # Settings.llm = LlamaCPP(
        #     model_path=str(model_path),
        #     temperature=1.0,
        #     context_window=131072,
        #     max_new_tokens=4096,
        #     model_kwargs={
        #         "n_ctx": 131072,
        #         "n_gpu_layers": 99,
        #         "verbose": False,
        #     },
        #     generate_kwargs={
        #         "top_p": 0.95,
        #         "top_k": 64,
        #     },

        # )
        
        ## Make sure llama-server is running before this code is executed.
        Settings.llm = OpenAILike(
            model="gemma",
            api_base="http://localhost:8080/v1",
            api_key="dummy",
            is_chat_model=True,
            is_function_calling_model=True
        )
        
        # Settings.llm = LMStudio(
        #     model_name="google/gemma-4-e2b",
        #     is_chat_model=True,
        #     additional_kwargs={
        #         "is_function_calling_model": True,
        #     }
        # )

        # unsloth_key = "sk-unsloth-05cdc30d28782a190303c5681916eb08"
        # Settings.llm = OpenAILike(
        #     model="gemma4",
        #     api_base="http://127.0.0.1:8888/v1",
        #     api_key= unsloth_key,
        #     is_chat_model=True,
        #     is_function_calling_model=True,
        #     system_prompt="You are a helpful assistant. Provide direct answers without showing your thinking process or reasoning steps."
        # )  

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
                "When a plot is created, mention the filename of the plot in your response."
                "To answer warranty related queries you will make recommendation by comparing B10, B20 and B30 lives with weibull's other parameters."
            ),
        )

        # -------------------------------------------------------------#
        #                   Set Agent and Context
        # -------------------------------------------------------------#
        # Save references on the instance for endpoint usage
        self.agent = function_agent
        self.ctx = Context(self.agent)

        # register endpoint on this FastAPI instance
        @self.post("/api/chat", response_model=ChatResponse)
        async def chat_endpoint(request: ChatRequest):
            try:
                response_object = await self.agent.run(
                    user_msg=request.prompt, ctx=self.ctx
                )

                if hasattr(response_object, "output") and hasattr(
                    response_object.output, "content"
                ):
                    response_content = response_object.output.content
                else:
                    response_content = str(response_object)

                image_url = None
                if "weibull_plot.png" in response_content:
                    image_url = "http://localhost:8000/static/weibull_plot.png"

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
            allow_origins=[
                "http://localhost:4200"
            ],  # Angular's default development server
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
        Settings.embed_model = GoogleGenAIEmbedding(
            model="embedding-001", api_key=os.environ.get("GOOGLE_API_KEY")
        )
        Settings.llm = GoogleGenAI(
            model="gemini-3-flash-preview", api_key=os.environ.get("GOOGLE_API_KEY")
        )

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
                "When a plot is created, mention the filename of the plot in your response."
                "To answer warranty related queries you will make recommendation by comparing B10, B20 and B30 lives with weibull's other parameters."
            ),
        )

        self.agent = function_agent
        self.ctx = Context(self.agent)

        @self.post("/api/chat", response_model=ChatResponse)
        async def chat_endpoint(request: ChatRequest):
            try:
                response_object = await self.agent.run(
                    user_msg=request.prompt, ctx=self.ctx
                )

                if hasattr(response_object, "output") and hasattr(
                    response_object.output, "content"
                ):
                    response_content = response_object.output.content
                else:
                    response_content = str(response_object)

                image_url = None
                if "weibull_plot.png" in response_content:
                    image_url = "http://localhost:8000/static/weibull_plot.png"

                return ChatResponse(content=response_content, image_url=image_url)

            except Exception as e:
                return ChatResponse(content=f"An error occurred: {e}", image_url=None)


# instantiate the Agent (which is a FastAPI app)
app = Agent()
# app = GoogleGenAIAgent()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
