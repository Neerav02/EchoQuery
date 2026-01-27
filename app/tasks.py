import time
import os
import boto3
from celery_app import celery_app
from database import SessionLocal
import models

@celery_app.task(name="create_task")
def create_task(job_id):
    print(f"Worker: Starting Job {job_id}")
    db = SessionLocal()

    # --- LAZY IMPORTS ---
    import whisper
    from transformers import pipeline
    
    # --- SMART S3 CONFIGURATION ---
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "echo-bucket")
    
    s3_client = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name="us-east-1"
    )

    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job: return "Job not found"

        job.status = "PROCESSING"
        db.commit()

        # 1. Download
        local_filename = f"temp_{job.storage_name}"
        s3_client.download_file(S3_BUCKET_NAME, job.storage_name, local_filename)

        # 2. Transcribe (Whisper)
        print("Worker: Running Whisper...")
        model = whisper.load_model("base")
        result = model.transcribe(local_filename)
        transcript_text = result["text"]
        
        # 3. Summarize (Hugging Face)
        print("Worker: Running Summarization...")
        summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")
        input_text = transcript_text[:1024] 
        summary_result = summarizer(input_text, max_length=60, min_length=30, do_sample=False)
        summary_text = summary_result[0]['summary_text']

        # 4. Sentiment Analysis (Hugging Face)
        print("Worker: Running Sentiment Analysis...")
        sentiment_analyzer = pipeline("text-classification", model="distilbert-base-uncased-finetuned-sst-2-english")
        sentiment_result = sentiment_analyzer(input_text[:512])
        sentiment_label = sentiment_result[0]['label'] 

        # 5. Save Results
        job.transcript = transcript_text
        job.summary = summary_text
        job.sentiment = sentiment_label
        job.status = "COMPLETED"
        db.commit()
        print("Worker: Job Complete with Analysis!")

        # Cleanup
        if os.path.exists(local_filename):
            os.remove(local_filename)

        return "Success"

    except Exception as e:
        print(f"Worker: ERROR - {str(e)}")
        if job:
            job.status = "FAILED"
            db.commit()
        return "Failed"
    finally:
        db.close()