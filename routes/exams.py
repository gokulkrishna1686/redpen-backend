"""
Exam management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional

from auth import require_role, get_current_user
from schemas import (
    ExamCreate, ExamResponse, ExamUpdate, ExamStatus, 
    UserProfile, UserRole
)
from supabase_client import get_supabase_client


router = APIRouter(prefix="/exams", tags=["Exams"])


@router.post("", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
async def create_exam(
    exam: ExamCreate,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Create a new exam.
    
    Only professors and admins can create exams.
    """
    supabase = get_supabase_client()
    
    # Check if exam_id already exists
    existing = supabase.table("exams").select("id").eq("exam_id", exam.exam_id).execute()
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Exam with ID '{exam.exam_id}' already exists"
        )
    
    # Create exam
    result = supabase.table("exams").insert({
        "exam_id": exam.exam_id,
        "name": exam.name,
        "description": exam.description,
        "created_by": user.id,
        "status": ExamStatus.DRAFT.value
    }).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create exam"
        )
    
    return ExamResponse(**result.data[0])


@router.get("", response_model=list[ExamResponse])
async def list_exams(
    status_filter: Optional[ExamStatus] = None,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    List all exams.
    
    Optionally filter by status.
    """
    supabase = get_supabase_client()
    
    query = supabase.table("exams").select("*")
    
    if status_filter:
        query = query.eq("status", status_filter.value)
    
    result = query.order("created_at", desc=True).execute()
    
    return [ExamResponse(**exam) for exam in result.data]


@router.get("/{exam_id}", response_model=ExamResponse)
async def get_exam(
    exam_id: str,
    user: UserProfile = Depends(require_role(UserRole.STUDENT, UserRole.PROF, UserRole.ADMIN))
):
    """
    Get exam details by ID.
    
    All authenticated users can view exam details.
    """
    supabase = get_supabase_client()
    
    result = supabase.table("exams").select("*").eq("exam_id", exam_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam '{exam_id}' not found"
        )
    
    return ExamResponse(**result.data[0])


@router.patch("/{exam_id}", response_model=ExamResponse)
async def update_exam(
    exam_id: str,
    updates: ExamUpdate,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Update exam details.
    
    Only professors and admins can update exams.
    """
    supabase = get_supabase_client()
    
    # Check exam exists
    existing = supabase.table("exams").select("*").eq("exam_id", exam_id).execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam '{exam_id}' not found"
        )
    
    # Build update dict with only provided fields
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    
    if not update_data:
        return ExamResponse(**existing.data[0])
    
    # Convert enum to value
    if "status" in update_data:
        update_data["status"] = update_data["status"].value
    
    result = supabase.table("exams").update(update_data).eq("exam_id", exam_id).execute()
    
    return ExamResponse(**result.data[0])


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(
    exam_id: str,
    user: UserProfile = Depends(require_role(UserRole.ADMIN))
):
    """
    Delete an exam.
    
    Only admins can delete exams. This will cascade delete all related data.
    """
    supabase = get_supabase_client()
    
    # Check exam exists
    existing = supabase.table("exams").select("id").eq("exam_id", exam_id).execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam '{exam_id}' not found"
        )
    
    supabase.table("exams").delete().eq("exam_id", exam_id).execute()
