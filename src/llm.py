from __future__ import annotations
from typing import Optional
import google.generativeai as genai
from .config import settings

# Configure Gemini
if settings.google_api_key:
    genai.configure(api_key=settings.google_api_key)


def llm_completion(prompt: str, system: Optional[str] = None, model: Optional[str] = None) -> str:
    model = model or settings.model_name
    contents = prompt if system is None else f"System: {system}\n\nUser: {prompt}"
    resp = genai.GenerativeModel(model).generate_content(contents)
    return resp.text or ""


def llm_fallback(prompt: str, system: Optional[str] = None) -> str:
    # Placeholder for Bedrock if needed later
    return ""
