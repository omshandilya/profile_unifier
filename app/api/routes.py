from fastapi import APIRouter
from app.models.schemas import ProfileResolveRequest, ProfileResolveResponse, HealthResponse
from app.observability.metrics import metrics_tracker
from app.config import settings

router = APIRouter()

@router.post("/profiles/resolve", response_model=ProfileResolveResponse)
async def resolve_profile(request: ProfileResolveRequest):
    metrics_tracker.increment("resolve_requests")
    # Placeholder implementation
    return {
        "profile_id": "placeholder-id",
        "unified_name": "Placeholder Name",
        "bio": "This is a placeholder bio.",
        "emails": ["placeholder@example.com"],
        "github_data": {"username": request.github_username} if request.github_username else None,
        "stackoverflow_data": {"user_id": request.stackoverflow_user_id} if request.stackoverflow_user_id else None,
        "devto_data": {"username": request.devto_username} if request.devto_username else None,
        "hackernews_data": {"username": request.hackernews_username} if request.hackernews_username else None,
        "resolved_at": "2026-06-26T17:27:27Z"
    }

@router.get("/profiles/{profile_id}", response_model=ProfileResolveResponse)
async def get_profile(profile_id: str):
    metrics_tracker.increment("profile_lookups")
    # Placeholder implementation
    return {
        "profile_id": profile_id,
        "unified_name": "Placeholder Name",
        "bio": "This is a placeholder bio.",
        "emails": ["placeholder@example.com"],
        "github_data": None,
        "stackoverflow_data": None,
        "devto_data": None,
        "hackernews_data": None,
        "resolved_at": "2026-06-26T17:27:27Z"
    }

@router.get("/health", response_model=HealthResponse)
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "uptime_metrics": metrics_tracker.get_metrics()
    }
