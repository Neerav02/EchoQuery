# FROM python:3.9-slim

# WORKDIR /app

# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# COPY . .

# # Streamlit runs on port 8501 by default
# EXPOSE 8501

# # We use the address 0.0.0.0 so we can access it from outside the container
# CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0"]

FROM python:3.10-slim

LABEL maintainer="Neerav Babel"

# Prevent Python buffering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd -m -r appuser

# Copy code
COPY . .
RUN chown -R appuser:appuser /app

# Switch user
USER appuser

EXPOSE 8501

# Healthcheck for Streamlit
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0"]