# 1. Start with Python 3.10
FROM python:3.10-slim

# 2. Set working directory
WORKDIR /code

# 3. INSTALL SYSTEM DEPENDENCIES (FFmpeg)
# This is the new part. We update the package list and install ffmpeg.
RUN apt-get update && apt-get install -y ffmpeg

# 4. Copy requirements and install Python libraries
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# 5. Copy the rest of the code
COPY . /code/

# 6. Start the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]