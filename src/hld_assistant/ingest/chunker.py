"""Section-aware chunking of extracted HLD content."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any

from hld_assistant.ingest.pdf_extractor import ExtractedDocument, build_section_paths

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _chunk_id(doc_key: str, ordinal: int) -> str:
    digest = hashlib.sha1(f"{doc_key}:{ordinal}".encode()).hexdigest()[:12]
    return f"chk_{digest}"


@dataclass
class Chunk:
    id: str
    ordinal: int
    section_path: str
    page_start: int
    page_end: int
    kind: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _split_units(text: str) -> list[str]:
    """Split on sentence boundaries, then hard-wrap anything still too long."""
    units: list[str] = []
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for sentence in SENTENCE_RE.split(paragraph):
            sentence = sentence.strip()
            if sentence:
                units.append(sentence)
    return units


def _pack(units: list[str], chunk_chars: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for unit in units:
        while len(unit) > chunk_chars:
            if current:
                pieces.append(current.strip())
                current = ""
            pieces.append(unit[:chunk_chars].strip())
            unit = unit[chunk_chars - overlap:]
        if current and len(current) + len(unit) + 1 > chunk_chars:
            pieces.append(current.strip())
            current = unit
        else:
            current = f"{current} {unit}".strip()
    if current:
        pieces.append(current.strip())
    return [p for p in pieces if p]


def chunk_document(
    doc: ExtractedDocument,
    chunk_chars: int = 1200,
    overlap: int = 200,
    doc_key: str | None = None,
) -> list[Chunk]:
    doc_key = doc_key or doc.filename
    page_paths = dict(build_section_paths(doc))
    chunks: list[Chunk] = []
    ordinal = 0

    for page in doc.pages:
        section = " > ".join(page_paths.get(page.number, [])) or doc.filename
        text_parts: list[tuple[str, str]] = []
        if page.text.strip():
            text_parts.append(("text", page.text))
        if page.table_text.strip():
            text_parts.append(("table", page.table_text))

        for kind, content in text_parts:
            for piece in _pack(_split_units(content), chunk_chars, overlap):
                chunks.append(
                    Chunk(
                        id=_chunk_id(doc_key, ordinal),
                        ordinal=ordinal,
                        section_path=section,
                        page_start=page.number,
                        page_end=page.number,
                        kind=kind,
                        text=piece,
                    )
                )
                ordinal += 1

    return chunks


def chunks_as_dicts(chunks: list[Chunk]) -> list[dict[str, Any]]:
    return [c.to_dict() for c in chunks]
