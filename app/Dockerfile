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
# 'curl' for healthcheck, 'ffmpeg' for media audio processing & Whisper
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version > /dev/null

# 5. Create a non-root user 'appuser'
# This is the "Unique/Pro" step recruiters love.
RUN useradd -m -r appuser

# 6. Set work directory
WORKDIR /app

# 7. Upgrade base package managers for robust download resumption and wheel handling
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 --upgrade pip setuptools wheel

# 8. Install CPU-only PyTorch (Dedicated layer prevents CUDA packages and optimizes Docker caching)
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 torch==2.14.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu

# 9. Install application requirements (PyTorch dependencies resolve from PyPI; torch version preserved)
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# 10. Build-time verification (Pip consistency check, CPU-only verification, version & architecture verification)
RUN python -m pip check \
    && python -c "import torch, platform; print(f'=== Build-time Verification: PyTorch {torch.__version__} | CUDA: {torch.version.cuda} | Arch: {platform.machine()} ==='); assert torch.version.cuda is None, 'CUDA packages detected; expected CPU-only'; assert torch.__version__ == '2.14.1+cpu', f'Unexpected torch version: {torch.__version__}'; assert platform.machine() in ('aarch64', 'arm64', 'x86_64'), f'Unexpected architecture: {platform.machine()}'; print('=== Verification Passed: PyTorch CPU-only confirmed ===')"

# 11. Copy Code & Change Ownership
# We give 'appuser' permission to use this folder
COPY . .
RUN chown -R appuser:appuser /app

# 12. Switch to non-root user
USER appuser

# 13. Expose Port
EXPOSE 8000

# 14. Healthcheck (Self-Healing)
# Docker will ping this every 30s. If it fails, it restarts the container.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 15. Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]