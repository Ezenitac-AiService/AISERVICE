FROM python:3.12-slim
WORKDIR /workspace
COPY packages/core /workspace/packages/core
COPY services/chatbot_b /workspace/services/chatbot_b
RUN pip install --no-cache-dir /workspace/packages/core /workspace/services/chatbot_b
EXPOSE 8002
CMD ["python", "services/chatbot_b/main.py"]
