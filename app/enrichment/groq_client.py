import asyncio
import logging
from typing import Optional
import httpx
from app.config import settings
from app.observability.metrics import metrics

logger = logging.getLogger("effiflo-dev-unifier")

_PRIMARY_MODEL = "llama-3.3-70b-versatile"
_FALLBACK_MODEL = "mixtral-8x7b-32768"


class GroqEnricher:
    """
    Wraps the Groq Cloud REST completions API to produce a concise developer bio
    paragraph from a resolved canonical profile dict.
    """

    def __init__(self):
        self.api_key: Optional[str] = settings.groq_api_key
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    def _build_prompt(self, profile: dict) -> str:
        name = profile.get("display_name") or "Unknown Developer"
        location = profile.get("location") or "Unknown location"
        bio = profile.get("bio") or ""

        # Top 5 languages
        raw_langs: dict = profile.get("merged_languages") or {}
        top_langs = sorted(raw_langs.items(), key=lambda x: x[1], reverse=True)[:5]
        langs_str = ", ".join(f"{lang} ({count:,} bytes)" for lang, count in top_langs) or "N/A"

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

    async def _call_model(self, prompt: str, model_name: str) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 300,
            "temperature": 0.6,
        }

        async with httpx.AsyncClient() as client:
            res = await client.post(self.base_url, headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
            data = res.json()

        # Extract text
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("No choices returned from Groq completions.")
        text = choices[0].get("message", {}).get("content", "").strip()

        # Extract token usage
        usage = data.get("usage", {})
        tokens_used = usage.get("total_tokens", 0)

        return {"summary": text, "tokens_used": tokens_used, "model": model_name}

    async def generate_summary(self, canonical_profile: dict) -> dict:
        name = canonical_profile.get("display_name") or "Unknown"

        if not self.api_key:
            logger.warning("GROQ_API_KEY not set — returning placeholder summary.")
            return {"summary": "Summary unavailable.", "tokens_used": 0, "model": ""}

        prompt = self._build_prompt(canonical_profile)

        for model_name in [_PRIMARY_MODEL, _FALLBACK_MODEL]:
            try:
                result = await self._call_model(prompt, model_name)
                tokens = result["tokens_used"]
                logger.info(f"→ Groq summary for {name}, tokens used: {tokens}")
                metrics.record_llm_usage(tokens)
                return result
            except Exception as exc:
                logger.warning(
                    f"Groq model '{model_name}' failed for '{name}': {exc}. "
                    f"{'Trying fallback...' if model_name == _PRIMARY_MODEL else 'Giving up.'}"
                )

        return {"summary": "Summary unavailable.", "tokens_used": 0, "model": ""}
