FROM python:3.12-slim
WORKDIR /workspace
COPY packages/core /workspace/packages/core
COPY services/dashboard_backend /workspace/services/dashboard_backend
RUN pip install --no-cache-dir /workspace/packages/core /workspace/services/dashboard_backend
EXPOSE 5050
CMD ["python", "-m", "services.dashboard_backend.app"]
