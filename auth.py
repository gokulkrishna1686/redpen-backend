"""
Authentication middleware for Supabase JWT validation.
Provides role-based access control for API endpoints.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from typing import Optional
from functools import wraps

from config import get_settings
from schemas import UserProfile, UserRole
from supabase_client import get_supabase_client

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserProfile:
    """
    Validate JWT token and return the current user's profile.
    
    Args:
        credentials: Bearer token from Authorization header
        
    Returns:
        UserProfile with user details and role
        
    Raises:
        HTTPException: If token is invalid or user not found
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
        # Supabase uses the anon key as the JWT secret for verification
        # But we need to decode without verification to get the user ID,
        # then fetch the profile from the database
        payload = jwt.decode(
            token,
            settings.SUPABASE_ANON_KEY,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
    except JWTError as e:
        # Try decoding with service key as fallback
        try:
            payload = jwt.decode(
                token,
                settings.SUPABASE_SERVICE_KEY,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user ID",
        )
    
    # Fetch user profile from database
    supabase = get_supabase_client()
    result = supabase.table("profiles").select("*").eq("id", user_id).execute()
    
    if not result.data:
        # Profile might not exist yet, create with default role
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found. Please complete registration.",
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
    Useful for endpoints that have optional authentication.
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
    
    Args:
        allowed_roles: Roles that are allowed to access the endpoint
        
    Returns:
        Dependency function that validates user role
        
    Example:
        @router.post("/exams")
        async def create_exam(user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))):
            ...
    """
    async def role_checker(
        user: UserProfile = Depends(get_current_user)
    ) -> UserProfile:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}",
            )
        return user
    
    return role_checker


# Convenience dependencies for common role combinations
require_prof = require_role(UserRole.PROF, UserRole.ADMIN)
require_admin = require_role(UserRole.ADMIN)
require_any_role = require_role(UserRole.STUDENT, UserRole.PROF, UserRole.ADMIN)
