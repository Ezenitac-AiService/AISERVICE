FROM python:3.12-slim
WORKDIR /workspace
COPY packages/core /workspace/packages/core
COPY services/chatbot_a /workspace/services/chatbot_a
RUN pip install --no-cache-dir /workspace/packages/core /workspace/services/chatbot_a
EXPOSE 8501
CMD ["python", "services/chatbot_a/app.py"]
