from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Protocol

from langchain_core.embeddings import Embeddings

from app.core.config import Settings
from app.core.exceptions import AppError
from app.schemas.matching import EmbeddingConfigSnapshot


class EmbeddingProvider(Protocol):
    @property
    def config_snapshot(self) -> EmbeddingConfigSnapshot: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformersEmbeddingProvider:
    """Lazy, process-cached local multilingual Sentence Transformers provider."""

    def __init__(self, model_name: str, device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device

    @property
    def config_snapshot(self) -> EmbeddingConfigSnapshot:
        return EmbeddingConfigSnapshot(
            provider="sentence_transformers",
            model=self.model_name,
            device=self.device,
        )

    @staticmethod
    @lru_cache(maxsize=4)
    def _model(model_name: str, device: str) -> object:
        try:
            from sentence_transformers import SentenceTransformer

            return SentenceTransformer(model_name, device=device)
        except Exception as exc:
            raise AppError(
                "EMBEDDING_MODEL_UNAVAILABLE",
                "The configured local embedding model could not be loaded",
                503,
            ) from exc

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self.ensure_model_loaded()
        try:
            vectors = model.encode(  # type: ignore[attr-defined]
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise AppError(
                "EMBEDDING_FAILED",
                "Local document embedding failed",
                503,
            ) from exc
        return [list(map(float, vector)) for vector in vectors]

    def ensure_model_loaded(self) -> object:
        """Load the process-cached model before a timed indexing phase."""
        return self._model(self.model_name, self.device)

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            return []
        embedded = self.embed_documents([text])
        return embedded[0] if embedded else []


class FakeEmbeddingProvider:
    """Deterministic offline provider used by tests and evaluation."""

    def __init__(
        self,
        vectors: Mapping[str, Sequence[float]] | None = None,
        *,
        dimensions: int = 32,
    ) -> None:
        self.vectors = {key: self._normalize(list(value)) for key, value in (vectors or {}).items()}
        self.dimensions = dimensions

    @property
    def config_snapshot(self) -> EmbeddingConfigSnapshot:
        return EmbeddingConfigSnapshot(
            provider="fake",
            model="fake-deterministic-v1",
            device="cpu",
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            return [0.0] * self.dimensions
        if text in self.vectors:
            return self.vectors[text]
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[\w+#.-]+", text.casefold())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1 if digest[4] % 2 == 0 else -1
        return self._normalize(vector)

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class LangChainEmbeddingAdapter(Embeddings):
    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.provider.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.provider.embed_query(text)


def embedding_provider_from_settings(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "sentence_transformers":
        return SentenceTransformersEmbeddingProvider(
            settings.embedding_model,
            settings.embedding_device,
        )
    if settings.embedding_provider == "fake":
        return FakeEmbeddingProvider()
    raise AppError(
        "EMBEDDING_PROVIDER_UNSUPPORTED",
        "The configured embedding provider is not supported",
        503,
    )
