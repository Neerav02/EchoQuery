FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Streamlit runs on port 8501 by default
EXPOSE 8501

# We use the address 0.0.0.0 so we can access it from outside the container
CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0"]