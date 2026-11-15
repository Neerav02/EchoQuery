import os
import sys
import socket
import logging
from celery import Celery
from kombu import Exchange, Queue

logger = logging.getLogger("echoquery.celery")

def get_effective_broker_url() -> str:
    url = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
    if "@broker:" in url or "broker:5672" in url:
        try:
            socket.gethostbyname("broker")
        except socket.gaierror:
            url = url.replace("@broker:", "@localhost:").replace("@broker/", "@localhost/")
    return url

def get_effective_backend_url() -> str:
    url = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    if "redis:6379" in url or "@redis:" in url:
        try:
            socket.gethostbyname("redis")
        except socket.gaierror:
            url = url.replace("@redis:", "@localhost:").replace("redis://redis:", "redis://localhost:")
    return url

BROKER_URL = get_effective_broker_url()
RESULT_BACKEND = get_effective_backend_url()

# Verify backend connectivity to avoid log spam when running without Redis container
active_backend = RESULT_BACKEND
if "redis" in RESULT_BACKEND:
    try:
        import redis
        r = redis.Redis.from_url(RESULT_BACKEND, socket_timeout=1)
        r.ping()
    except Exception:
        # Fallback to rpc backend if Redis server is offline locally
        active_backend = "rpc://"

# Unify Celery module singleton across import styles (app.celery_app vs celery_app)
if __package__ and "celery_app" not in sys.modules:
    sys.modules["celery_app"] = sys.modules[__name__]

_task_module = f"{__package__}.tasks" if __package__ else "tasks"

celery_app = Celery(
    "echoquery_tasks",
    broker=BROKER_URL,
    backend=active_backend,
    include=[_task_module]
)

# Configure Queues and Dead Letter Queue (DLQ) topology
default_exchange = Exchange("echoquery_exchange", type="direct")
dlx_exchange = Exchange("echoquery_dlx", type="direct")

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True, # Guarantee task delivery (acked after execution)
    task_reject_on_worker_lost=True,
    
    # Queue definition with Dead-Letter-Exchange (DLX) routing
    task_queues=(
        Queue(
            "tasks", 
            default_exchange, 
            routing_key="task.process",
            queue_arguments={
                "x-dead-letter-exchange": "echoquery_dlx",
                "x-dead-letter-routing-key": "task.dlq"
            }
        ),
        Queue(
            "dlq", 
            dlx_exchange, 
            routing_key="task.dlq"
        ),
    ),
    task_default_queue="tasks",
    task_default_exchange="echoquery_exchange",
    task_default_routing_key="task.process",
)