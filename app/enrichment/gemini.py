import google.generativeai as genai
from typing import Optional
from app.config import settings

class GeminiEnricher:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        if self.api_key:
            genai.configure(api_key=self.api_key)

    async def generate_profile_summary(self, profile_data: dict) -> Optional[str]:
        if not self.api_key:
            return "Gemini API key not configured. Summary unavailable."
        
        try:
            model = genai.GenerativeModel('gemini-pro')
            prompt = f"Summarize the following developer's profile and skills: {profile_data}"
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error generating summary: {str(e)}"
