# config.py - Application Configuration

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # API Keys
    GEMINI_API_KEY: str = ""
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/bidwise"
    
    # ChromaDB
    CHROMA_DB_PATH: str = "./chroma_data"
    
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_EXCHANGE: str = "bidwise"
    RABBITMQ_PREFETCH_COUNT: int = 10
    
    # Cache
    CACHE_TTL: int = 3600  # 1 hour
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8006
    DEBUG: bool = True
    
    # AI Model
    AI_MODEL_NAME: str = "gemini-2.0-flash-exp"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
