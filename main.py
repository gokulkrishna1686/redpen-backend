"""
FastAPI Application Entry Point - Exam Grading System

This is the main application that brings together all routes and middleware.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings

# Import routers
from routes.exams import router as exams_router
from routes.answer_keys import router as answer_keys_router
from routes.answer_sheets import router as answer_sheets_router
from routes.students import router as students_router
from routes.evaluation import router as evaluation_router
from routes.results import router as results_router


# Initialize settings
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="""
    Automated Exam Grading System powered by Google Gemini AI.
    
    ## Features
    - **Exam Management**: Create and manage exams with rubric-based answer keys
    - **PDF Upload**: Upload handwritten student answer sheets as PDFs
    - **AI Grading**: Automatic grading using Gemini 2.5 Pro for handwriting recognition
    - **Async Processing**: Background evaluation with progress tracking
    - **Results Management**: View, update, and export grading results
    - **Professor Review**: Handle illegible answers with manual override
    
    ## Authentication
    All endpoints require a valid Supabase JWT token. Include it in the Authorization header:
    ```
    Authorization: Bearer <your-jwt-token>
    ```
    
    ## Roles
    - **student**: Can view their own exam results
    - **prof**: Can create exams, upload answer sheets, and grade
    - **admin**: Full access including deletion operations
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware - adjust origins for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers with API prefix
API_PREFIX = "/api/v1"

app.include_router(exams_router, prefix=API_PREFIX)
app.include_router(answer_keys_router, prefix=API_PREFIX)
app.include_router(answer_sheets_router, prefix=API_PREFIX)
app.include_router(students_router, prefix=API_PREFIX)
app.include_router(evaluation_router, prefix=API_PREFIX)
app.include_router(results_router, prefix=API_PREFIX)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint - API information."""
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# Run with: uvicorn main:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
