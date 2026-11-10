import json
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from database import SessionLocal
import models
from config import settings

logger = logging.getLogger("echoquery.outbox")

def enqueue_outbox_task(
    db: Session, 
    job_id: int, 
    topic: str, 
    payload: Dict[str, Any]
) -> models.OutboxTask:
    """
    Enqueues a durable task in the Transactional Outbox table within the caller's active database transaction.
    Guarantees that the job record and its dispatch intention commit atomically.
    """
    outbox_task = models.OutboxTask(
        job_id=job_id,
        topic=topic,
        payload=json.dumps(payload),
        status="QUEUED",
        retry_count=0
    )
    db.add(outbox_task)
    db.flush()
    return outbox_task

def dispatch_single_task(task: models.OutboxTask, db: Session) -> bool:
    """
    Attempts to dispatch a single outbox task to the message broker (Celery / RabbitMQ).
    Marks task as DISPATCHED upon success or updates retry count and error upon failure.
    """
    from tasks import create_task
    try:
        payload = json.loads(task.payload)
        job_id = payload.get("job_id", task.job_id)
        user_email = payload.get("email")

        # Dispatch to Celery worker queue
        create_task.delay(job_id, user_email)

        task.status = "DISPATCHED"
        task.dispatched_at = datetime.now(timezone.utc)
        task.error_message = None
        db.commit()
        logger.info(f"Outbox task #{task.id} (Job #{job_id}) successfully dispatched to message broker.")
        return True

    except Exception as e:
        task.retry_count += 1
        task.error_message = str(e)
        if task.retry_count >= 5:
            task.status = "FAILED"
            logger.error(f"Outbox task #{task.id} failed permanently after {task.retry_count} retries: {e}")
        else:
            task.status = "QUEUED"
            logger.warning(f"Outbox task #{task.id} dispatch attempt {task.retry_count} failed: {e}. Will retry.")
        db.commit()
        return False

def relay_pending_outbox_tasks(limit: int = 50) -> int:
    """
    Polls the outbox for QUEUED tasks and attempts to dispatch them.
    Returns the count of successfully dispatched tasks.
    """
    db = SessionLocal()
    dispatched_count = 0
    try:
        pending_tasks = (
            db.query(models.OutboxTask)
            .filter(models.OutboxTask.status == "QUEUED")
            .order_by(models.OutboxTask.created_at.asc())
            .limit(limit)
            .all()
        )

        for task in pending_tasks:
            if dispatch_single_task(task, db):
                dispatched_count += 1

        return dispatched_count
    finally:
        db.close()

class OutboxRelayDaemon:
    """
    Background worker thread that periodically flushes queued outbox tasks
    to the RabbitMQ / Celery broker, ensuring at-least-once durable delivery.
    """
    def __init__(self, interval_seconds: float = 3.0):
        self.interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="EchoQuery-OutboxRelay", daemon=True)
        self._thread.start()
        logger.info("OutboxRelay daemon started.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("OutboxRelay daemon stopped.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                relay_pending_outbox_tasks(limit=100)
            except Exception as e:
                logger.error(f"Error in OutboxRelay loop: {e}")
            self._stop_event.wait(self.interval)

outbox_relay = OutboxRelayDaemon()
