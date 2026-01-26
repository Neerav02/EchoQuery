# # 1. Start with Python 3.10
# FROM python:3.10-slim

# # 2. Set working directory
# WORKDIR /code

# # 3. INSTALL SYSTEM DEPENDENCIES (FFmpeg)
# # This is the new part. We update the package list and install ffmpeg.
# RUN apt-get update && apt-get install -y ffmpeg

# # 4. Copy requirements and install Python libraries
# COPY ./requirements.txt /code/requirements.txt
# RUN pip install --no-cache-dir --upgrade -r requirements.txt

# # 5. Copy the rest of the code
# COPY . /code/

# # 6. Start the app
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]

# 1. Base Image: Official Python Slim version (Smaller & Faster)
FROM python:3.10-slim

# 2. Add Metadata (Makes it professional)
LABEL maintainer="Neerav Babel <your_email@example.com>"
LABEL description="EchoQuery Backend API"

# 3. Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 4. Install System Dependencies
# We need 'curl' for the Healthcheck later
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 5. Create a non-root user 'appuser'
# This is the "Unique/Pro" step recruiters love.
RUN useradd -m -r appuser

# 6. Set work directory
WORKDIR /app

# 7. Install Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8. Copy Code & Change Ownership
# We give 'appuser' permission to use this folder
COPY . .
RUN chown -R appuser:appuser /app

# 9. Switch to non-root user
USER appuser

# 10. Expose Port
EXPOSE 8000

# 11. Healthcheck (Self-Healing)
# Docker will ping this every 30s. If it fails, it restarts the container.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/docs || exit 1

# 12. Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]