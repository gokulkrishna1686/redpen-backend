"""
Student management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from auth import require_role
from schemas import StudentResponse, StudentUpdate, UserProfile, UserRole
from supabase_client import get_supabase_client


router = APIRouter(prefix="/exams/{exam_id}/students", tags=["Students"])


@router.get("", response_model=list[StudentResponse])
async def list_students(
    exam_id: str,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    List all students who have submitted answer sheets for an exam.
    """
    supabase = get_supabase_client()
    
    # Check exam exists
    exam_result = supabase.table("exams").select("id").eq("exam_id", exam_id).execute()
    if not exam_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam '{exam_id}' not found"
        )
    
    # Get all answer sheets with student IDs
    result = supabase.table("answer_sheets").select("student_id, exam_id, file_name, processed").eq("exam_id", exam_id).execute()
    
    students = []
    for sheet in result.data:
        if sheet.get("student_id"):
            students.append(StudentResponse(
                student_id=sheet["student_id"],
                exam_id=sheet["exam_id"],
                file_name=sheet["file_name"],
                processed=sheet["processed"]
            ))
    
    return students


@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(
    exam_id: str,
    student_id: str,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Get details of a specific student in an exam.
    """
    supabase = get_supabase_client()
    
    result = supabase.table("answer_sheets").select("*").eq("exam_id", exam_id).eq("student_id", student_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found in exam '{exam_id}'"
        )
    
    sheet = result.data[0]
    return StudentResponse(
        student_id=sheet["student_id"],
        exam_id=sheet["exam_id"],
        file_name=sheet["file_name"],
        processed=sheet["processed"]
    )


@router.patch("/{student_id}", response_model=StudentResponse)
async def update_student(
    exam_id: str,
    student_id: str,
    updates: StudentUpdate,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Update student information (e.g., correct misread student ID).
    
    This is useful when Gemini misreads the student ID from the answer sheet.
    """
    supabase = get_supabase_client()
    
    # Find the answer sheet
    existing = supabase.table("answer_sheets").select("*").eq("exam_id", exam_id).eq("student_id", student_id).execute()
    
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found in exam '{exam_id}'"
        )
    
    sheet_id = existing.data[0]["id"]
    old_student_id = existing.data[0]["student_id"]
    new_student_id = updates.student_id or old_student_id
    
    # Update answer sheet
    supabase.table("answer_sheets").update({
        "student_id": new_student_id
    }).eq("id", sheet_id).execute()
    
    # Also update results if they exist
    if new_student_id != old_student_id:
        supabase.table("results").update({
            "student_id": new_student_id
        }).eq("exam_id", exam_id).eq("student_id", old_student_id).execute()
        
        supabase.table("illegible_flags").update({
            "student_id": new_student_id
        }).eq("exam_id", exam_id).eq("student_id", old_student_id).execute()
    
    # Get updated data
    result = supabase.table("answer_sheets").select("*").eq("id", sheet_id).execute()
    sheet = result.data[0]
    
    return StudentResponse(
        student_id=sheet["student_id"],
        exam_id=sheet["exam_id"],
        file_name=sheet["file_name"],
        processed=sheet["processed"]
    )
