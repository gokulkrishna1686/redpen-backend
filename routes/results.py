"""
Results management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional

from auth import require_role, get_current_user
from schemas import (
    ResultResponse, ResultUpdate, ResultsSummary, QuestionBreakdown,
    IllegalFlagResponse, IllegalFlagResolve,
    UserProfile, UserRole
)
from supabase_client import get_supabase_client


router = APIRouter(prefix="/exams/{exam_id}/results", tags=["Results"])


@router.get("", response_model=ResultsSummary)
async def get_all_results(
    exam_id: str,
    pending_review_only: bool = False,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Get all results for an exam with summary statistics.
    """
    supabase = get_supabase_client()
    
    query = supabase.table("results").select("*").eq("exam_id", exam_id)
    
    if pending_review_only:
        query = query.eq("has_illegible", True).eq("reviewed", False)
    
    result = query.order("student_id").execute()
    
    results = [ResultResponse(**r) for r in result.data]
    
    # Calculate summary stats
    total_students = len(results)
    evaluated_students = len([r for r in results if not r.has_illegible or r.reviewed])
    pending_review = len([r for r in results if r.has_illegible and not r.reviewed])
    
    total_marks_sum = sum(r.total_marks or 0 for r in results if r.total_marks is not None)
    average_marks = total_marks_sum / total_students if total_students > 0 else None
    
    return ResultsSummary(
        exam_id=exam_id,
        total_students=total_students,
        evaluated_students=evaluated_students,
        pending_review=pending_review,
        average_marks=average_marks,
        results=results
    )


@router.get("/{student_id}", response_model=ResultResponse)
async def get_student_result(
    exam_id: str,
    student_id: str,
    user: UserProfile = Depends(get_current_user)
):
    """
    Get result for a specific student.
    
    Students can only view their own results.
    Professors and admins can view any result.
    """
    supabase = get_supabase_client()
    
    # Authorization check for students
    if user.role == UserRole.STUDENT:
        if user.student_id != student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own results"
            )
    
    result = supabase.table("results").select("*").eq("exam_id", exam_id).eq("student_id", student_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result not found for student '{student_id}' in exam '{exam_id}'"
        )
    
    return ResultResponse(**result.data[0])


@router.patch("/{student_id}", response_model=ResultResponse)
async def update_result(
    exam_id: str,
    student_id: str,
    updates: ResultUpdate,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Update a student's result (professor override).
    
    This allows professors to:
    - Correct AI grading errors
    - Override marks for specific questions
    - Mark the result as reviewed
    """
    supabase = get_supabase_client()
    
    # Check result exists
    existing = supabase.table("results").select("*").eq("exam_id", exam_id).eq("student_id", student_id).execute()
    
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result not found for student '{student_id}'"
        )
    
    current_result = existing.data[0]
    update_data = {}
    
    # Update breakdown if provided
    if updates.breakdown:
        new_breakdown = current_result["breakdown"].copy()
        
        for qid, question_update in updates.breakdown.items():
            new_breakdown[qid] = question_update.model_dump()
        
        update_data["breakdown"] = new_breakdown
        
        # Recalculate total marks
        total_marks = 0.0
        has_illegible = False
        for qid, breakdown in new_breakdown.items():
            if breakdown.get("illegible"):
                has_illegible = True
            elif breakdown.get("awarded") is not None:
                total_marks += breakdown["awarded"]
        
        update_data["total_marks"] = total_marks
        update_data["has_illegible"] = has_illegible
    
    # Update reviewed status
    if updates.reviewed is not None:
        update_data["reviewed"] = updates.reviewed
    
    if not update_data:
        return ResultResponse(**current_result)
    
    result = supabase.table("results").update(update_data).eq("exam_id", exam_id).eq("student_id", student_id).execute()
    
    return ResultResponse(**result.data[0])


# ============== Illegible Flags Routes ==============

@router.get("/{student_id}/illegible", response_model=list[IllegalFlagResponse])
async def get_illegible_flags(
    exam_id: str,
    student_id: str,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Get all illegible flags for a student's result.
    """
    supabase = get_supabase_client()
    
    result = supabase.table("illegible_flags").select("*").eq("exam_id", exam_id).eq("student_id", student_id).execute()
    
    return [IllegalFlagResponse(**flag) for flag in result.data]


@router.patch("/{student_id}/illegible/{question_id}", response_model=IllegalFlagResponse)
async def resolve_illegible_flag(
    exam_id: str,
    student_id: str,
    question_id: str,
    resolution: IllegalFlagResolve,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Resolve an illegible flag by manually assigning marks.
    """
    supabase = get_supabase_client()
    from datetime import datetime
    
    # Find the flag
    flag_result = supabase.table("illegible_flags").select("*").eq("exam_id", exam_id).eq("student_id", student_id).eq("question_id", question_id).execute()
    
    if not flag_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Illegible flag not found for question '{question_id}'"
        )
    
    flag = flag_result.data[0]
    
    # Update the flag
    updated_flag = supabase.table("illegible_flags").update({
        "resolved": True,
        "resolved_by": user.id,
        "resolved_marks": resolution.marks,
        "resolved_at": datetime.utcnow().isoformat()
    }).eq("id", flag["id"]).execute()
    
    # Update the result breakdown
    result_data = supabase.table("results").select("*").eq("exam_id", exam_id).eq("student_id", student_id).execute()
    
    if result_data.data:
        current_result = result_data.data[0]
        breakdown = current_result["breakdown"]
        
        if question_id in breakdown:
            breakdown[question_id]["awarded"] = resolution.marks
            breakdown[question_id]["illegible"] = False
            breakdown[question_id]["justification"] = f"Manually graded by professor. Original: {breakdown[question_id].get('justification', 'N/A')}"
        
        # Recalculate totals
        total_marks = sum(
            q.get("awarded", 0) for q in breakdown.values() 
            if q.get("awarded") is not None and not q.get("illegible")
        )
        has_illegible = any(q.get("illegible", False) for q in breakdown.values())
        
        supabase.table("results").update({
            "breakdown": breakdown,
            "total_marks": total_marks,
            "has_illegible": has_illegible
        }).eq("exam_id", exam_id).eq("student_id", student_id).execute()
    
    return IllegalFlagResponse(**updated_flag.data[0])
