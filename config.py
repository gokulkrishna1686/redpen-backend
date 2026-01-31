"""
Configuration management using Pydantic Settings.
Loads environment variables from .env file.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Google Gemini
    GOOGLE_API_KEY: str
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    
    # App settings
    APP_NAME: str = "Exam Grading System"
    DEBUG: bool = False
    
    # Gemini model
    GEMINI_MODEL: str = "gemini-2.5-pro-preview-05-06"
    
    # Storage bucket name
    STORAGE_BUCKET: str = "answer-sheets"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
