"""
Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# ============== ENUMS ==============

class UserRole(str, Enum):
    STUDENT = "student"
    PROF = "prof"
    ADMIN = "admin"


class ExamStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    EVALUATING = "evaluating"
    COMPLETED = "completed"


class EvaluationJobStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# ============== ANSWER KEY SCHEMAS ==============

class RubricItem(BaseModel):
    """A single rubric point with marks."""
    point: str = Field(..., description="Description of what to look for")
    marks: float = Field(..., ge=0, description="Marks for this rubric point")


class Question(BaseModel):
    """A question in the answer key."""
    qid: str = Field(..., description="Question ID like Q1, Q2")
    max_marks: float = Field(..., ge=0, description="Maximum marks for this question")
    rubric: list[RubricItem] = Field(..., description="List of rubric points")
    keywords: list[str] = Field(default=[], description="Keywords to look for in answers")


class AnswerKeyCreate(BaseModel):
    """Request schema for creating an answer key."""
    questions: list[Question] = Field(..., description="List of questions with rubrics")


class AnswerKeyResponse(BaseModel):
    """Response schema for answer key."""
    id: str
    exam_id: str
    questions: list[Question]
    created_at: datetime
    updated_at: datetime


# ============== EXAM SCHEMAS ==============

class ExamCreate(BaseModel):
    """Request schema for creating an exam."""
    exam_id: str = Field(..., description="Human-readable exam ID like CS101_MIDSEM")
    name: str = Field(..., description="Exam name")
    description: Optional[str] = Field(None, description="Optional description")


class ExamResponse(BaseModel):
    """Response schema for an exam."""
    id: str
    exam_id: str
    name: str
    description: Optional[str]
    created_by: Optional[str]
    status: ExamStatus
    created_at: datetime
    updated_at: datetime


class ExamUpdate(BaseModel):
    """Request schema for updating an exam."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ExamStatus] = None


# ============== ANSWER SHEET SCHEMAS ==============

class AnswerSheetResponse(BaseModel):
    """Response schema for an uploaded answer sheet."""
    id: str
    exam_id: str
    student_id: Optional[str]
    file_path: str
    file_name: str
    uploaded_at: datetime
    processed: bool


# ============== STUDENT SCHEMAS ==============

class StudentResponse(BaseModel):
    """Response schema for a student in an exam."""
    student_id: str
    exam_id: str
    file_name: str
    processed: bool


class StudentUpdate(BaseModel):
    """Request schema for updating student info."""
    student_id: Optional[str] = None


# ============== EVALUATION SCHEMAS ==============

class EvaluationJobResponse(BaseModel):
    """Response schema for evaluation job status."""
    id: str
    exam_id: str
    status: EvaluationJobStatus
    total_sheets: int
    processed_sheets: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime


class EvaluationStartResponse(BaseModel):
    """Response when starting an evaluation."""
    message: str
    job_id: str
    status: EvaluationJobStatus


# ============== RESULT SCHEMAS ==============

class QuestionBreakdown(BaseModel):
    """Breakdown of marks for a single question."""
    awarded: Optional[float] = Field(None, description="Marks awarded, null if illegible")
    max: float = Field(..., description="Maximum marks")
    justification: str = Field(..., description="Explanation of grading")
    confidence: float = Field(..., ge=0, le=1, description="AI confidence score")
    illegible: bool = Field(default=False, description="Whether answer was illegible")


class ResultResponse(BaseModel):
    """Response schema for a student's result."""
    id: str
    exam_id: str
    student_id: str
    total_marks: Optional[float]
    max_marks: Optional[float]
    breakdown: dict[str, QuestionBreakdown]
    has_illegible: bool
    reviewed: bool
    created_at: datetime
    updated_at: datetime


class ResultUpdate(BaseModel):
    """Request schema for updating a result (professor override)."""
    breakdown: Optional[dict[str, QuestionBreakdown]] = None
    reviewed: Optional[bool] = None


class ResultsSummary(BaseModel):
    """Summary of all results for an exam."""
    exam_id: str
    total_students: int
    evaluated_students: int
    pending_review: int
    average_marks: Optional[float]
    results: list[ResultResponse]


# ============== ILLEGIBLE FLAG SCHEMAS ==============

class IllegalFlagResponse(BaseModel):
    """Response for an illegible answer flag."""
    id: str
    result_id: str
    exam_id: str
    student_id: str
    question_id: str
    original_answer_path: Optional[str]
    resolved: bool
    resolved_by: Optional[str]
    resolved_marks: Optional[float]
    resolved_at: Optional[datetime]
    created_at: datetime


class IllegalFlagResolve(BaseModel):
    """Request schema for resolving an illegible flag."""
    marks: float = Field(..., ge=0, description="Marks to award")


# ============== AUTH SCHEMAS ==============

class UserProfile(BaseModel):
    """User profile from Supabase auth."""
    id: str
    email: Optional[str]
    full_name: Optional[str]
    role: UserRole
    student_id: Optional[str]


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # User ID
    email: Optional[str]
    role: Optional[str]
    exp: int
