web: uvicorn app.main:app --port 8000 & streamlit run frontend/main.py --server.port $PORT --server.address 0.0.0.0
worker: celery -A app.tasks.celery_app worker --loglevel=info
frontend: streamlit run frontend/main.py --server.port $PORT --server.address 0.0.0.0
