"""
Gemini AI client for handwriting recognition and exam grading.
Uses the new google-genai package.
"""
from google import genai
from google.genai import types
import json
import re
from typing import Optional

from config import get_settings
from schemas import Question, QuestionBreakdown


# Initialize Gemini client
settings = get_settings()
client = genai.Client(api_key=settings.GOOGLE_API_KEY)


async def extract_student_id(pdf_bytes: bytes) -> Optional[str]:
    """
    Extract the student ID from the top of a handwritten answer sheet.
    
    Args:
        pdf_bytes: The PDF file content as bytes
        
    Returns:
        Extracted student ID or None if not found
    """
    prompt = """Analyze this handwritten exam answer sheet. 
Your task is to find and extract the STUDENT ID (also called Roll Number, Registration Number, or similar).

The student ID is typically:
- Written at the TOP of the first page
- In a designated field/box
- Could be in format like: 21CS045, 2021BCS0123, ABC123, etc.

Return ONLY the student ID as plain text, nothing else.
If you cannot find or read the student ID clearly, return exactly: UNKNOWN

Example valid responses:
21CS045
2021BCS0123
UNKNOWN"""

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(
                        category="HARM_CATEGORY_HARASSMENT",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_HATE_SPEECH",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_DANGEROUS_CONTENT",
                        threshold="BLOCK_NONE"
                    ),
                ]
            )
        )
        
        student_id = response.text.strip()
        
        # Validate - should be alphanumeric, not too long
        if student_id and student_id != "UNKNOWN" and len(student_id) <= 20:
            # Clean up any extra whitespace or newlines
            student_id = re.sub(r'\s+', '', student_id)
            return student_id
        
        return None
        
    except Exception as e:
        print(f"Error extracting student ID: {e}")
        return None


async def evaluate_answer(
    pdf_bytes: bytes,
    question: Question,
    question_number: int = 1
) -> QuestionBreakdown:
    """
    Evaluate a student's handwritten answer against the rubric.
    
    Args:
        pdf_bytes: The PDF file content as bytes
        question: The question with rubric and keywords
        question_number: Position of the question (for context)
        
    Returns:
        QuestionBreakdown with marks, justification, and confidence
    """
    # Build rubric description
    rubric_text = "\n".join([
        f"  - {item.point}: {item.marks} marks"
        for item in question.rubric
    ])
    
    keywords_text = ", ".join(question.keywords) if question.keywords else "None specified"
    
    prompt = f"""You are an expert exam grader. Analyze the handwritten answer sheet and grade Question {question.qid}.

## Question Details:
- Question ID: {question.qid}
- Maximum Marks: {question.max_marks}

## Grading Rubric:
{rubric_text}

## Keywords to look for: {keywords_text}

## Instructions:
1. Locate the answer for Question {question.qid} in the PDF
2. Read and interpret the handwritten answer carefully
3. Compare against each rubric point and award partial marks as appropriate
4. Consider keywords as positive indicators but don't require exact matches

## Special Cases:
- If the answer section is BLANK or empty: Award 0 marks, set "illegible": false
- If the handwriting is ILLEGIBLE (cannot read): Set "illegible": true, "awarded": null
- For partial answers: Award proportional marks based on rubric coverage

## Required JSON Response Format:
{{
  "awarded": <number or null if illegible>,
  "max": {question.max_marks},
  "justification": "<detailed explanation of grading decision>",
  "confidence": <0.0 to 1.0 - your confidence in this grading>,
  "illegible": <true if cannot read, false otherwise>
}}

IMPORTANT: Return ONLY valid JSON, no markdown formatting or explanations outside the JSON."""

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(
                        category="HARM_CATEGORY_HARASSMENT",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_HATE_SPEECH",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        threshold="BLOCK_NONE"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_DANGEROUS_CONTENT",
                        threshold="BLOCK_NONE"
                    ),
                ]
            )
        )
        
        # Parse the JSON response
        response_text = response.text.strip()
        
        # Handle markdown code blocks if present
        if response_text.startswith("```"):
            response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)
        
        result = json.loads(response_text)
        
        return QuestionBreakdown(
            awarded=result.get("awarded"),
            max=result.get("max", question.max_marks),
            justification=result.get("justification", "Grading completed"),
            confidence=min(1.0, max(0.0, result.get("confidence", 0.5))),
            illegible=result.get("illegible", False)
        )
        
    except json.JSONDecodeError as e:
        # If JSON parsing fails, return a safe default
        return QuestionBreakdown(
            awarded=None,
            max=question.max_marks,
            justification=f"Error parsing AI response: {str(e)}",
            confidence=0.0,
            illegible=True
        )
    except Exception as e:
        return QuestionBreakdown(
            awarded=None,
            max=question.max_marks,
            justification=f"Error during evaluation: {str(e)}",
            confidence=0.0,
            illegible=True
        )


async def evaluate_full_answer_sheet(
    pdf_bytes: bytes,
    questions: list[Question]
) -> tuple[Optional[str], dict[str, QuestionBreakdown]]:
    """
    Evaluate an entire answer sheet against all questions.
    
    Args:
        pdf_bytes: The PDF file content as bytes
        questions: List of questions with rubrics
        
    Returns:
        Tuple of (student_id, breakdown dict)
    """
    # First extract student ID
    student_id = await extract_student_id(pdf_bytes)
    
    # Then evaluate each question
    breakdown = {}
    for i, question in enumerate(questions, 1):
        result = await evaluate_answer(pdf_bytes, question, i)
        breakdown[question.qid] = result
    
    return student_id, breakdown
