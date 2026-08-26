# ==============================================================================
# vLLM Serv: Ubuntu 24.04 + Python 3.12 GPU Accelerated Container
# ==============================================================================
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/.venv/lib/python3.12/site-packages \
    LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers:/usr/local/lib:/usr/lib/x86_64-linux-gnu \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install minimal OS dependencies, Python 3.12, curl, and procps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    curl \
    ca-certificates \
    pciutils \
    procps \
    libgomp1 \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install uv for high-speed package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files and pre-compiled wheels
COPY pyproject.toml requirements.txt uv.lock* ./
COPY wheels/ ./wheels/

# Install pre-compiled wheels and all runtime packages in /app/.venv
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv ./wheels/legacy_i7_930/*.whl && \
    uv pip install --python /app/.venv nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 fastapi uvicorn sse-starlette pydantic httpx jinja2 numpy python-dotenv requests pytest huggingface-hub pynvml redis && \
    find /app/.venv -name "libcudart*.so*" -exec cp -vL {} /usr/lib/x86_64-linux-gnu/ \; 2>/dev/null || true && \
    find /app/.venv -name "libcublas*.so*" -exec cp -vL {} /usr/lib/x86_64-linux-gnu/ \; 2>/dev/null || true && \
    find /app/.venv -name "libcusparse*.so*" -exec cp -vL {} /usr/lib/x86_64-linux-gnu/ \; 2>/dev/null || true && \
    find /app/.venv -name "libnvjitlink*.so*" -exec cp -vL {} /usr/lib/x86_64-linux-gnu/ \; 2>/dev/null || true && \
    ldconfig

# Copy source code, configurations, scripts, and static assets
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY tests/ ./tests/

# Make scripts executable
RUN chmod +x ./scripts/*.sh ./scripts/*.py 2>/dev/null || true

# Expose ports: 8081 (Main API & Dashboard), 8089 (llama backend), 8090 (embedding), 8091 (reranker)
EXPOSE 8081 8089 8090 8091

# Default entrypoint
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8081"]
