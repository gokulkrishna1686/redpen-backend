"""
Background evaluation worker for async exam grading.
"""
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from supabase_client import get_supabase_client
from storage import download_pdf
from gemini_client import evaluate_full_answer_sheet
from schemas import Question, QuestionBreakdown


# Thread pool for background processing
executor = ThreadPoolExecutor(max_workers=3)

# Track running jobs
running_jobs: dict[str, asyncio.Task] = {}


async def start_evaluation(exam_id: str) -> str:
    """
    Start a background evaluation job for an exam.
    
    Args:
        exam_id: The exam ID to evaluate
        
    Returns:
        The job ID
    """
    supabase = get_supabase_client()
    
    # Check if exam exists and has answer key
    exam_result = supabase.table("exams").select("*").eq("exam_id", exam_id).execute()
    if not exam_result.data:
        raise ValueError(f"Exam {exam_id} not found")
    
    answer_key_result = supabase.table("answer_keys").select("*").eq("exam_id", exam_id).execute()
    if not answer_key_result.data:
        raise ValueError(f"Answer key not found for exam {exam_id}")
    
    # Get count of answer sheets
    sheets_result = supabase.table("answer_sheets").select("id").eq("exam_id", exam_id).execute()
    total_sheets = len(sheets_result.data)
    
    if total_sheets == 0:
        raise ValueError(f"No answer sheets uploaded for exam {exam_id}")
    
    # Create evaluation job record
    job_result = supabase.table("evaluation_jobs").insert({
        "exam_id": exam_id,
        "status": "pending",
        "total_sheets": total_sheets,
        "processed_sheets": 0
    }).execute()
    
    job_id = job_result.data[0]["id"]
    
    # Update exam status
    supabase.table("exams").update({"status": "evaluating"}).eq("exam_id", exam_id).execute()
    
    # Start background task
    task = asyncio.create_task(process_evaluation(job_id, exam_id))
    running_jobs[job_id] = task
    
    return job_id


async def process_evaluation(job_id: str, exam_id: str):
    """
    Process evaluation for all answer sheets in an exam.
    
    Args:
        job_id: The evaluation job ID
        exam_id: The exam ID
    """
    supabase = get_supabase_client()
    
    try:
        # Update job status to in_progress
        supabase.table("evaluation_jobs").update({
            "status": "in_progress",
            "started_at": datetime.utcnow().isoformat()
        }).eq("id", job_id).execute()
        
        # Fetch answer key
        answer_key_result = supabase.table("answer_keys").select("questions").eq("exam_id", exam_id).execute()
        questions_data = answer_key_result.data[0]["questions"]
        questions = [Question(**q) for q in questions_data]
        
        # Fetch all unprocessed answer sheets
        sheets_result = supabase.table("answer_sheets").select("*").eq("exam_id", exam_id).eq("processed", False).execute()
        
        processed_count = 0
        
        for sheet in sheets_result.data:
            try:
                # Download PDF
                pdf_bytes = download_pdf(sheet["file_path"])
                
                # Evaluate with Gemini
                student_id, breakdown = await evaluate_full_answer_sheet(pdf_bytes, questions)
                
                # Use extracted student ID or fallback to sheet ID
                if not student_id:
                    student_id = f"UNKNOWN_{sheet['id'][:8]}"
                
                # Calculate totals
                total_marks = 0.0
                max_marks = 0.0
                has_illegible = False
                
                breakdown_dict = {}
                for qid, result in breakdown.items():
                    breakdown_dict[qid] = result.model_dump()
                    max_marks += result.max
                    if result.illegible:
                        has_illegible = True
                    elif result.awarded is not None:
                        total_marks += result.awarded
                
                # Save result to database
                supabase.table("results").upsert({
                    "exam_id": exam_id,
                    "student_id": student_id,
                    "total_marks": total_marks,
                    "max_marks": max_marks,
                    "breakdown": breakdown_dict,
                    "has_illegible": has_illegible,
                    "reviewed": False
                }, on_conflict="exam_id,student_id").execute()
                
                # Create illegible flags if needed
                if has_illegible:
                    # Get the result ID
                    result_data = supabase.table("results").select("id").eq("exam_id", exam_id).eq("student_id", student_id).execute()
                    result_id = result_data.data[0]["id"]
                    
                    for qid, result in breakdown.items():
                        if result.illegible:
                            supabase.table("illegible_flags").insert({
                                "result_id": result_id,
                                "exam_id": exam_id,
                                "student_id": student_id,
                                "question_id": qid,
                                "original_answer_path": sheet["file_path"]
                            }).execute()
                
                # Update answer sheet with student ID and mark as processed
                supabase.table("answer_sheets").update({
                    "student_id": student_id,
                    "processed": True
                }).eq("id", sheet["id"]).execute()
                
                processed_count += 1
                
                # Update job progress
                supabase.table("evaluation_jobs").update({
                    "processed_sheets": processed_count
                }).eq("id", job_id).execute()
                
            except Exception as e:
                print(f"Error processing sheet {sheet['id']}: {e}")
                # Continue with next sheet
                continue
        
        # Mark job as completed
        supabase.table("evaluation_jobs").update({
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat()
        }).eq("id", job_id).execute()
        
        # Update exam status
        supabase.table("exams").update({"status": "completed"}).eq("exam_id", exam_id).execute()
        
    except Exception as e:
        # Mark job as failed
        supabase.table("evaluation_jobs").update({
            "status": "failed",
            "error_message": str(e),
            "completed_at": datetime.utcnow().isoformat()
        }).eq("id", job_id).execute()
        
        # Revert exam status
        supabase.table("exams").update({"status": "ready"}).eq("exam_id", exam_id).execute()
        
        raise
    finally:
        # Remove from running jobs
        if job_id in running_jobs:
            del running_jobs[job_id]


def get_job_status(job_id: str) -> Optional[dict]:
    """
    Get the status of an evaluation job.
    
    Args:
        job_id: The job ID
        
    Returns:
        Job status dict or None if not found
    """
    supabase = get_supabase_client()
    result = supabase.table("evaluation_jobs").select("*").eq("id", job_id).execute()
    
    if result.data:
        return result.data[0]
    return None


def get_exam_job_status(exam_id: str) -> Optional[dict]:
    """
    Get the latest evaluation job for an exam.
    
    Args:
        exam_id: The exam ID
        
    Returns:
        Job status dict or None if not found
    """
    supabase = get_supabase_client()
    result = supabase.table("evaluation_jobs").select("*").eq("exam_id", exam_id).order("created_at", desc=True).limit(1).execute()
    
    if result.data:
        return result.data[0]
    return None
