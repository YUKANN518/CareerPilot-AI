from fastapi import APIRouter

from app.api import (
    admin_knowledge_documents,
    applications,
    auth,
    career_assistant,
    dashboard,
    health,
    interviews,
    jobs,
    match_runs,
    matches,
    resume_optimizations,
    resumes,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(admin_knowledge_documents.router)
api_router.include_router(resumes.router)
api_router.include_router(resumes.version_router)
api_router.include_router(jobs.router)
api_router.include_router(applications.router)
api_router.include_router(matches.router)
api_router.include_router(match_runs.router)
api_router.include_router(resume_optimizations.router)
api_router.include_router(interviews.router)
api_router.include_router(career_assistant.router)
