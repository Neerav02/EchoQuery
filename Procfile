web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT
worker: celery -A app.tasks.celery_app worker --loglevel=info
frontend: streamlit run frontend/main.py --server.port $PORT --server.address 0.0.0.0
