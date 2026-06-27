import asyncio
import logging
from typing import Optional

from google import genai
from google.genai import types

from app.config import settings
from app.observability.metrics import metrics

logger = logging.getLogger("effiflo-dev-unifier")

_PRIMARY_MODEL = "gemini-2.0-flash"
_FALLBACK_MODEL = "gemini-1.5-flash"


class GeminiEnricher:
    """
    Wraps the google-genai SDK to produce a concise developer bio paragraph
    from a resolved canonical profile dict.
    """

    def __init__(self):
        self.api_key: Optional[str] = settings.GEMINI_API_KEY
        # Instantiate the client once; all calls share it.
        self._client: Optional[genai.Client] = None
        if self.api_key:
            self._client = genai.Client(api_key=self.api_key)

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_prompt(self, profile: dict) -> str:
        name = profile.get("display_name") or "Unknown Developer"
        location = profile.get("location") or "Unknown location"
        bio = profile.get("bio") or ""

        # Top 5 languages by byte count
        raw_langs: dict = profile.get("merged_languages") or {}
        top_langs = sorted(raw_langs.items(), key=lambda x: x[1], reverse=True)[:5]
        langs_str = (
            ", ".join(f"{lang} ({count:,} bytes)" for lang, count in top_langs)
            or "N/A"
        )

        # Top 8 tags
        all_tags = profile.get("merged_tags") or []
        if isinstance(all_tags, list):
            top_tags = [str(t) for t in all_tags[:8]]
        else:
            top_tags = list(str(t) for t in list(all_tags)[:8])
        tags_str = ", ".join(top_tags) or "N/A"

        # Platform stats
        gh_repos: int = profile.get("github_repo_count") or 0
        so_rep: int = profile.get("stackoverflow_reputation") or 0
        devto_articles: int = profile.get("devto_article_count") or 0

        # Recent activity
        last_commit = profile.get("last_commit_date") or "N/A"
        recent_articles: list = profile.get("recent_article_titles") or []
        recent_articles_str = "; ".join(str(t) for t in recent_articles[:3]) or "N/A"

        return (
            "You are writing a professional developer profile summary.\n\n"
            "Developer information:\n"
            f"- Name: {name}\n"
            f"- Location: {location}\n"
            f"- Bio: {bio if bio else 'Not provided'}\n"
            f"- Top languages (by code volume): {langs_str}\n"
            f"- Key topics & tags: {tags_str}\n"
            f"- GitHub repositories: {gh_repos}\n"
            f"- Stack Overflow reputation: {so_rep}\n"
            f"- dev.to articles published: {devto_articles}\n"
            f"- Last commit date: {last_commit}\n"
            f"- Recent article titles: {recent_articles_str}\n\n"
            "Write a single paragraph of 4–6 sentences summarising this developer's "
            "skills, primary focus areas, and recent activity. Be specific. "
            "Do not use bullet points. Do not start with \"This developer\". "
            "Write in third person."
        )

    # ------------------------------------------------------------------
    # Internal: sync call wrapped in executor
    # ------------------------------------------------------------------

    async def _call_model(self, prompt: str, model_name: str) -> dict:
        client = self._client

        def _sync_call():
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=300,
                    temperature=0.6,
                ),
            )
            return response

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _sync_call)

        # Token count
        try:
            tokens_used = response.usage_metadata.total_token_count
        except AttributeError:
            tokens_used = 0

        # Text extraction
        try:
            summary_text = response.text.strip()
        except (AttributeError, ValueError):
            summary_text = "Summary unavailable."

        return {"summary": summary_text, "tokens_used": tokens_used, "model": model_name}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_summary(self, canonical_profile: dict) -> dict:
        """
        Generate a Gemini developer summary for a canonical profile dict.

        Returns:
            {"summary": str, "tokens_used": int, "model": str}
        """
        name = canonical_profile.get("display_name") or "Unknown"

        if not self._client:
            logger.warning("GEMINI_API_KEY not set — returning placeholder summary.")
            return {"summary": "Summary unavailable.", "tokens_used": 0, "model": ""}

        prompt = self._build_prompt(canonical_profile)

        for model_name in [_PRIMARY_MODEL, _FALLBACK_MODEL]:
            try:
                result = await self._call_model(prompt, model_name)
                tokens = result["tokens_used"]
                logger.info(f"→ Gemini summary for {name}, tokens used: {tokens}")
                metrics.record_llm_usage(tokens)
                return result
            except Exception as exc:
                logger.warning(
                    f"Gemini model '{model_name}' failed for '{name}': {exc}. "
                    f"{'Trying fallback...' if model_name == _PRIMARY_MODEL else 'Giving up.'}"
                )

        return {"summary": "Summary unavailable.", "tokens_used": 0, "model": ""}
