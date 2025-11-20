🎙️ EchoQuery: Asynchronous AI Media Analysis Pipeline

[Python](https://img.shields.io/badge/Python-3.10-blue?style=for-the-badge&logo=python&logoColor=white)
[FastAPI](https://img.shields.io/badge/FastAPI-0.100-009688?style=for-the-badge&logo=fastapi&logoColor=white)
[Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
[Celery](https://img.shields.io/badge/Celery-Distributed-green?style=for-the-badge&logo=celery&logoColor=white)
[OpenAI Whisper](https://img.shields.io/badge/AI-OpenAI%20Whisper-purple?style=for-the-badge)

**EchoQuery** is an enterprise-grade, event-driven backend system designed to process heavy media files asynchronously. It leverages a microservices architecture to ingest audio, transcribe it using **OpenAI Whisper**, and perform advanced NLP analysis (Summarization & Sentiment) using **Hugging Face Transformers**.

Unlike simple synchronous applications that freeze during heavy processing, EchoQuery uses a **Producer-Consumer** pattern to handle compute-intensive AI tasks in the background without blocking the main API.

---

🖼️ Project Demo

### The Dashboard (Streamlit)
*User uploads a file, waits for real-time processing, and views the AI-generated insights.*

![Dashboard Screenshot] 
![WhatsApp Image 2025-11-20 at 23 01 21_df82eca2](https://github.com/user-attachments/assets/78b463bd-f166-4ec9-b93c-bc98b477a3dc)

---

🏗️ System Architecture

The system is containerized using **Docker** and orchestrates 6 interacting services to ensure scalability and fault tolerance.

### The Workflow
1.  **Ingestion:** User uploads a file via the Frontend. The **API (FastAPI)** streams it directly to **MinIO** (Object Storage) to keep the database light.
2.  **Queuing:** The API creates a job record in **PostgreSQL** and pushes a task ID to the **RabbitMQ** message broker.
3.  **Processing:** The **Celery Worker** (listening on a separate thread) picks up the task, downloads the file, and loads the AI models.
4.  **AI Analysis:**
    * **Transcription:** OpenAI Whisper (`base` model).
    * **Summarization:** `sshleifer/distilbart-cnn-12-6`.
    * **Sentiment:** `distilbert-base-uncased-finetuned-sst-2-english`.
5.  **Result:** Data is saved to PostgreSQL. The Frontend polls the API and displays the results instantly.

---

🛠️ Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | Streamlit | Interactive UI for uploads & result visualization |
| **Backend API** | FastAPI (Python) | High-performance REST API, Request Handling |
| **Async Workers** | Celery | Distributed Task Queue for background processing |
| **Broker** | RabbitMQ | Message Broker to decouple API from Workers |
| **Database** | PostgreSQL | Relational DB for User Auth & Job Metadata |
| **Storage** | MinIO | S3-Compatible Object Storage for large media files |
| **AI / ML** | OpenAI Whisper | Speech-to-Text Transcription |
| **NLP** | Hugging Face | Summarization & Sentiment Analysis |
| **DevOps** | Docker Compose | Container Orchestration |

---
📂 Project Directory Structure

EchoQuery/
├── app/
│   ├── main.py          # FastAPI entry point & Endpoints
│   ├── tasks.py         # Celery Worker & AI Logic (The "Brain")
│   ├── models.py        # SQLAlchemy Database Schemas
│   ├── database.py      # DB Connection Configuration
│   ├── celery_app.py    # Celery App & Broker Config
│   ├── requirements.txt # Backend Python Dependencies
│   └── Dockerfile       # Backend Container Instructions
├── frontend/
│   ├── main.py          # Streamlit Dashboard Logic
│   └── Dockerfile       # Frontend Container Instructions
├── screenshots/         # Images for README
├── docker-compose.yml   # The Master Orchestration File

---

🚀 Installation & Setup Guide

Follow these steps to run the project locally.

Prerequisites
* **Docker Desktop** installed and running.
* **Git** installed.

🕹️ Usage

Once the containers are running, access the services via your browser:

1. The Frontend Dashboard (Streamlit)
Use this to upload files and view the AI analysis.
👉 [Click here to open Dashboard](http://localhost:8501)

2. API Documentation (Swagger UI)
Use this to manually test the backend endpoints.
👉 [Click here to open API Docs](http://localhost:8000/docs)

3. Storage Console (MinIO)
Use this to view the raw files stored in the system.
👉 [Click here to open MinIO](http://localhost:9001)

---

1. Clone the Repository
```bash
git clone [ https://github.com/Neerav02/EchoQuery.git]
cd EchoQuery
