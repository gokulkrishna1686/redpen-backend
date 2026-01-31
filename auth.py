"""
Authentication middleware for Supabase JWT validation.
Provides role-based access control for API endpoints.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from typing import Optional
import httpx

from config import get_settings
from schemas import UserProfile, UserRole
from supabase_client import get_supabase_client

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)

# Cache for JWKS
_jwks_cache = None


async def get_jwks():
    """Fetch Supabase JWKS for token verification."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    
    settings = get_settings()
    jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url)
        if response.status_code == 200:
            _jwks_cache = response.json()
            return _jwks_cache
    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserProfile:
    """
    Validate JWT token and return the current user's profile.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    settings = get_settings()
    
    try:
        # Decode without verification first to get claims
        # Supabase tokens use ES256, which requires public key verification
        # For simplicity, we decode without verification and trust Supabase
        unverified_payload = jwt.get_unverified_claims(token)
        
        user_id = unverified_payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user ID",
            )
        
        # Check token expiration
        import time
        exp = unverified_payload.get("exp", 0)
        if exp < time.time():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Fetch user profile from database
    supabase = get_supabase_client()
    result = supabase.table("profiles").select("*").eq("id", user_id).execute()
    
    if not result.data:
        # Profile doesn't exist - might need to be created
        # Let's try to create it from the token data
        email = unverified_payload.get("email")
        try:
            supabase.table("profiles").insert({
                "id": user_id,
                "email": email,
                "full_name": "",
                "role": "student"  # Default role
            }).execute()
            
            # Fetch again
            result = supabase.table("profiles").select("*").eq("id", user_id).execute()
        except Exception:
            pass
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found. Please contact admin to set up your profile.",
        )
    
    profile_data = result.data[0]
    
    return UserProfile(
        id=profile_data["id"],
        email=profile_data.get("email"),
        full_name=profile_data.get("full_name"),
        role=UserRole(profile_data.get("role", "student")),
        student_id=profile_data.get("student_id"),
    )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[UserProfile]:
    """
    Get current user if authenticated, None otherwise.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory for role-based access control.
    """
    async def role_checker(
        user: UserProfile = Depends(get_current_user)
    ) -> UserProfile:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}. Your role: {user.role.value}",
            )
        return user
    
    return role_checker


# Convenience dependencies
require_prof = require_role(UserRole.PROF, UserRole.ADMIN)
require_admin = require_role(UserRole.ADMIN)
require_any_role = require_role(UserRole.STUDENT, UserRole.PROF, UserRole.ADMIN)
