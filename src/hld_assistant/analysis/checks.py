"""Consistency and completeness checks over extracted architecture knowledge."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Any, Iterable

from hld_assistant.analysis.entities import normalize_name
from hld_assistant.ingest.chunker import Chunk
from hld_assistant.ingest.pdf_extractor import ExtractedDocument, build_section_paths

DEPENDENCY_RE = re.compile(
    r"\b(?:uses|requires?|depends (?:on|upon)|sends to|receives from|connected to|"
    r"invokes|calls|is mapped to|mapped to|allocated to|transmits to|reads from|"
    r"writes to)\s+([A-Z][A-Za-z0-9_\-]+)",
    re.I,
)
PROVIDED_RE = re.compile(r"\bprovided\b|\bprovides\b|\bout put\b|\boutput\b", re.I)
REQUIRED_RE = re.compile(r"\brequired\b|\brequires\b|\bin put\b|\binput\b", re.I)
DEFINITION_PREFIX_RE = re.compile(r"^\s*(?:[-•*]|\d+(?:\.\d+)*[.)]|\|)?\s*([A-Z][A-Za-z0-9_\-]+)")

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _finding(rule: str, severity: str, message: str, evidence: list[dict],
             suggestion: str) -> dict[str, Any]:
    return {
        "id": f"fnd_{uuid.uuid4().hex[:12]}",
        "rule": rule,
        "severity": severity,
        "message": message,
        "evidence": evidence,
        "suggestion": suggestion,
        "status": "open",
    }


def _evidence(page: int, section: str, quote: str) -> dict[str, Any]:
    return {"page": page, "section": section, "quote": quote[:300]}


def _iter_windows(chunk_text: str, needle: str, radius: int = 110) -> Iterable[str]:
    lower = chunk_text.lower()
    start = 0
    needle_lower = needle.lower()
    while True:
        index = lower.find(needle_lower, start)
        if index < 0:
            break
        yield chunk_text[max(0, index - radius): index + len(needle) + radius]
        start = index + len(needle)


def check_terminology(entities: list[dict[str, Any]]) -> list[dict]:
    findings: list[dict] = []
    variants: dict[str, set[str]] = defaultdict(set)
    pages: dict[tuple[str, str], int] = {}
    for entity in entities:
        variants[entity["norm_name"]].add(entity["name"])
        pages.setdefault((entity["norm_name"], entity["name"]), entity["page"])
    for norm, names in sorted(variants.items()):
        if len(names) < 2:
            continue
        ordered = sorted(names)
        evidence = [
            _evidence(pages[(norm, name)], "", name) for name in ordered[:6]
        ]
        findings.append(
            _finding(
                rule="terminology_variance",
                severity="warning",
                message=(
                    f"'{ordered[0]}' appears with {len(ordered) - 1} different "
                    f"spellings: {', '.join(ordered[1:])}"
                ),
                evidence=evidence,
                suggestion="Agree on one canonical spelling and update the HLD before reuse.",
            )
        )
    return findings


def check_kind_conflicts(entities: list[dict[str, Any]]) -> list[dict]:
    findings: list[dict] = []
    by_name: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for entity in entities:
        by_name[entity["norm_name"]][entity["kind"]] = entity
    for _norm, kinds in sorted(by_name.items()):
        if len(kinds) < 2:
            continue
        sample = next(iter(kinds.values()))
        evidence = [
            _evidence(e["page"], e["section_path"], f"{e['kind']}: {e['name']}")
            for e in kinds.values()
        ]
        findings.append(
            _finding(
                rule="entity_kind_conflict",
                severity="error",
                message=(
                    f"'{sample['name']}' is used as both "
                    f"{' and '.join(sorted(kinds))} in different places."
                ),
                evidence=evidence,
                suggestion="Confirm the intended classification and align all references.",
            )
        )
    return findings


def check_port_direction(
    doc: ExtractedDocument, chunks: list[Chunk], entities: list[dict[str, Any]]
) -> list[dict]:
    """Flag ports described as provided/output in one place and required/input
    in another. Table direction columns and prose windows are treated as
    separate claims, and table rows themselves are never compared to their
    neighbours."""
    provided: dict[str, tuple[int, str, str]] = {}
    required: dict[str, tuple[int, str, str]] = {}
    port_names = {e["name"] for e in entities if e["kind"] == "Port"}
    if not port_names:
        return []
    section_paths = dict(build_section_paths(doc))

    for page in doc.pages:
        section = " > ".join(section_paths.get(page.number, []))
        for table in page.tables:
            if not table:
                continue
            headers = [cell.strip().lower() for cell in table[0]]
            dir_idx = next(
                (i for i, header in enumerate(headers) if "direction" in header), None
            )
            if dir_idx is None:
                continue
            for row in table[1:]:
                if len(row) <= dir_idx or not row[0]:
                    continue
                name = row[0].strip()
                if name not in port_names:
                    continue
                direction = row[dir_idx].strip().lower()
                quote = " | ".join(cell.strip() for cell in row[:4])
                norm = normalize_name(name)
                if _is_provided_cell(direction):
                    provided.setdefault(norm, (page.number, section, quote))
                elif _is_required_cell(direction):
                    required.setdefault(norm, (page.number, section, quote))

    for chunk in chunks:
        if chunk.kind == "table":
            continue
        for name in port_names:
            norm = normalize_name(name)
            for window in _iter_windows(chunk.text, name):
                if norm not in provided and PROVIDED_RE.search(window):
                    provided[norm] = (chunk.page_start, chunk.section_path, window.strip())
                if norm not in required and REQUIRED_RE.search(window):
                    required[norm] = (chunk.page_start, chunk.section_path, window.strip())

    findings: list[dict] = []
    for norm in sorted(set(provided) & set(required)):
        name = next(n for n in port_names if normalize_name(n) == norm)
        p_page, p_section, p_quote = provided[norm]
        r_page, r_section, r_quote = required[norm]
        findings.append(
            _finding(
                rule="port_direction_conflict",
                severity="error",
                message=(
                    f"Port '{name}' is described as both provided/output "
                    f"(p.{p_page}) and required/input (p.{r_page})."
                ),
                evidence=[
                    _evidence(p_page, p_section, p_quote),
                    _evidence(r_page, r_section, r_quote),
                ],
                suggestion="Verify the port direction against the interface specification.",
            )
        )
    return findings


def _is_provided_cell(direction: str) -> bool:
    return any(token in direction for token in ("provided", "provides", "output")) or (
        direction in {"out", "sender"}
    )


def _is_required_cell(direction: str) -> bool:
    return any(token in direction for token in ("required", "requires", "input")) or (
        direction in {"in", "receiver"}
    )


def _defined_names(chunks: list[Chunk], doc: ExtractedDocument) -> set[str]:
    defined: set[str] = set()
    for chunk in chunks:
        if chunk.kind == "table":
            for row in chunk.text.splitlines():
                for cell in row.split("|"):
                    match = DEFINITION_PREFIX_RE.match(cell.strip())
                    if match:
                        defined.add(normalize_name(match.group(1)))
        else:
            for line in chunk.text.splitlines():
                match = DEFINITION_PREFIX_RE.match(line)
                if match:
                    defined.add(normalize_name(match.group(1)))
    for page in doc.pages:
        for table in page.tables:
            for table_row in table:
                for cell in table_row:
                    if cell and cell.strip():
                        defined.add(normalize_name(cell))
    return defined


def check_undefined_references(
    chunks: list[Chunk], doc: ExtractedDocument, entities: list[dict[str, Any]]
) -> list[dict]:
    findings: list[dict] = []
    defined = _defined_names(chunks, doc)
    for entity in entities:
        defined.add(entity["norm_name"])
    seen: set[str] = set()
    for chunk in chunks:
        for match in DEPENDENCY_RE.finditer(chunk.text):
            name = match.group(1).strip(".,;:")
            norm = normalize_name(name)
            if not norm or norm in defined or norm in seen or len(name) < 4:
                continue
            seen.add(norm)
            findings.append(
                _finding(
                    rule="undefined_reference",
                    severity="warning",
                    message=f"'{name}' is referenced as a dependency but never defined in the document.",
                    evidence=[_evidence(chunk.page_start, chunk.section_path, match.group(0))],
                    suggestion="Add a definition, or correct the reference if the name is wrong.",
                )
            )
    return findings


def check_signal_interface_coverage(
    entities: list[dict[str, Any]], chunks: list[Chunk]
) -> list[dict]:
    findings: list[dict] = []
    interfaces = {e["norm_name"] for e in entities if e["kind"] == "Interface"}
    signals = [e for e in entities if e["kind"] in {"Signal", "ISignal"}]
    chunk_by_norm: dict[str, Chunk | None] = {}
    for signal in signals:
        chunk_by_norm.setdefault(signal["norm_name"], _find_chunk(chunks, signal["name"]))
    for signal in signals:
        norm = signal["norm_name"]
        shares_root = any(
            norm.startswith(i[: max(6, len(i) // 2)]) or i.startswith(norm[: max(6, len(norm) // 2)])
            for i in interfaces
        )
        chunk = chunk_by_norm.get(norm)
        in_interface_context = bool(
            chunk and re.search(r"\binterface\b", chunk.text, re.I)
        )
        if shares_root or in_interface_context:
            continue
        findings.append(
            _finding(
                rule="signal_without_interface",
                severity="info",
                message=f"Signal '{signal['name']}' is never associated with an interface.",
                evidence=[
                    _evidence(signal["page"], signal["section_path"], signal.get("context", ""))
                ],
                suggestion="Map the signal to its sender/receiver interface for traceability.",
            )
        )
    return findings


def _find_chunk(chunks: list[Chunk], name: str) -> Chunk | None:
    for chunk in chunks:
        if name.lower() in chunk.text.lower():
            return chunk
    return None


def check_empty_sections(doc: ExtractedDocument) -> list[dict]:
    findings: list[dict] = []
    section_paths = dict(build_section_paths(doc))
    for heading in doc.headings:
        page = next((p for p in doc.pages if p.number == heading.page), None)
        if page is None:
            continue
        body = (page.text or "").replace(heading.label, "", 1).strip()
        if len(body) >= 60:
            continue
        findings.append(
            _finding(
                rule="empty_section",
                severity="info",
                message=f"Section '{heading.label}' has little or no content on page {heading.page}.",
                evidence=[_evidence(heading.page, " > ".join(section_paths.get(heading.page, [])), heading.label)],
                suggestion="Complete the section or mark it as intentionally omitted.",
            )
        )
    return findings


def check_duplicate_definitions(entities: list[dict[str, Any]]) -> list[dict]:
    findings: list[dict] = []
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        by_key[(entity["norm_name"], entity["kind"])].append(entity)
    for (_norm, kind), group in sorted(by_key.items()):
        pages = {e["page"] for e in group}
        if len(pages) < 2:
            continue
        findings.append(
            _finding(
                rule="duplicate_definition",
                severity="info",
                message=f"{kind} '{group[0]['name']}' is defined on {len(pages)} pages.",
                evidence=[_evidence(e["page"], e["section_path"], e["name"]) for e in group[:5]],
                suggestion="Check that all definitions carry the same attributes.",
            )
        )
    return findings


def run_checks(
    doc: ExtractedDocument,
    chunks: list[Chunk],
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    findings.extend(check_terminology(entities))
    findings.extend(check_kind_conflicts(entities))
    findings.extend(check_port_direction(doc, chunks, entities))
    findings.extend(check_undefined_references(chunks, doc, entities))
    findings.extend(check_signal_interface_coverage(entities, chunks))
    findings.extend(check_duplicate_definitions(entities))
    findings.extend(check_empty_sections(doc))
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["rule"]))
    return findings
