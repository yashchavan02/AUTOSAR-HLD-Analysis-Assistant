"""Revision comparison between two ingested HLD documents."""

from __future__ import annotations

import difflib
from collections import defaultdict
from typing import Any


def _entity_map(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for entity in entities:
        mapping.setdefault(entity["norm_name"], entity)
    return mapping


def compare_entities(
    entities_a: list[dict[str, Any]], entities_b: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    map_a = _entity_map(entities_a)
    map_b = _entity_map(entities_b)
    added = [map_b[k] for k in sorted(set(map_b) - set(map_a))]
    removed = [map_a[k] for k in sorted(set(map_a) - set(map_b))]
    modified = []
    for key in sorted(set(map_a) & set(map_b)):
        a, b = map_a[key], map_b[key]
        if a["kind"] != b["kind"]:
            modified.append(
                {
                    "name": a["name"],
                    "from_kind": a["kind"],
                    "to_kind": b["kind"],
                    "page_a": a["page"],
                    "page_b": b["page"],
                }
            )
    return {"added": added, "removed": removed, "modified": modified}


def compare_sections(headings_a: list[dict], headings_b: list[dict]) -> dict[str, list[str]]:
    set_a = {h["label"] for h in headings_a}
    set_b = {h["label"] for h in headings_b}
    return {
        "added": sorted(set_b - set_a),
        "removed": sorted(set_a - set_b),
        "common": sorted(set_a & set_b),
    }


def compare_section_text(
    chunks_a: list[dict[str, Any]], chunks_b: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    def group(chunks: list[dict[str, Any]]) -> dict[str, str]:
        texts: dict[str, list[str]] = defaultdict(list)
        for chunk in chunks:
            texts[chunk["section_path"]].append(chunk["text"])
        return {key: "\n".join(value) for key, value in texts.items()}

    text_a = group(chunks_a)
    text_b = group(chunks_b)
    changed: list[dict[str, Any]] = []
    for section in sorted(set(text_a) & set(text_b)):
        similarity = difflib.SequenceMatcher(
            None, text_a[section], text_b[section]
        ).ratio()
        if similarity >= 0.999:
            continue
        diff = list(
            difflib.unified_diff(
                text_a[section].splitlines(),
                text_b[section].splitlines(),
                lineterm="",
                n=0,
            )
        )
        changed.append(
            {
                "section": section,
                "similarity": round(similarity, 3),
                "lines_added": sum(1 for line in diff if line.startswith("+") and not line.startswith("+++")),
                "lines_removed": sum(1 for line in diff if line.startswith("-") and not line.startswith("---")),
                "diff": diff[:60],
            }
        )
    changed.sort(key=lambda item: item["similarity"])
    return changed


def build_comparison(
    doc_a: dict[str, Any],
    doc_b: dict[str, Any],
    entities_a: list[dict[str, Any]],
    entities_b: list[dict[str, Any]],
    headings_a: list[dict],
    headings_b: list[dict],
    chunks_a: list[dict[str, Any]],
    chunks_b: list[dict[str, Any]],
) -> dict[str, Any]:
    entity_diff = compare_entities(entities_a, entities_b)
    section_diff = compare_sections(headings_a, headings_b)
    changed = compare_section_text(chunks_a, chunks_b)
    report = {
        "revision_a": {
            "id": doc_a.get("id"),
            "name": doc_a.get("name"),
            "version": doc_a.get("version_label"),
            "status": doc_a.get("status"),
            "pages": doc_a.get("pages"),
        },
        "revision_b": {
            "id": doc_b.get("id"),
            "name": doc_b.get("name"),
            "version": doc_b.get("version_label"),
            "status": doc_b.get("status"),
            "pages": doc_b.get("pages"),
        },
        "entities": entity_diff,
        "sections": section_diff,
        "sections_changed": changed,
        "summary": {
            "entities_added": len(entity_diff["added"]),
            "entities_removed": len(entity_diff["removed"]),
            "entities_modified": len(entity_diff["modified"]),
            "sections_added": len(section_diff["added"]),
            "sections_removed": len(section_diff["removed"]),
            "sections_changed": len(changed),
        },
    }
    return report
