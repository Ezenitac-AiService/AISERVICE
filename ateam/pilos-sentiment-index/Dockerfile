FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=5000

WORKDIR /app

# Install build dependencies for C-extensions (kiwipiepy, scikit-learn, etc.) and curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package specification
COPY pyproject.toml /app/

# Install python dependencies and gunicorn
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir gunicorn && \
    pip install --no-cache-dir .

# Copy application source code
COPY pilos /app/pilos
COPY data /app/data
COPY docs /app/docs

# Expose web service port
EXPOSE 5000

# Run Flask application via Gunicorn WSGI server with gthread worker profile for SSE concurrency (FR-003)
CMD ["gunicorn", "--worker-class=gthread", "--workers=2", "--threads=4", "--bind=0.0.0.0:5000", "--timeout=300", "pilos.web.app:app"]
