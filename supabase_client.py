"""
Supabase client singleton for database and storage operations.
"""
from supabase import create_client, Client
from functools import lru_cache
from config import get_settings


@lru_cache()
def get_supabase_client() -> Client:
    """
    Get cached Supabase client instance.
    Uses service role key for full backend access.
    """
    settings = get_settings()
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_KEY
    )


@lru_cache()
def get_supabase_anon_client() -> Client:
    """
    Get cached Supabase client with anon key.
    Used for operations that should respect RLS.
    """
    settings = get_settings()
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY
    )


# Convenience alias
supabase = get_supabase_client()
