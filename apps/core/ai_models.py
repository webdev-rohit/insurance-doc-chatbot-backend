from functools import lru_cache
from google import genai

from apps.core.config import settings


@lru_cache(maxsize=1)
def get_genai_client() -> genai.Client:
    """
    Single shared client for both LLM and embedding calls.
    Replaces vertexai.init() + separate model instantiation.
    Cached — only created once for the lifetime of the app.
    """
    return genai.Client(
        vertexai=True,
        project=settings.project_id,
        location=settings.region,
    )