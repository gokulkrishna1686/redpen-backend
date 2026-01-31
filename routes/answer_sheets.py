"""
Answer sheet upload endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List

from auth import require_role
from schemas import AnswerSheetResponse, UserProfile, UserRole
from supabase_client import get_supabase_client
from storage import upload_pdf, get_pdf_url, list_pdfs


router = APIRouter(prefix="/exams/{exam_id}/answer-sheets", tags=["Answer Sheets"])


@router.post("", response_model=list[AnswerSheetResponse], status_code=status.HTTP_201_CREATED)
async def upload_answer_sheets(
    exam_id: str,
    files: List[UploadFile] = File(..., description="PDF answer sheet files"),
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Upload student answer sheet PDFs.
    
    Multiple files can be uploaded at once.
    Each PDF should be a single student's answer sheet.
    """
    supabase = get_supabase_client()
    
    # Check exam exists
    exam_result = supabase.table("exams").select("*").eq("exam_id", exam_id).execute()
    if not exam_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam '{exam_id}' not found"
        )
    
    uploaded_sheets = []
    
    for file in files:
        # Validate file type
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            continue
        
        try:
            # Upload to storage
            file_path = await upload_pdf(exam_id, file)
            
            # Create database record
            result = supabase.table("answer_sheets").insert({
                "exam_id": exam_id,
                "file_path": file_path,
                "file_name": file.filename,
                "processed": False
            }).execute()
            
            if result.data:
                uploaded_sheets.append(AnswerSheetResponse(**result.data[0]))
                
        except Exception as e:
            # Log error but continue with other files
            print(f"Error uploading {file.filename}: {e}")
            continue
    
    if not uploaded_sheets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid PDF files were uploaded"
        )
    
    return uploaded_sheets


@router.get("", response_model=list[AnswerSheetResponse])
async def list_answer_sheets(
    exam_id: str,
    processed_only: bool = False,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    List all uploaded answer sheets for an exam.
    """
    supabase = get_supabase_client()
    
    query = supabase.table("answer_sheets").select("*").eq("exam_id", exam_id)
    
    if processed_only:
        query = query.eq("processed", True)
    
    result = query.order("uploaded_at", desc=True).execute()
    
    return [AnswerSheetResponse(**sheet) for sheet in result.data]


@router.get("/{sheet_id}", response_model=AnswerSheetResponse)
async def get_answer_sheet(
    exam_id: str,
    sheet_id: str,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Get details of a specific answer sheet.
    """
    supabase = get_supabase_client()
    
    result = supabase.table("answer_sheets").select("*").eq("id", sheet_id).eq("exam_id", exam_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer sheet not found"
        )
    
    return AnswerSheetResponse(**result.data[0])


@router.get("/{sheet_id}/url")
async def get_answer_sheet_url(
    exam_id: str,
    sheet_id: str,
    user: UserProfile = Depends(require_role(UserRole.PROF, UserRole.ADMIN))
):
    """
    Get a signed URL to view/download an answer sheet.
    """
    supabase = get_supabase_client()
    
    result = supabase.table("answer_sheets").select("file_path").eq("id", sheet_id).eq("exam_id", exam_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer sheet not found"
        )
    
    url = get_pdf_url(result.data[0]["file_path"])
    
    return {"url": url, "expires_in_seconds": 3600}


@router.delete("/{sheet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_answer_sheet(
    exam_id: str,
    sheet_id: str,
    user: UserProfile = Depends(require_role(UserRole.ADMIN))
):
    """
    Delete an answer sheet.
    
    Only admins can delete answer sheets.
    """
    supabase = get_supabase_client()
    
    # Check exists
    existing = supabase.table("answer_sheets").select("*").eq("id", sheet_id).eq("exam_id", exam_id).execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer sheet not found"
        )
    
    # Delete from storage and database
    from storage import delete_pdf
    delete_pdf(existing.data[0]["file_path"])
    
    supabase.table("answer_sheets").delete().eq("id", sheet_id).execute()
