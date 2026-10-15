"""Persistent vector storage on top of ChromaDB (explicit embeddings only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import chromadb

from hld_assistant.index.embedder import Embedder


@dataclass
class VectorRecord:
    id: str
    text: str
    metadata: dict[str, Any]


@dataclass
class Match:
    id: str
    text: str
    metadata: dict[str, Any]
    distance: float


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_")[:64] or "default"


class VectorStore:
    """One collection per embedder so vector spaces never get mixed."""

    def __init__(self, directory: Path | str, embedder: Embedder):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=str(self.directory))
        self.collection = self.client.get_or_create_collection(
            name=f"hld_{_slug(embedder.name)}",
            metadata={"hnsw:space": "cosine", "embedder": embedder.name},
        )

    @property
    def count(self) -> int:
        return int(self.collection.count())

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        texts = [r.text for r in records]
        vectors = self.embedder.embed(texts)
        self.collection.upsert(
            ids=[r.id for r in records],
            documents=texts,
            metadatas=[_clean_metadata(r.metadata) for r in records],
            embeddings=cast(Any, vectors),
        )

    def query(
        self,
        text: str,
        k: int = 6,
        where: dict[str, Any] | None = None,
    ) -> list[Match]:
        if self.count == 0:
            return []
        vector = self.embedder.embed([text])[0]
        kwargs: dict[str, Any] = {
            "query_embeddings": [vector],
            "n_results": max(1, min(k, self.count)),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        result = self.collection.query(**kwargs)
        matches: list[Match] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0] or []
        metas = (result.get("metadatas") or [[]])[0] or []
        dists = (result.get("distances") or [[]])[0] or []
        for i, chunk_id in enumerate(ids):
            matches.append(
                Match(
                    id=chunk_id,
                    text=docs[i] if i < len(docs) else "",
                    metadata=dict(metas[i]) if i < len(metas) else {},
                    distance=float(dists[i]) if i < len(dists) else 1.0,
                )
            )
        return matches

    def delete_document(self, doc_id: str) -> None:
        try:
            self.collection.delete(where={"doc_id": doc_id})
        except Exception:
            pass

    def delete_all(self) -> None:
        try:
            self.client.delete_collection(self.collection.name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=f"hld_{_slug(self.embedder.name)}",
            metadata={"hnsw:space": "cosine", "embedder": self.embedder.name},
        )


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Chroma only accepts str/int/float/bool metadata values."""
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif value is None:
            continue
        else:
            clean[key] = str(value)
    return clean
