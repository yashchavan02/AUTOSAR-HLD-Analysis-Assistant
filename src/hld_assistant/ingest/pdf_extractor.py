"""Section-aware PDF extraction for HLD documents using PyMuPDF."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*[\.:)]?\s+(\S.*)$")
APPENDIX_RE = re.compile(r"^\s*(Appendix|Annex)\s+([A-Z0-9]+)\s*[\.:)]?\s+(\S.*)$", re.I)


@dataclass
class Heading:
    level: int
    number: str
    title: str
    page: int

    @property
    def label(self) -> str:
        return f"{self.number} {self.title}".strip()


@dataclass
class PageContent:
    number: int
    text: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)
    scanned: bool = False

    @property
    def table_text(self) -> str:
        blocks = []
        for i, table in enumerate(self.tables, start=1):
            rows = [" | ".join(cell.strip() for cell in row) for row in table]
            blocks.append(f"[Table {i} on page {self.number}]\n" + "\n".join(rows))
        return "\n\n".join(blocks)


@dataclass
class ExtractedDocument:
    filename: str
    page_count: int
    metadata: dict[str, Any]
    pages: list[PageContent]
    headings: list[Heading]
    warnings: list[str] = field(default_factory=list)

    @property
    def scanned_pages(self) -> int:
        return sum(1 for p in self.pages if p.scanned)


def _span_size_counts(page: pymupdf.Page) -> tuple[float, int]:
    """Return the dominant font size and how often it occurs."""
    counts: dict[float, int] = {}
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                size = round(float(span.get("size", 0)), 1)
                counts[size] = counts.get(size, 0) + len(text)
    if not counts:
        return 0.0, 0
    size, weight = max(counts.items(), key=lambda kv: kv[1])
    return size, weight


def _classify_heading(text: str, size: float, body_size: float, bold: bool) -> int | None:
    """Return heading level 1-4, or None when the line is body text."""
    text = text.strip()
    if not text or len(text) > 120:
        return None
    if text.endswith((".", ";", ",")) and not HEADING_RE.match(text):
        return None
    match = HEADING_RE.match(text) or APPENDIX_RE.match(text)
    if match:
        numbered = HEADING_RE.match(text)
        depth = len(numbered.group(1).split(".")) if numbered else 1
        return min(depth, 4)
    if body_size and size >= body_size * 1.3:
        return 1
    if bold and body_size and size >= body_size * 1.05:
        return 3
    if body_size and size >= body_size * 1.15:
        return 2
    return None


def _extract_page_text(page: pymupdf.Page) -> tuple[str, list[list[list[str]]], bool]:
    raw = page.get_text("text") or ""
    tables: list[list[list[str]]] = []
    try:
        finder = page.find_tables()
        for table in finder.tables:
            data = table.extract()
            rows = [[(cell or "").replace("\n", " ").strip() for cell in row] for row in data]
            if rows:
                tables.append(rows)
            if table.bbox:
                page.add_redact_annot(pymupdf.Rect(table.bbox))
        if tables:
            page.apply_redactions(images=0)
            raw = page.get_text("text") or ""
    except Exception:  # tables are best effort; never fail ingestion on them
        tables = []
    has_image = bool(page.get_images(full=True))
    scanned = not raw.strip() and has_image
    return raw, tables, scanned


def extract_pdf(path: Path | str, filename: str | None = None) -> ExtractedDocument:
    path = Path(path)
    warnings: list[str] = []
    with pymupdf.open(path) as doc:
        pages: list[PageContent] = []
        headings: list[Heading] = []
        sizes = [_span_size_counts(p) for p in doc]
        body_size = max((s for s, w in sizes if s), default=0.0)

        for index, page in enumerate(doc, start=1):
            text, tables, scanned = _extract_page_text(page)
            pages.append(PageContent(number=index, text=text, tables=tables, scanned=scanned))

            sizes[index - 1][0]
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    line_text = "".join(s.get("text", "") for s in spans).strip()
                    if not line_text:
                        continue
                    line_size = max(float(s.get("size", 0)) for s in spans)
                    bold = any(
                        "bold" in str(s.get("flags", 0)) or (s.get("flags", 0) & 2**4)
                        for s in spans
                    )
                    level = _classify_heading(line_text, line_size, body_size, bold)
                    if level is None:
                        continue
                    match = HEADING_RE.match(line_text) or APPENDIX_RE.match(line_text)
                    if match:
                        if HEADING_RE.match(line_text):
                            number, title = match.group(1), match.group(2).strip()
                        else:
                            number, title = match.group(2), match.group(3).strip()
                    else:
                        number, title = "", line_text
                    headings.append(Heading(level=level, number=number, title=title, page=index))

        if any(p.scanned for p in pages):
            warnings.append(
                f"{sum(1 for p in pages if p.scanned)} page(s) have no text layer "
                "(scanned/image content). OCR is not enabled in this pilot; those pages "
                "are excluded from search."
            )

        metadata = {
            k: v for k, v in (doc.metadata or {}).items() if v
        }
        metadata["page_count"] = doc.page_count

    headings = _dedupe_headings(headings)
    return ExtractedDocument(
        filename=filename or path.name,
        page_count=len(pages),
        metadata=metadata,
        pages=pages,
        headings=headings,
        warnings=warnings,
    )


def _dedupe_headings(headings: list[Heading]) -> list[Heading]:
    seen: set[tuple[int, str, str]] = set()
    out: list[Heading] = []
    for h in headings:
        key = (h.page, h.number, h.title.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def build_section_paths(doc: ExtractedDocument) -> list[tuple[int, list[str]]]:
    """Map each page to its breadcrumb of ancestor headings."""
    stack: list[Heading] = []
    page_paths: dict[int, list[str]] = {p.number: [] for p in doc.pages}
    current: list[str] = []
    by_page: dict[int, list[Heading]] = {}
    for h in doc.headings:
        by_page.setdefault(h.page, []).append(h)

    for page_no in sorted(page_paths):
        for heading in by_page.get(page_no, []):
            while stack and stack[-1].level >= heading.level:
                stack.pop()
            stack.append(heading)
            current = [h.label for h in stack]
        page_paths[page_no] = list(current)
    return [(n, page_paths[n]) for n in sorted(page_paths)]
