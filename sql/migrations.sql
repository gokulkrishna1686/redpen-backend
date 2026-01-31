-- =============================================
-- EXAM GRADING SYSTEM - SUPABASE SCHEMA
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New Query)
-- =============================================

-- 1. PROFILES TABLE (extends Supabase auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT,
    full_name TEXT,
    role TEXT NOT NULL CHECK (role IN ('student', 'prof', 'admin')) DEFAULT 'student',
    student_id TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. EXAMS TABLE
CREATE TABLE IF NOT EXISTS public.exams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_by UUID REFERENCES public.profiles(id),
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'ready', 'evaluating', 'completed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. ANSWER KEYS TABLE
CREATE TABLE IF NOT EXISTS public.answer_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id TEXT REFERENCES public.exams(exam_id) ON DELETE CASCADE,
    questions JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(exam_id)
);

-- 4. ANSWER SHEETS TABLE
CREATE TABLE IF NOT EXISTS public.answer_sheets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id TEXT REFERENCES public.exams(exam_id) ON DELETE CASCADE,
    student_id TEXT,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE
);

-- 5. EVALUATION JOBS TABLE
CREATE TABLE IF NOT EXISTS public.evaluation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id TEXT REFERENCES public.exams(exam_id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'failed')),
    total_sheets INTEGER DEFAULT 0,
    processed_sheets INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. RESULTS TABLE
CREATE TABLE IF NOT EXISTS public.results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id TEXT REFERENCES public.exams(exam_id) ON DELETE CASCADE,
    student_id TEXT NOT NULL,
    total_marks DECIMAL(5,2),
    max_marks DECIMAL(5,2),
    breakdown JSONB NOT NULL,
    has_illegible BOOLEAN DEFAULT FALSE,
    reviewed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(exam_id, student_id)
);

-- 7. ILLEGIBLE FLAGS TABLE
CREATE TABLE IF NOT EXISTS public.illegible_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id UUID REFERENCES public.results(id) ON DELETE CASCADE,
    exam_id TEXT REFERENCES public.exams(exam_id) ON DELETE CASCADE,
    student_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    original_answer_path TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_by UUID REFERENCES public.profiles(id),
    resolved_marks DECIMAL(5,2),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- ENABLE ROW LEVEL SECURITY
-- =============================================

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exams ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.answer_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.answer_sheets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evaluation_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.illegible_flags ENABLE ROW LEVEL SECURITY;

-- =============================================
-- RLS POLICIES
-- =============================================

-- Profiles policies
CREATE POLICY "Users can view own profile" ON public.profiles 
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Admins and profs can view all profiles" ON public.profiles 
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('admin', 'prof'))
    );

-- Exam policies
CREATE POLICY "Profs and admins can manage exams" ON public.exams 
    FOR ALL USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('admin', 'prof'))
    );

CREATE POLICY "Students can view exams" ON public.exams 
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'student')
    );

-- Results policies
CREATE POLICY "Students can view own results" ON public.results 
    FOR SELECT USING (
        student_id = (SELECT student_id FROM public.profiles WHERE id = auth.uid())
    );

CREATE POLICY "Profs and admins can manage results" ON public.results 
    FOR ALL USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('admin', 'prof'))
    );

-- =============================================
-- SERVICE ROLE BYPASS POLICIES (for backend)
-- =============================================

CREATE POLICY "Service role full access profiles" ON public.profiles 
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access answer_keys" ON public.answer_keys 
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access answer_sheets" ON public.answer_sheets 
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access evaluation_jobs" ON public.evaluation_jobs 
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access illegible_flags" ON public.illegible_flags 
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

-- =============================================
-- TRIGGERS
-- =============================================

-- Auto-create profile on user signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, role)
    VALUES (
        NEW.id, 
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', ''),
        COALESCE(NEW.raw_user_meta_data->>'role', 'student')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Drop trigger if exists and recreate
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_exams_updated_at ON public.exams;
CREATE TRIGGER update_exams_updated_at 
    BEFORE UPDATE ON public.exams 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_results_updated_at ON public.results;
CREATE TRIGGER update_results_updated_at 
    BEFORE UPDATE ON public.results 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_answer_keys_updated_at ON public.answer_keys;
CREATE TRIGGER update_answer_keys_updated_at 
    BEFORE UPDATE ON public.answer_keys 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================
-- INDEXES FOR PERFORMANCE
-- =============================================

CREATE INDEX IF NOT EXISTS idx_answer_sheets_exam_id ON public.answer_sheets(exam_id);
CREATE INDEX IF NOT EXISTS idx_answer_sheets_student_id ON public.answer_sheets(student_id);
CREATE INDEX IF NOT EXISTS idx_results_exam_id ON public.results(exam_id);
CREATE INDEX IF NOT EXISTS idx_results_student_id ON public.results(student_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_exam_id ON public.evaluation_jobs(exam_id);
CREATE INDEX IF NOT EXISTS idx_illegible_flags_exam_id ON public.illegible_flags(exam_id);
