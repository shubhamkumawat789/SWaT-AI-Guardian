# Use official Python 3.10 slim image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV KAFKA_BOOTSTRAP_SERVERS kafka:9093

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY src/ /app/src/
COPY config/ /app/config/
COPY models/ /app/models/
COPY data/ /app/data/

# Create logs directory
RUN mkdir -p /app/logs

# Expose ports (FastAPI: 8000, Streamlit: 8501)
EXPOSE 8000 8501

# Default command (can be overridden in docker-compose)
CMD ["python", "src/api/fastapi_server.py"]
