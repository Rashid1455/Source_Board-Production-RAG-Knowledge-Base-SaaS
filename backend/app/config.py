from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql://sourceboard:sourceboard@localhost:5432/sourceboard'
    app_origin: str = 'http://localhost:3000'
    cookie_secure: bool = False
    s3_endpoint: str = 'http://localhost:9000'
    s3_access_key: str = 'sourceboard'
    s3_secret_key: str = 'sourceboard-local-only'
    s3_bucket: str = 'sourceboard'
    s3_region: str = 'us-east-1'
    model_api_key: str = ''
    model_base_url: str = 'https://api.openai.com/v1'
    embedding_model: str = 'text-embedding-3-small'
    chat_model: str = 'gpt-4.1-mini'
    min_similarity: float = 0.40
    upload_limit: int = 10 * 1024 * 1024
    worker_poll_seconds: int = 3


@lru_cache
def settings():
    return Settings()
