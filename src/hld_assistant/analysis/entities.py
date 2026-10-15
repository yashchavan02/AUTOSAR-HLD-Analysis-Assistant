"""Rule-based recognition of AUTOSAR architecture entities in HLD text."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from hld_assistant.ingest.pdf_extractor import ExtractedDocument, build_section_paths

BSW_MODULES = {
    "CanIf", "CanNm", "CanSM", "CanTp", "CanTrcv", "Com", "ComM", "Dcm", "Dem",
    "EcuM", "BswM", "Fee", "Fls", "FdTx", "J1939Tp", "LinIf", "LinSM", "NvM",
    "PduR", "Rte", "Nm", "NvM_Write", "SoAd", "TcpIp", "Uds", "WdgM", "Xcp",
    "IoHwAb", "MemIf", "Adc", "Pwm", "Gpt", "Spi", "Wdg", "Mcu", "Port", "Dio",
}

PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    ("Component", re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:SwComponentType|ComponentType|Component|Composition))\b"), 0.95),
    ("Port", re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:PortPrototype|Port))\b"), 0.9),
    ("Interface", re.compile(r"\b([A-Z][A-Za-z0-9_]*Interface)\b"), 0.95),
    ("Signal", re.compile(r"\b([A-Z][A-Za-z0-9_]*Signal)\b"), 0.9),
    ("ISignal", re.compile(r"\b(I-Signal\s+[A-Za-z0-9_]+)"), 0.9),
    ("Pdu", re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:NPdu|IPdu|SPdu|Pdu|PDU))\b"), 0.9),
    ("Runnable", re.compile(r"\b([A-Z][A-Za-z0-9_]*Runnable(?:Entity)?)\b"), 0.9),
    ("Event", re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:TimingEvent|DataReceivedEvent|ModeSwitchedEvent|InitEvent|OperationInvokedEvent|Event))\b"), 0.85),
    ("Task", re.compile(r"\b([A-Z][A-Za-z0-9_]*Task)\b"), 0.8),
    ("Ecu", re.compile(r"\b([A-Z][A-Za-z0-9_]*ECU|[A-Z][A-Za-z0-9_]*Ecu)\b"), 0.8),
    ("Connector", re.compile(r"\b((?:Assembly|Delegation)SwConnector)\b"), 0.9),
    ("Service", re.compile(r"\b([A-Z][A-Za-z0-9_]*Service)\b"), 0.75),
]

KIND_KEYWORDS = {
    "component": "Component",
    "sw component": "Component",
    "composition": "Component",
    "port": "Port",
    "interface": "Interface",
    "signal": "Signal",
    "pdu": "Pdu",
    "runnable": "Runnable",
    "event": "Event",
    "task": "Task",
    "ecu": "Ecu",
    "connector": "Connector",
    "service": "Service",
}


@dataclass
class Entity:
    kind: str
    name: str
    norm_name: str
    page: int
    section_path: str
    context: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "norm_name": self.norm_name,
            "page": self.page,
            "section_path": self.section_path,
            "context": self.context,
            "confidence": self.confidence,
        }


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _context(line: str, match: re.Match[str], radius: int = 90) -> str:
    start = max(0, match.start() - radius)
    end = min(len(line), match.end() + radius)
    text = line[start:end].strip()
    return ("…" if start > 0 else "") + text + ("…" if end < len(line) else "")


def _kind_for_header(header: str) -> str | None:
    key = re.sub(r"[^a-z ]", "", header.lower()).strip()
    for keyword, kind in KIND_KEYWORDS.items():
        if keyword in key:
            return kind
    return None


def extract_entities(
    doc: ExtractedDocument,
    section_paths: dict[int, list[str]] | None = None,
) -> list[dict[str, Any]]:
    section_paths = section_paths or dict(build_section_paths(doc))
    found: dict[tuple[str, str], Entity] = {}
    order: list[tuple[str, str]] = []

    def add(entity: Entity) -> None:
        key = (entity.norm_name, entity.kind)
        if key not in found:
            found[key] = entity
            order.append(key)

    for page in doc.pages:
        section = " > ".join(section_paths.get(page.number, []))
        for line in (page.text or "").splitlines():
            line = line.strip()
            if not line or len(line) > 400:
                continue
            for kind, pattern, confidence in PATTERNS:
                for match in pattern.finditer(line):
                    name = match.group(1).strip()
                    if len(name) < 3 or name.lower() in {"thistask", "thecomponent"}:
                        continue
                    add(
                        Entity(
                            kind=kind,
                            name=name,
                            norm_name=normalize_name(name),
                            page=page.number,
                            section_path=section,
                            context=_context(line, match),
                            confidence=confidence,
                        )
                    )
            for module in BSW_MODULES:
                module_match = re.search(rf"\b{re.escape(module)}\b", line)
                if module_match:
                    add(
                        Entity(
                            kind="BswModule",
                            name=module,
                            norm_name=normalize_name(module),
                            page=page.number,
                            section_path=section,
                            context=_context(line, module_match),
                            confidence=0.8,
                        )
                    )

        for table in page.tables:
            if not table:
                continue
            columns = [
                (index, header_kind)
                for index, header in enumerate(table[0])
                if (header_kind := _kind_for_header(header))
            ]
            for row in table[1:]:
                if not row:
                    continue
                for index, kind in columns:
                    if index >= len(row):
                        continue
                    name = (row[index] or "").strip()
                    if (
                        not name
                        or len(name) > 80
                        or name.lower() in {"name", "-", "n/a", "none"}
                    ):
                        continue
                    add(
                        Entity(
                            kind=kind,
                            name=name,
                            norm_name=normalize_name(name),
                            page=page.number,
                            section_path=section,
                            context=" | ".join(c.strip() for c in row[:4]),
                            confidence=0.95,
                        )
                    )

    entities = [found[key].to_dict() for key in order]
    return _boost_shared_names(entities)


def _boost_shared_names(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Names seen on many pages are more certainly real design entities."""
    counts: dict[str, int] = defaultdict(int)
    for entity in entities:
        counts[entity["norm_name"]] += 1
    for entity in entities:
        seen = counts[entity["norm_name"]]
        entity["confidence"] = round(min(0.99, entity["confidence"] + 0.01 * (seen - 1)), 3)
    return entities


def entity_index(entities: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        index[entity["norm_name"]].append(entity)
    return index
