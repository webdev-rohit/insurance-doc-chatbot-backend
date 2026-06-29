import vertexai
from vertexai.language_models import TextEmbeddingModel

from apps.core.config import settings

def get_embed_model(self) -> TextEmbeddingModel:
    if self._embed_model is None:
        vertexai.init(project=settings.project_id, location=settings.region)
        self._embed_model = TextEmbeddingModel.from_pretrained(settings.embedding_model_name)
    return self._embed_model