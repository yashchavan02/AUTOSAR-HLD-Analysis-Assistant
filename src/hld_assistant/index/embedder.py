"""Embedding backends.

``auto`` picks sentence-transformers when it is installed and its model can be
loaded, otherwise falls back to a dependency-free hashing embedder so the pilot
keeps working offline.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


class HashingEmbedder:
    """Character n-gram hashing embedder. No model download, deterministic,
    and surprisingly serviceable for exact/substring style technical terms."""

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = TOKEN_RE.findall(text.lower())
        grams: list[str] = list(tokens)
        joined = " ".join(tokens)
        for token in tokens:
            padded = f"#{token}#"
            grams.extend(padded[i:i + 3] for i in range(len(padded) - 2))
        grams.extend(joined[i:i + 5] for i in range(max(0, len(joined) - 4)))
        for gram in grams:
            digest = hashlib.md5(gram.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _l2_normalize(vector)


class SentenceTransformerEmbedder:
    """Wrapper around sentence-transformers (optional dependency)."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]


class FastEmbedEmbedder:
    """ONNX embedding models via fastembed - no torch dependency."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.model = TextEmbedding(model_name)
        sample = next(iter(self.model.embed(["dimension probe"])))
        self.dim = len(sample)
        self.name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(v) for v in vector] for vector in self.model.embed(texts)]


def create_embedder(settings) -> Embedder:
    """Build the configured embedder, degrading gracefully."""
    choice = (settings.embedder or "auto").lower()
    if choice == "hashing":
        return HashingEmbedder(settings.hashing_dim)
    if choice in {"auto", "sentence-transformers"}:
        try:
            embedder = SentenceTransformerEmbedder(settings.embedding_model)
            logger.info("Using sentence-transformers embedder: %s", settings.embedding_model)
            return embedder
        except Exception as exc:  # missing package, no model download, etc.
            if choice == "sentence-transformers":
                raise
            logger.warning(
                "sentence-transformers unavailable (%s); trying fastembed", exc
            )
    if choice in {"auto", "fastembed"}:
        try:
            onnx_embedder = FastEmbedEmbedder(settings.fastembed_model)
            logger.info("Using fastembed embedder: %s", settings.fastembed_model)
            return onnx_embedder
        except Exception as exc:
            if choice == "fastembed":
                raise
            logger.warning("fastembed unavailable (%s); using hashing embedder", exc)
    return HashingEmbedder(settings.hashing_dim)
