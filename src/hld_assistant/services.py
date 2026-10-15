"""Application service layer shared by the Streamlit UI and the FastAPI app."""

from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hld_assistant.analysis.checks import run_checks
from hld_assistant.analysis.compare import build_comparison
from hld_assistant.analysis.entities import extract_entities
from hld_assistant.config import Settings, get_settings
from hld_assistant.db import Store
from hld_assistant.export import exporter
from hld_assistant.index.embedder import create_embedder
from hld_assistant.index.vector_store import VectorRecord, VectorStore
from hld_assistant.ingest.chunker import chunk_document, chunks_as_dicts
from hld_assistant.ingest.pdf_extractor import extract_pdf
from hld_assistant.rag import prompts
from hld_assistant.rag.llm import LLMClient, LLMUnavailable
from hld_assistant.rag.retriever import RetrievedPassage, Retriever

logger = logging.getLogger(__name__)

CITATION_RE = re.compile(r"\[(\d+)\]")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AssistantServices:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()
        self.store = Store(self.settings.db_path)
        self.store.init_schema()
        self.embedder = create_embedder(self.settings)
        self.vectors = VectorStore(self.settings.vector_dir, self.embedder)
        self.retriever = Retriever(
            self.vectors,
            self.settings,
            lambda doc_id: self.store.get_document(doc_id) or {"name": doc_id},
        )
        self.llm = LLMClient(self.settings)

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        documents = self.store.list_documents()
        chunks_stored = self.store.count_chunks()
        indexed = self.vectors.count
        return {
            "documents": len(documents),
            "chunks_indexed": indexed,
            "chunks_stored": chunks_stored,
            "index_complete": indexed >= chunks_stored,
            "embedder": self.embedder.name,
            "llm": self.llm.status(),
            "data_dir": str(self.settings.data_dir),
            "project": self.settings.project,
            "version": _utc_now(),
        }

    # ------------------------------------------------------------------
    # ingestion
    # ------------------------------------------------------------------
    def ingest(
        self,
        source: Path | str,
        name: str | None = None,
        version_label: str = "",
        status: str = "draft",
        replace_id: str | None = None,
    ) -> dict[str, Any]:
        source = Path(source)
        payload = source.read_bytes()
        sha256 = hashlib.sha256(payload).hexdigest()
        for doc in self.store.list_documents():
            if doc["sha256"] == sha256 and doc["id"] != replace_id:
                return {
                    "doc_id": doc["id"],
                    "duplicate_of": doc["name"],
                    "message": "Identical content already ingested.",
                }

        doc_name = name or source.name
        if replace_id:
            self.delete_document(replace_id, keep_file=True)

        extracted = extract_pdf(source, filename=doc_name)
        chunks = chunk_document(
            extracted,
            chunk_chars=self.settings.chunk_chars,
            overlap=self.settings.chunk_overlap,
            doc_key=f"{doc_name}:{sha256[:12]}",
        )
        entities = extract_entities(extracted)

        doc_id = self.store.add_document(
            name=doc_name,
            source_path=str(source),
            sha256=sha256,
            version_label=version_label,
            status=status,
            pages=extracted.page_count,
            scanned_pages=extracted.scanned_pages,
            headings=len(extracted.headings),
            chunks=len(chunks),
            metadata={
                **extracted.metadata,
                "warnings": extracted.warnings,
                "ingested_at": _utc_now(),
                "headings": [
                    {"label": h.label, "page": h.page, "level": h.level}
                    for h in extracted.headings
                ],
            },
        )
        chunk_dicts = chunks_as_dicts(chunks)
        for chunk in chunk_dicts:
            chunk["doc_id"] = doc_id
        self.store.add_chunks(doc_id, chunk_dicts)
        self.store.replace_entities(doc_id, entities)
        self._index_chunks(doc_id, doc_name, chunk_dicts)

        return {
            "doc_id": doc_id,
            "name": doc_name,
            "pages": extracted.page_count,
            "scanned_pages": extracted.scanned_pages,
            "chunks": len(chunks),
            "entities": len(entities),
            "headings": len(extracted.headings),
            "warnings": extracted.warnings,
        }

    def _index_chunks(self, doc_id: str, doc_name: str, chunks: list[dict[str, Any]]) -> None:
        self.vectors.delete_document(doc_id)
        records = [
            VectorRecord(
                id=chunk["id"],
                text=chunk["text"],
                metadata={
                    "doc_id": doc_id,
                    "document": doc_name,
                    "section_path": chunk["section_path"],
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "kind": chunk["kind"],
                    "ordinal": chunk["ordinal"],
                },
            )
            for chunk in chunks
        ]
        for start in range(0, len(records), 64):
            self.vectors.upsert(records[start:start + 64])

    def reindex(self, doc_id: str) -> dict[str, Any]:
        doc = self.store.get_document(doc_id)
        if not doc:
            raise KeyError(f"Unknown document: {doc_id}")
        chunks = self.store.get_chunks(doc_id)
        self._index_chunks(doc_id, doc["name"], chunks)
        return {"doc_id": doc_id, "chunks": len(chunks), "indexed": self.vectors.count}

    def list_documents(self) -> list[dict[str, Any]]:
        return self.store.list_documents()

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        return self.store.get_document(doc_id)

    def delete_document(self, doc_id: str, keep_file: bool = False) -> None:
        doc = self.store.get_document(doc_id)
        if not doc:
            return
        self.vectors.delete_document(doc_id)
        self.store.delete_document(doc_id)
        if not keep_file:
            source = Path(doc.get("source_path", ""))
            try:
                if source.is_file() and self.settings.data_dir in source.parents:
                    source.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # search & Q&A
    # ------------------------------------------------------------------
    def search(
        self, query: str, doc_ids: list[str] | None = None, k: int | None = None
    ) -> list[RetrievedPassage]:
        return self.retriever.search(query, doc_ids=doc_ids, k=k)

    def ask(
        self,
        question: str,
        doc_ids: list[str] | None = None,
        k: int | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        passages = self.search(question, doc_ids=doc_ids, k=k)
        result: dict[str, Any]
        if not passages:
            answer = "No indexed content matches this query. Ingest an HLD document first."
            result = {
                "mode": "empty",
                "answer": answer,
                "citations": [],
                "grounded": False,
                "passages": [],
            }
        else:
            context = prompts.render_context([p.to_dict() for p in passages])
            generated = None
            if self.llm.enabled:
                try:
                    generated = self.llm.generate(
                        prompts.SYSTEM_PROMPT,
                        prompts.USER_PROMPT.format(context=context, question=question),
                    )
                except LLMUnavailable as exc:
                    logger.warning("LLM unavailable, falling back to retrieval mode: %s", exc)

            if generated:
                citations = _citations_for(generated, passages)
                result = {
                    "mode": "generate",
                    "answer": generated,
                    "citations": citations,
                    "grounded": bool(citations) or "Insufficient evidence" in generated,
                    "passages": [p.to_dict() for p in passages],
                }
            else:
                answer = _extractive_answer(question, passages)
                citations = [p.citation for p in passages]
                result = {
                    "mode": "retrieval",
                    "answer": answer,
                    "citations": citations,
                    "grounded": True,
                    "passages": [p.to_dict() for p in passages],
                }

        if persist:
            result["query_id"] = self.store.add_query(
                question=question,
                answer=result["answer"],
                citations=[{"citation": c} for c in result["citations"]],
                grounded=result["grounded"],
                mode=result["mode"],
            )
        return result

    def list_queries(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list_queries(limit)

    def add_review(self, target: str, target_id: str, verdict: str, comment: str,
                   reviewer: str) -> str:
        return self.store.add_review(target, target_id, verdict, comment, reviewer)

    def list_reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_reviews(limit)

    # ------------------------------------------------------------------
    # analysis
    # ------------------------------------------------------------------
    def inventory(self, doc_id: str) -> dict[str, list[dict[str, Any]]]:
        entities = self.store.get_entities(doc_id)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        counts: dict[tuple[str, str], int] = defaultdict(int)
        first: dict[tuple[str, str], dict[str, Any]] = {}
        for entity in entities:
            key = (entity["kind"], entity["name"])
            counts[key] += 1
            first.setdefault(key, entity)
        for (kind, name), entity in sorted(first.items()):
            entry = dict(entity)
            entry["occurrences"] = counts[(kind, name)]
            grouped[kind].append(entry)
        return dict(grouped)

    def checks(self, doc_id: str, persist: bool = True) -> list[dict[str, Any]]:
        doc = self.store.get_document(doc_id)
        if not doc:
            raise KeyError(f"Unknown document: {doc_id}")
        source = Path(doc["source_path"])
        if not source.is_file():
            raise FileNotFoundError(
                f"Source PDF for '{doc['name']}' is no longer at {source}; "
                "re-upload it to run document-level checks."
            )
        extracted = extract_pdf(source, filename=doc["name"])
        chunks = [
            c for c in self.store.get_chunks(doc_id)
        ]
        chunk_objs = [
            _chunk_from_dict(c) for c in chunks
        ]
        entities = self.store.get_entities(doc_id)
        findings = run_checks(extracted, chunk_objs, entities)
        if persist:
            self.store.replace_findings(doc_id, findings)
        return findings

    def get_findings(self, doc_id: str) -> list[dict[str, Any]]:
        return self.store.get_findings(doc_id)

    def compare(self, doc_id_a: str, doc_id_b: str) -> dict[str, Any]:
        doc_a = self.store.get_document(doc_id_a)
        doc_b = self.store.get_document(doc_id_b)
        if not doc_a or not doc_b:
            raise KeyError("Both document ids must refer to ingested documents")
        return build_comparison(
            doc_a,
            doc_b,
            self.store.get_entities(doc_id_a),
            self.store.get_entities(doc_id_b),
            _headings_of(doc_a),
            _headings_of(doc_b),
            self.store.get_chunks(doc_id_a),
            self.store.get_chunks(doc_id_b),
        )

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------
    def export_document(self, doc_id: str, include_queries: bool = True) -> list[Path]:
        doc = self.store.get_document(doc_id)
        if not doc:
            raise KeyError(f"Unknown document: {doc_id}")
        findings = self.store.get_findings(doc_id)
        if not findings:
            try:
                findings = self.checks(doc_id)
            except (FileNotFoundError, KeyError):
                findings = []
        queries = self.store.list_queries(100) if include_queries else None
        return exporter.write_exports(
            self.settings.export_dir,
            doc,
            self.inventory(doc_id),
            self.store.get_entities(doc_id),
            findings,
            queries,
        )

    def export_comparison(self, report: dict[str, Any]) -> list[Path]:
        return exporter.write_comparison_export(self.settings.export_dir, report)


def _chunk_from_dict(data: dict[str, Any]):
    from hld_assistant.ingest.chunker import Chunk

    return Chunk(
        id=data["id"],
        ordinal=data["ordinal"],
        section_path=data["section_path"],
        page_start=data["page_start"],
        page_end=data["page_end"],
        kind=data.get("kind", "text"),
        text=data["text"],
    )


def _headings_of(doc: dict[str, Any]) -> list[dict[str, Any]]:
    meta = doc.get("metadata", {}) or {}
    headings = meta.get("headings")
    if isinstance(headings, list):
        return headings
    return [
        {"label": label, "page": 0, "level": 1}
        for label in meta.get("section_labels", [])
    ]


def _citations_for(answer: str, passages: list[RetrievedPassage]) -> list[str]:
    cited: list[str] = []
    for raw in CITATION_RE.findall(answer):
        index = int(raw)
        if 1 <= index <= len(passages):
            citation = passages[index - 1].citation
            if citation not in cited:
                cited.append(citation)
    return cited


def _extractive_answer(question: str, passages: list[RetrievedPassage]) -> str:
    terms = [t.lower() for t in re.findall(r"[A-Za-z0-9]{4,}", question)]
    lines = [
        "LLM endpoint unavailable - showing grounded evidence excerpts only "
        "(no generated claims):",
        "",
    ]
    for index, passage in enumerate(passages, start=1):
        sentences = re.split(r"(?<=[.!?])\s+", passage.text)
        scored = []
        for sentence in sentences:
            lower = sentence.lower()
            score = sum(1 for term in terms if term in lower)
            if score or len(sentences) <= 2:
                scored.append((score, sentence))
        scored.sort(key=lambda item: -item[0])
        best = " ".join(s for _, s in scored[:2]).strip() or passage.text[:300].strip()
        lines.append(f"[{index}] ({passage.citation}) {best}")
        lines.append("")
    lines.append("Review the excerpts above or start the configured LLM for a synthesis.")
    return "\n".join(lines)
