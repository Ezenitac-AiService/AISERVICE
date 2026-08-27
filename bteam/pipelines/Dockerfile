FROM python:3.12-slim
WORKDIR /workspace
COPY packages/core /workspace/packages/core
COPY pipelines /workspace/pipelines
COPY deployment /workspace/deployment
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.2.2+cpu
RUN pip install --no-cache-dir /workspace/packages/core /workspace/pipelines
CMD ["sh", "-c", "python -m deployment.preflight && python -m pipelines.pipeline_runner --all-products --steps all --interval-hours 24"]
