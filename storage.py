"""
Supabase storage operations for PDF file management.
"""
from fastapi import UploadFile, HTTPException, status
from typing import Optional
import uuid

from supabase_client import get_supabase_client
from config import get_settings


async def upload_pdf(
    exam_id: str,
    file: UploadFile,
    custom_filename: Optional[str] = None
) -> str:
    """
    Upload a PDF file to Supabase storage.
    
    Args:
        exam_id: The exam ID to organize files under
        file: The uploaded file
        custom_filename: Optional custom filename, otherwise uses original
        
    Returns:
        The storage path of the uploaded file
    """
    settings = get_settings()
    supabase = get_supabase_client()
    
    # Validate file type
    if not file.content_type or "pdf" not in file.content_type.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed"
        )
    
    # Generate unique filename to avoid collisions
    original_name = file.filename or "answer_sheet.pdf"
    unique_id = str(uuid.uuid4())[:8]
    filename = custom_filename or f"{unique_id}_{original_name}"
    
    # Storage path: exam_id/filename
    file_path = f"{exam_id}/{filename}"
    
    # Read file content
    content = await file.read()
    
    # Upload to Supabase storage
    try:
        result = supabase.storage.from_(settings.STORAGE_BUCKET).upload(
            path=file_path,
            file=content,
            file_options={"content-type": "application/pdf"}
        )
        return file_path
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )


def get_pdf_url(file_path: str, expires_in: int = 3600) -> str:
    """
    Get a signed URL for a PDF file.
    
    Args:
        file_path: The storage path of the file
        expires_in: URL expiration time in seconds (default 1 hour)
        
    Returns:
        Signed URL for the file
    """
    settings = get_settings()
    supabase = get_supabase_client()
    
    try:
        result = supabase.storage.from_(settings.STORAGE_BUCKET).create_signed_url(
            path=file_path,
            expires_in=expires_in
        )
        return result["signedURL"]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to get file URL: {str(e)}"
        )


def download_pdf(file_path: str) -> bytes:
    """
    Download a PDF file from storage.
    
    Args:
        file_path: The storage path of the file
        
    Returns:
        File content as bytes
    """
    settings = get_settings()
    supabase = get_supabase_client()
    
    try:
        result = supabase.storage.from_(settings.STORAGE_BUCKET).download(file_path)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to download file: {str(e)}"
        )


def list_pdfs(exam_id: str) -> list[dict]:
    """
    List all PDF files for an exam.
    
    Args:
        exam_id: The exam ID
        
    Returns:
        List of file metadata
    """
    settings = get_settings()
    supabase = get_supabase_client()
    
    try:
        result = supabase.storage.from_(settings.STORAGE_BUCKET).list(exam_id)
        return result
    except Exception as e:
        return []


def delete_pdf(file_path: str) -> bool:
    """
    Delete a PDF file from storage.
    
    Args:
        file_path: The storage path of the file
        
    Returns:
        True if deleted successfully
    """
    settings = get_settings()
    supabase = get_supabase_client()
    
    try:
        supabase.storage.from_(settings.STORAGE_BUCKET).remove([file_path])
        return True
    except Exception as e:
        return False
