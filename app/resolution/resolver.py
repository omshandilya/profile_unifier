from typing import Dict, Any, Optional
import uuid
from datetime import datetime, timezone

class EntityResolver:
    @staticmethod
    def resolve_profiles(
        github: Optional[Dict[str, Any]],
        stackoverflow: Optional[Dict[str, Any]],
        devto: Optional[Dict[str, Any]],
        hackernews: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge profiles from different platforms into a unified profile.
        """
        # Determine a unified name
        unified_name = "Anonymous Developer"
        bio = None
        emails = []

        if github:
            unified_name = github.get("name") or github.get("login") or unified_name
            bio = github.get("bio") or bio
            if github.get("email"):
                emails.append(github.get("email"))
        if stackoverflow:
            unified_name = stackoverflow.get("display_name") or unified_name
            bio = stackoverflow.get("about_me") or bio
        if devto:
            unified_name = devto.get("name") or unified_name
            bio = devto.get("summary") or bio
        
        # Uniqify emails
        emails = list(set([e for e in emails if e]))

        return {
            "profile_id": str(uuid.uuid4()),
            "unified_name": unified_name,
            "bio": bio,
            "emails": emails,
            "github_data": github,
            "stackoverflow_data": stackoverflow,
            "devto_data": devto,
            "hackernews_data": hackernews,
            "resolved_at": datetime.now(timezone.utc).isoformat()
        }
