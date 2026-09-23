# ==============================================================================
# Stage 1: llama.cpp CUDA Builder (Ubuntu 24.04 + CUDA 12.6 Devel)
# ==============================================================================
FROM nvidia/cuda:12.6.1-devel-ubuntu24.04 AS builder

ARG LLAMA_CPP_TAG=master
ENV DEBIAN_FRONTEND=noninteractive \
    CCACHE_DIR=/root/.cache/ccache \
    PATH="/usr/lib/ccache:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    cmake \
    build-essential \
    ccache \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch ${LLAMA_CPP_TAG} https://github.com/ggml-org/llama.cpp.git /build/llama.cpp

RUN ln -sf /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1

ENV LD_LIBRARY_PATH=/usr/local/cuda/lib64/stubs:${LD_LIBRARY_PATH} \
    LIBRARY_PATH=/usr/local/cuda/lib64/stubs:${LIBRARY_PATH}

WORKDIR /build/llama.cpp/build

RUN --mount=type=cache,target=/root/.cache/ccache \
    cmake .. \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CUDA_ARCHITECTURES=86 \
        -DGGML_CUDA=ON \
        -DGGML_CUDA_FA_QUANTS=all \
        -DCMAKE_CXX_FLAGS="-DCPPHTTPLIB_KEEPALIVE_MAX_COUNT=1000" \
        -DCMAKE_EXE_LINKER_FLAGS="-Wl,-rpath-link,/usr/local/cuda/lib64/stubs -L/usr/local/cuda/lib64/stubs" \
        -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-rpath-link,/usr/local/cuda/lib64/stubs -L/usr/local/cuda/lib64/stubs" \
        -DCMAKE_CUDA_COMPILER_LAUNCHER=ccache \
        -DCMAKE_CXX_COMPILER_LAUNCHER=ccache && \
    cmake --build . --config Release --target llama-server -j 4 && \
    strip --strip-unneeded bin/llama-server && \
    mkdir -p /build/out/bin /build/out/lib && \
    cp bin/llama-server /build/out/bin/ && \
    find . -maxdepth 4 -name "*.so*" -exec cp -P {} /build/out/lib/ \;

# ==============================================================================
# Stage 2: Runtime (Ubuntu 24.04 + CUDA 12.6 Runtime)
# ==============================================================================
FROM nvidia/cuda:12.6.1-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/.venv/lib/python3.12/site-packages \
    LD_LIBRARY_PATH=/usr/local/lib:/usr/lib/wsl/lib:/usr/lib/wsl/drivers:/usr/lib/x86_64-linux-gnu \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Ensure /tmp permissions and POSIX shared memory accessibility
RUN chmod 1777 /tmp

# Install minimal OS dependencies, Python 3.12, utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    curl \
    ca-certificates \
    pciutils \
    procps \
    psmisc \
    lsof \
    libgomp1 \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled llama-server binary and shared libraries
COPY --from=builder /build/out/bin/llama-server /usr/local/bin/llama-server
COPY --from=builder /build/out/lib/ /usr/local/lib/
RUN chmod +x /usr/local/bin/llama-server && ldconfig

# Install uv for high-speed package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml requirements.txt uv.lock* ./

# Install runtime packages in /app/.venv
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv fastapi uvicorn sse-starlette pydantic httpx jinja2 numpy python-dotenv requests pytest pytest-asyncio huggingface-hub nvidia-ml-py redis && \
    ldconfig

# Copy source code, configurations, scripts, and tests
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY tests/ ./tests/

# Make scripts executable
RUN chmod +x ./scripts/*.sh ./scripts/*.py 2>/dev/null || true

# Expose ports: 8081 (Ingress API & Dashboard only - Backend ports 8088-8091 are loopback isolated)
EXPOSE 8081

# Default entrypoint
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8081"]
