FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml .
COPY README.md .

# Install Python dependencies
RUN pip install --no-cache-dir .

# Copy application code
COPY src/ src/

# Copy frontend files
COPY frontend/ frontend/

# Set Python path
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8002/health', timeout=5).raise_for_status()"

# Run the application
EXPOSE 8002
CMD ["python", "-m", "uvicorn", "tradingsystem.main:app", "--host", "0.0.0.0", "--port", "8002"]
