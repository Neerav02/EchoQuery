import os
import logging
import tempfile
import shutil
import socket
from urllib.parse import urlparse
from typing import Optional, BinaryIO
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

logger = logging.getLogger("echoquery.storage")

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "minio_user")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio_password")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "echo-bucket")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
LOCAL_STORAGE_DIR = os.getenv("LOCAL_STORAGE_DIR", os.path.join(tempfile.gettempdir(), "echoquery_storage"))

_s3_client = None

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        try:
            s3_config = Config(
                connect_timeout=0.5,
                read_timeout=1.0,
                retries={"max_attempts": 1}
            )
            _s3_client = boto3.client(
                "s3",
                endpoint_url=S3_ENDPOINT_URL,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION,
                config=s3_config
            )
        except Exception as e:
            logger.warning(f"Failed to initialize S3 client: {e}")
            _s3_client = None
    return _s3_client

def is_storage_available() -> bool:
    """Verifies whether the S3/MinIO service is reachable using fast socket probe."""
    try:
        parsed = urlparse(S3_ENDPOINT_URL)
        host = parsed.hostname or "localhost"
        port = parsed.port or 9000
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.2)
        s.connect((host, port))
        s.close()
    except Exception:
        return False

    client = get_s3_client()
    if not client:
        return False
    try:
        client.list_buckets()
        return True
    except Exception:
        return False

def ensure_bucket_exists(bucket_name: Optional[str] = None) -> bool:
    """Creates the target S3 bucket if it doesn't already exist."""
    bucket = bucket_name or S3_BUCKET_NAME
    client = get_s3_client()
    if not client:
        return False

    try:
        client.head_bucket(Bucket=bucket)
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code in ["404", "NoSuchBucket"]:
            try:
                if AWS_REGION == "us-east-1":
                    client.create_bucket(Bucket=bucket)
                else:
                    client.create_bucket(
                        Bucket=bucket,
                        CreateBucketConfiguration={"LocationConstraint": AWS_REGION}
                    )
                logger.info(f"S3 bucket '{bucket}' created successfully.")
                return True
            except Exception as create_err:
                logger.error(f"Failed to create bucket '{bucket}': {create_err}")
                return False
        logger.error(f"Error checking bucket '{bucket}': {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating bucket '{bucket}': {e}")
        return False

def upload_file_stream(file_obj: BinaryIO, storage_name: str, bucket_name: Optional[str] = None, content_type: Optional[str] = None) -> str:
    """
    Streams file bytes directly to MinIO/S3.
    Falls back to local file storage if S3/MinIO is unreachable.
    """
    bucket = bucket_name or S3_BUCKET_NAME

    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    if is_storage_available():
        client = get_s3_client()
        if client:
            try:
                ensure_bucket_exists(bucket)
                file_obj.seek(0)
                client.upload_fileobj(file_obj, bucket, storage_name, ExtraArgs=extra_args if extra_args else None)
                logger.info(f"Uploaded '{storage_name}' to S3 bucket '{bucket}'.")
                return storage_name
            except Exception as e:
                logger.warning(f"S3 upload failed for '{storage_name}': {e}. Falling back to local storage.")

    # Local fallback
    os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)
    local_path = os.path.join(LOCAL_STORAGE_DIR, storage_name)
    file_obj.seek(0)
    with open(local_path, "wb") as f:
        shutil.copyfileobj(file_obj, f)
    logger.info(f"Stored '{storage_name}' in local storage: {local_path}")
    return storage_name

def download_file_to_temp(storage_name: str, bucket_name: Optional[str] = None) -> str:
    """
    Retrieves a media file from MinIO/S3 or local fallback storage,
    saving it to a temporary local file for worker processing.
    The caller is responsible for deleting the temp file after use.
    """
    bucket = bucket_name or S3_BUCKET_NAME

    suffix = os.path.splitext(storage_name)[1] or ".bin"
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = temp_file.name
    temp_file.close()

    # Try downloading from S3/MinIO first if available
    if is_storage_available():
        client = get_s3_client()
        if client:
            try:
                client.download_file(bucket, storage_name, temp_path)
                logger.info(f"Downloaded '{storage_name}' from S3 bucket '{bucket}' to temp: {temp_path}")
                return temp_path
            except Exception as e:
                logger.warning(f"Could not download '{storage_name}' from S3: {e}. Checking local storage fallback.")

    # Check local fallback directory
    local_source = os.path.join(LOCAL_STORAGE_DIR, storage_name)
    if os.path.exists(local_source):
        shutil.copy(local_source, temp_path)
        logger.info(f"Retrieved '{storage_name}' from local storage: {temp_path}")
        return temp_path

    raise FileNotFoundError(f"Media file '{storage_name}' not found in S3 bucket '{bucket}' or local fallback storage.")

def delete_file(storage_name: str, bucket_name: Optional[str] = None) -> bool:
    """Deletes the media object from S3 and local storage."""
    bucket = bucket_name or S3_BUCKET_NAME
    success = False

    if is_storage_available():
        client = get_s3_client()
        if client:
            try:
                client.delete_object(Bucket=bucket, Key=storage_name)
                success = True
            except Exception as e:
                logger.warning(f"Failed to delete '{storage_name}' from S3: {e}")

    local_path = os.path.join(LOCAL_STORAGE_DIR, storage_name)
    if os.path.exists(local_path):
        try:
            os.remove(local_path)
            success = True
        except Exception as e:
            logger.warning(f"Failed to delete local fallback '{local_path}': {e}")

    return success
