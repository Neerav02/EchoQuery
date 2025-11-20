from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
import models
from database import engine, get_db
from tasks import create_task
import boto3
import uuid

# Initialize Database Tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# MinIO Config
S3_BUCKET_NAME = "echo-bucket"
s3_client = boto3.client(
    "s3",
    endpoint_url="http://minio:9000",
    aws_access_key_id="minio_user",
    aws_secret_access_key="minio_password",
    region_name="us-east-1"
)

# Data Models
class UserCreate(BaseModel):
    email: str
    password: str

# --- ROUTES ---

@app.post("/users/")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing: raise HTTPException(400, "Email exists")
    new_user = models.User(email=user.email, hashed_password=user.password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/upload/")
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    unique_name = f"{uuid.uuid4()}-{file.filename}"
    try:
        s3_client.upload_fileobj(file.file, S3_BUCKET_NAME, unique_name)
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {e}")

    new_job = models.Job(filename=file.filename, storage_name=unique_name, status="PENDING")
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    
    # Trigger the worker
    create_task.delay(new_job.id)

    return {"message": "Upload started", "job_id": new_job.id}

# --- THIS IS HOW YOU SEE THE DATA ---
@app.get("/jobs/{job_id}")
def get_job_status(job_id: int, db: Session = Depends(get_db)):
    # 1. Find the job
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # 2. Return the data
    return {
        "job_id": job.id,
        "status": job.status,
        "transcript": job.transcript,
        "summary": job.summary,     
        "sentiment": job.sentiment  
    }