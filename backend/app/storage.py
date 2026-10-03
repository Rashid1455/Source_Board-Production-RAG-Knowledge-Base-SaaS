from functools import lru_cache
import boto3
from botocore.config import Config
from .config import settings


@lru_cache
def storage():
    cfg = settings()
    return boto3.client('s3', endpoint_url=cfg.s3_endpoint or None,
                       aws_access_key_id=cfg.s3_access_key, aws_secret_access_key=cfg.s3_secret_key,
                       region_name=cfg.s3_region,
                       config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=30,
                                     retries={'max_attempts':3}, s3={'addressing_style':'path'}))
