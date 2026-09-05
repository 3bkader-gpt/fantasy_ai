"""Backwards compatibility shim for AIManager."""
from src.infrastructure.ai.gemini_advisor import GeminiAdvisor as AIManager

__all__ = ["AIManager"]
