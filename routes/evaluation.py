"""
Evaluation trigger and status endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from auth import require_role
from schemas import (
    EvaluationJobResponse, EvaluationStartResponse, EvaluationJobStatus,
    UserProfile, UserRole
)
from supabase_client import get_supabase_client
from evaluator import start_evaluation, get_exam_job_status


router = APIRouter(prefix="/exams/{exam_id}", tags=["Evaluation"])


@router.post("/evaluate", response_model=EvaluationStartResponse)
async def trigger_evaluation(
    exam_id: str,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Start the async evaluation process for all answer sheets.
    
    This triggers a background job that:
    1. Downloads each answer sheet PDF
    2. Extracts the student ID using Gemini
    3. Evaluates answers against the rubric
    4. Stores results in the database
    
    Use /status to monitor progress.
    """
    supabase = get_supabase_client()
    
    # Check exam exists
    exam_result = supabase.table("exams").select("*").eq("exam_id", exam_id).execute()
    if not exam_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam '{exam_id}' not found"
        )
    
    exam = exam_result.data[0]
    
    # Check if already evaluating
    if exam["status"] == "evaluating":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evaluation is already in progress for this exam"
        )
    
    try:
        job_id = await start_evaluation(exam_id)
        
        return EvaluationStartResponse(
            message="Evaluation started successfully",
            job_id=job_id,
            status=EvaluationJobStatus.IN_PROGRESS
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start evaluation: {str(e)}"
        )


@router.get("/status", response_model=EvaluationJobResponse)
async def get_evaluation_status(
    exam_id: str,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Get the status of the latest evaluation job for an exam.
    """
    job = get_exam_job_status(exam_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evaluation job found for exam '{exam_id}'"
        )
    
    return EvaluationJobResponse(**job)


@router.get("/status/{job_id}", response_model=EvaluationJobResponse)
async def get_job_status_by_id(
    exam_id: str,
    job_id: str,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Get the status of a specific evaluation job.
    """
    supabase = get_supabase_client()
    
    result = supabase.table("evaluation_jobs").select("*").eq("id", job_id).eq("exam_id", exam_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation job not found"
        )
    
    return EvaluationJobResponse(**result.data[0])
