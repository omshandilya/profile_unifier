from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class ProfileResolveRequest(BaseModel):
    github_username: Optional[str] = None
    stackoverflow_user_id: Optional[str] = None
    devto_username: Optional[str] = None
    hackernews_username: Optional[str] = None

class ProfileResolveResponse(BaseModel):
    profile_id: str
    unified_name: str
    bio: Optional[str] = None
    emails: List[str] = []
    github_data: Optional[Dict[str, Any]] = None
    stackoverflow_data: Optional[Dict[str, Any]] = None
    devto_data: Optional[Dict[str, Any]] = None
    hackernews_data: Optional[Dict[str, Any]] = None
    resolved_at: str

class HealthResponse(BaseModel):
    status: str
    environment: str
    uptime_metrics: Dict[str, Any]
