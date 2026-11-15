import sys
import time
import os
import uuid
import logging
from sqlalchemy import update

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if "celery_app" in sys.modules or not __package__:
    from celery_app import celery_app
else:
    from app.celery_app import celery_app
from database import SessionLocal
import models
from redis_lock import distributed_lock
from storage import download_file_to_temp
from email_service import send_job_completion_email
from ai.router import default_router
from events import publish_job_event

logger = logging.getLogger("echoquery.tasks")

def analyze_media_content(filename: str, local_path: str = None) -> dict:
    """
    Delegates speech recognition and analytical summarization to HybridAIRouter.
    Returns structured dictionary conforming to job schema.
    """
    target_path = local_path if local_path and os.path.exists(local_path) else filename
    ai_result = default_router.transcribe_and_analyze(target_path)
    return {
        "transcript": ai_result.transcript,
        "summary": ai_result.summary,
        "sentiment": ai_result.sentiment,
        "skills": ai_result.skills,
        "segments": ai_result.segments,
        "provider": ai_result.provider,
        "model_name": ai_result.model_name,
        "token_usage": (ai_result.input_tokens or 0) + (ai_result.output_tokens or 0)
    }

def execute_job_compute_logic(job_id: int, user_email: str = None):
    """
    Core compute logic executed by worker replicas.
    Includes:
    1. Redis distributed lock with ownership token.
    2. Atomic database state claim (PENDING -> PROCESSING).
    3. Ephemeral MinIO file download and scratch cleanup.
    4. Real-time Pub/Sub and stream event publishing.
    5. DLQ transition upon exhausting max retries.
    """
    start_time = time.time()
    db = SessionLocal()
    lock_key = f"job_process_{job_id}"
    claim_token = str(uuid.uuid4())

    with distributed_lock(lock_key, timeout=30) as lock_result:
        tmp_scratch_file = None
        try:
            # 1. Atomic Database State Claim (prevents race condition duplicate compute)
            stmt = (
                update(models.Job)
                .where(models.Job.id == job_id, models.Job.status == "PENDING")
                .values(
                    status="PROCESSING", 
                    lock_token=claim_token, 
                    lock_acquired=True
                )
            )
            result = db.execute(stmt)
            db.commit()

            if result.rowcount == 0:
                existing = db.query(models.Job).filter(models.Job.id == job_id).first()
                if existing:
                    logger.info(f"Job #{job_id} already in status '{existing.status}'. Skipping duplicate execution.")
                return "AlreadyClaimedOrCompleted"

            job = db.query(models.Job).filter(models.Job.id == job_id).first()
            if not job:
                return "Job not found"

            # Broadcast status transition to WebSocket clients
            publish_job_event(job.id, "JOB_STATUS", {"status": "PROCESSING", "filename": job.filename})

            # 2. Ephemeral Storage Retrieval from MinIO / S3
            if job.storage_name:
                try:
                    tmp_scratch_file = download_file_to_temp(job.storage_name, job.storage_bucket)
                    logger.info(f"Downloaded media object '{job.storage_name}' to temp scratch: {tmp_scratch_file}")
                except Exception as s3_err:
                    logger.warning(f"Could not retrieve media file from storage for Job #{job_id}: {s3_err}")

            # 3. Hybrid AI Inference Execution
            analysis = analyze_media_content(job.filename, local_path=tmp_scratch_file)

            # Stream individual transcription segments
            for seg in analysis.get("segments", []):
                publish_job_event(job.id, "TRANSCRIPT_SEGMENT", seg)

            # Stream summarization delta
            publish_job_event(job.id, "SUMMARY_DELTA", {
                "summary": analysis["summary"],
                "sentiment": analysis["sentiment"],
                "skills": analysis["skills"]
            })

            elapsed_time = (time.time() - start_time) * 1000  # ms

            # 4. Atomic Completion Persistence
            job.transcript = analysis["transcript"]
            job.summary = analysis["summary"]
            job.sentiment = analysis["sentiment"]
            job.ai_provider = analysis.get("provider")
            job.ai_model = analysis.get("model_name")
            job.token_usage = analysis.get("token_usage")
            job.status = "COMPLETED"
            job.execution_time_ms = round(elapsed_time, 2)
            job.lock_acquired = False
            job.error_message = None
            db.commit()

            # Broadcast completion event
            publish_job_event(job.id, "JOB_STATUS", {
                "status": "COMPLETED",
                "execution_time_ms": job.execution_time_ms,
                "provider": job.ai_provider
            })

            if user_email:
                try:
                    send_job_completion_email(
                        user_email, job.id, job.filename, 
                        analysis["transcript"], analysis["summary"], 
                        analysis["sentiment"], elapsed_time
                    )
                except Exception as email_err:
                    logger.warning(f"Email notification failed for Job #{job_id}: {email_err}")

            logger.info(f"AI Speech Analysis Complete: Job #{job_id} processed in {elapsed_time:.2f}ms")
            return "Success"

        except Exception as e:
            logger.error(f"Compute Error on Job #{job_id}: {str(e)}")
            db.rollback()
            try:
                job = db.query(models.Job).filter(models.Job.id == job_id).first()
                if job:
                    job.retry_count += 1
                    job.error_message = f"{type(e).__name__}: {str(e)}"
                    job.lock_acquired = False

                    if job.retry_count >= job.max_retries:
                        job.status = "DEAD_LETTER"
                        job.is_dlq = True
                        publish_job_event(job.id, "JOB_STATUS", {"status": "DEAD_LETTER", "error": job.error_message})
                        logger.error(f"Job #{job_id} permanently failed after {job.retry_count} attempts. Diverted to DLQ.")
                    else:
                        job.status = "FAILED"
                        publish_job_event(job.id, "JOB_STATUS", {"status": "FAILED", "error": job.error_message})
                    db.commit()
            except Exception as update_err:
                logger.error(f"Failed to record error state for Job #{job_id}: {update_err}")

            return "Failed"

        finally:
            # 5. Guaranteed scratch disk cleanup
            if tmp_scratch_file and os.path.exists(tmp_scratch_file):
                try:
                    os.unlink(tmp_scratch_file)
                    logger.debug(f"Removed temp scratch file: {tmp_scratch_file}")
                except Exception as cleanup_err:
                    logger.warning(f"Failed to clean temp scratch file {tmp_scratch_file}: {cleanup_err}")
            db.close()

@celery_app.task(
    bind=True,
    name="create_task",
    max_retries=3,
    default_retry_delay=2,
    autoretry_for=(Exception,),
    retry_backoff=True
)
def create_task(self, job_id: int, user_email: str = None):
    result = execute_job_compute_logic(job_id, user_email)
    if result == "Failed":
        db = SessionLocal()
        try:
            job = db.query(models.Job).filter(models.Job.id == job_id).first()
            if job and not job.is_dlq and job.retry_count < job.max_retries:
                err_msg = job.error_message or "Task execution failed"
                job.status = "PENDING"
                db.commit()
                raise self.retry(
                    exc=RuntimeError(err_msg),
                    countdown=min(2 ** self.request.retries, 10),
                )
        finally:
            db.close()
    return result

@celery_app.task(name="replay_dlq_task")
def replay_dlq_task(job_id: int):
    db = SessionLocal()
    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if job and job.is_dlq:
            job.status = "PENDING"
            job.is_dlq = False
            job.retry_count = 0
            job.error_message = None
            db.commit()
            execute_job_compute_logic(job.id)
            return f"Job #{job_id} replayed"
        return "Job not in DLQ"
    finally:
        db.close()
