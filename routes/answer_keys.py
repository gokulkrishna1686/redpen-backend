"""
Answer key management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from auth import require_role
from schemas import (
    AnswerKeyCreate, AnswerKeyResponse, ExamStatus,
    UserProfile, UserRole
)
from supabase_client import get_supabase_client


router = APIRouter(prefix="/exams/{exam_id}/answer-key", tags=["Answer Keys"])


@router.post("", response_model=AnswerKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_answer_key(
    exam_id: str,
    answer_key: AnswerKeyCreate,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Create or update the answer key for an exam.
    
    Only professors and admins can manage answer keys.
    The answer key includes questions with rubrics and keywords for grading.
    """
    supabase = get_supabase_client()
    
    # Check exam exists
    exam_result = supabase.table("exams").select("*").eq("exam_id", exam_id).execute()
    if not exam_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam '{exam_id}' not found"
        )
    
    # Convert questions to dict for JSON storage
    questions_data = [q.model_dump() for q in answer_key.questions]
    
    # Upsert answer key (create or update)
    result = supabase.table("answer_keys").upsert({
        "exam_id": exam_id,
        "questions": questions_data
    }, on_conflict="exam_id").execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save answer key"
        )
    
    # Update exam status to ready if still draft
    if exam_result.data[0]["status"] == ExamStatus.DRAFT.value:
        supabase.table("exams").update({"status": ExamStatus.READY.value}).eq("exam_id", exam_id).execute()
    
    return AnswerKeyResponse(**result.data[0])


@router.get("", response_model=AnswerKeyResponse)
async def get_answer_key(
    exam_id: str,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Get the answer key for an exam.
    
    Only professors and admins can view answer keys.
    """
    supabase = get_supabase_client()
    
    result = supabase.table("answer_keys").select("*").eq("exam_id", exam_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Answer key not found for exam '{exam_id}'"
        )
    
    return AnswerKeyResponse(**result.data[0])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_answer_key(
    exam_id: str,
    user: UserProfile = Depends(require_role(UserRole.ADMIN))
):
    """
    Delete the answer key for an exam.
    
    Only admins can delete answer keys.
    """
    supabase = get_supabase_client()
    
    # Check exists
    existing = supabase.table("answer_keys").select("id").eq("exam_id", exam_id).execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Answer key not found for exam '{exam_id}'"
        )
    
    supabase.table("answer_keys").delete().eq("exam_id", exam_id).execute()
    
    # Revert exam status to draft
    supabase.table("exams").update({"status": ExamStatus.DRAFT.value}).eq("exam_id", exam_id).execute()
