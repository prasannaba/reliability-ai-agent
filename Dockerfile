# Reliability Copilot — one image, three roles (selected by command in compose):
#   default CMD      FastAPI host serving API + UI on :8000
#   mcp-reliability  standalone reliability MCP over streamable HTTP on :8001
#   mcp-physics      standalone physics MCP over streamable HTTP on :8002
# Stage 1 builds the React UI; stage 2 runs the Python backend and serves it.
FROM node:20-slim AS ui
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
# Torch backend for the image (default CPU: embeddings never need CUDA).
# Local `uv sync` runs are unaffected and keep GPU torch where available.
#   cpu (default)  slim image; overridden per build with --build-arg.
#   cu130          GPU image for CUDA hosts (see docker-compose.cuda.yml).
ARG TORCH_BACKEND=cpu
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_TORCH_BACKEND=${TORCH_BACKEND} \
    DOCKER_CONTAINER=true \
    HF_HOME=/app/hf-cache
RUN pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
# uv's download cache is a BuildKit cache mount (not an image layer), so a
# re-sync after a lockfile change reuses cached wheels instead of
# re-downloading torch/sentence-transformers/etc. from scratch.
# --no-dev keeps pytest out of the image; the optional cloud group stays for
# Azure Key Vault secret backends.
#
# Torch GPU stack (torch, torchvision, triton, cuda-*, nvidia-*) is excluded
# from the lockfile sync and installed explicitly on the next line: `uv sync`
# alone does not remap the locked PyPI torch to UV_TORCH_BACKEND on Linux,
# while `uv pip install` does on every platform. TORCH_PIN must match
# backend/uv.lock (torchvision pins torch exactly, so drift fails loudly).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group cloud \
      --no-install-package torch --no-install-package torchvision \
      --no-install-package triton \
      --no-install-package cuda-bindings --no-install-package cuda-pathfinder \
      --no-install-package cuda-toolkit \
      --no-install-package nvidia-cublas --no-install-package nvidia-cuda-cupti \
      --no-install-package nvidia-cuda-nvrtc --no-install-package nvidia-cuda-runtime \
      --no-install-package nvidia-cudnn-cu13 --no-install-package nvidia-cufft \
      --no-install-package nvidia-cufile --no-install-package nvidia-curand \
      --no-install-package nvidia-cusolver --no-install-package nvidia-cusparse \
      --no-install-package nvidia-cusparselt-cu13 --no-install-package nvidia-nccl-cu13 \
      --no-install-package nvidia-nvjitlink --no-install-package nvidia-nvshmem-cu13 \
      --no-install-package nvidia-nvtx \
    && uv pip install --python .venv/bin/python "torch==2.14.0" "torchvision==0.29.0"
# Run as non-root: previous root-only image meant any RCE (e.g. via a
# malicious knowledge-base document parsed by Docling) was root-RCE.
# Writable dirs (volumes + secret/rag state) are owned by appuser; if you
# bind-mount host dirs, chown them to UID 10000 first.
RUN useradd --uid 10000 --create-home appuser \
    && mkdir -p /app/knowledge-base /app/knowledge-base-physics /app/backend/.rag /app/backend/.rag-physics /app/backend/static
# --chown here (instead of a later chown -R) avoids duplicating the whole
# venv into a second ~6GB layer.
COPY --chown=10000:10000 backend/ ./
# Production UI bundle served by FastAPI at / (covers backend/static/ui).
COPY --chown=10000:10000 --from=ui /src/frontend/dist/frontend/browser/ ./static/ui/
# Pre-download the embedding model so first search works offline at runtime
# (runtime keeps EMBEDDING_LOCAL_FILES_ONLY=true, the repo default).
# Runs as root; the model cache is re-owned below so the app user can read it
# (sentence-transformers may also write lock files there at runtime).
RUN mkdir -p /app/knowledge-base /app/hf-cache \
    && EMBEDDING_LOCAL_FILES_ONLY=false uv run --no-sync python -c \
    "from src.knowledge.base import ReliabilityKnowledgeBase; ReliabilityKnowledgeBase().embedder" \
    && chown -R 10000:10000 /app/hf-cache /app/knowledge-base /app/knowledge-base-physics /app/backend/.rag /app/backend/.rag-physics /app/backend/static
USER 10000:10000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"
CMD ["uv", "run", "--no-sync", "python", "-m", "src.host.app"]
