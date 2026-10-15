"""Hybrid retrieval: vector similarity plus a light lexical rerank."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Callable

from hld_assistant.config import Settings
from hld_assistant.index.vector_store import VectorStore

TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


@dataclass
class RetrievedPassage:
    chunk_id: str
    doc_id: str
    document: str
    text: str
    section_path: str
    page_start: int
    page_end: int
    kind: str
    vector_score: float
    lexical_score: float
    score: float

    @property
    def citation(self) -> str:
        pages = (
            str(self.page_start)
            if self.page_start == self.page_end
            else f"{self.page_start}-{self.page_end}"
        )
        section = self.section_path or "unsectioned"
        return f"{self.document} | {section} | p.{pages}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citation"] = self.citation
        return data


def _lexical_overlap(query: str, text: str) -> float:
    query_terms = set(TOKEN_RE.findall(query.lower()))
    if not query_terms:
        return 0.0
    text_terms = set(TOKEN_RE.findall(text.lower()))
    if not text_terms:
        return 0.0
    overlap = query_terms & text_terms
    # substring hits matter for technical identifiers (VehicleSpeed vs Speed)
    for term in query_terms:
        if term in text.lower():
            overlap.add(term)
    return len(overlap) / len(query_terms)


class Retriever:
    def __init__(
        self,
        store: VectorStore,
        settings: Settings,
        doc_lookup: Callable[[str], dict[str, Any]] | None = None,
    ):
        self.store = store
        self.settings = settings
        self.doc_lookup = doc_lookup or (lambda doc_id: {"name": doc_id})

    def search(
        self,
        query: str,
        doc_ids: list[str] | None = None,
        k: int | None = None,
    ) -> list[RetrievedPassage]:
        k = k or self.settings.top_k
        where: dict[str, Any] | None = None
        if doc_ids:
            where = {"doc_id": {"$in": list(doc_ids)}}
        matches = self.store.query(query, k=max(k * 3, k), where=where)

        passages: list[RetrievedPassage] = []
        for match in matches:
            meta = match.metadata or {}
            doc_id = str(meta.get("doc_id", ""))
            document = str(meta.get("document") or self.doc_lookup(doc_id).get("name", doc_id))
            vector_score = max(0.0, 1.0 - match.distance)
            lexical_score = _lexical_overlap(query, match.text)
            passages.append(
                RetrievedPassage(
                    chunk_id=match.id,
                    doc_id=doc_id,
                    document=document,
                    text=match.text,
                    section_path=str(meta.get("section_path", "")),
                    page_start=int(meta.get("page_start", 0)),
                    page_end=int(meta.get("page_end", 0)),
                    kind=str(meta.get("kind", "text")),
                    vector_score=round(vector_score, 4),
                    lexical_score=round(lexical_score, 4),
                    score=round(0.7 * vector_score + 0.3 * lexical_score, 4),
                )
            )

        passages.sort(key=lambda p: p.score, reverse=True)
        return passages[:k]
