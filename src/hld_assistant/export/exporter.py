"""Structured export of extracted findings (JSON / CSV / Markdown)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any


def entities_csv(entities: list[dict[str, Any]]) -> str:
    return _csv(
        entities,
        ["kind", "name", "norm_name", "page", "section_path", "confidence", "context"],
    )


def findings_csv(findings: list[dict[str, Any]]) -> str:
    rows = []
    for finding in findings:
        evidence = "; ".join(
            f"p.{e.get('page')} {e.get('section', '')}: {e.get('quote', '')}"
            for e in finding.get("evidence", [])
        )
        rows.append(
            {
                "rule": finding.get("rule", ""),
                "severity": finding.get("severity", ""),
                "message": finding.get("message", ""),
                "suggestion": finding.get("suggestion", ""),
                "status": finding.get("status", ""),
                "evidence": evidence,
            }
        )
    return _csv(
        rows,
        ["rule", "severity", "message", "suggestion", "status", "evidence"],
    )


def inventory_csv(inventory: dict[str, list[dict[str, Any]]]) -> str:
    rows = []
    for kind, items in inventory.items():
        for item in items:
            rows.append(
                {
                    "kind": kind,
                    "name": item.get("name", ""),
                    "pages": item.get("page", ""),
                    "section_path": item.get("section_path", ""),
                    "occurrences": item.get("occurrences", 1),
                }
            )
    return _csv(rows, ["kind", "name", "pages", "section_path", "occurrences"])


def _csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buffer.getvalue()


def report_markdown(
    doc: dict[str, Any],
    inventory: dict[str, list[dict[str, Any]]],
    findings: list[dict[str, Any]],
    queries: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        f"# Architecture knowledge report: {doc.get('name', '')}",
        "",
        f"- Document ID: `{doc.get('id', '')}`",
        f"- Version: {doc.get('version_label') or 'n/a'} | Status: {doc.get('status', '')}",
        f"- Pages: {doc.get('pages', 0)} | Chunks: {doc.get('chunks', 0)}",
        "",
        "## Component and interface inventory",
        "",
    ]
    for kind in sorted(inventory):
        items = inventory[kind]
        lines.append(f"### {kind} ({len(items)})")
        for item in items:
            page = item.get("page", "?")
            section = item.get("section_path", "")
            suffix = f" — p.{page}" + (f", {section}" if section else "")
            lines.append(f"- {item.get('name', '')}{suffix}")
        lines.append("")

    lines += ["## Potential inconsistencies", ""]
    if not findings:
        lines.append("No issues detected by the automated checks.")
    for finding in findings:
        lines.append(f"### [{finding.get('severity', '').upper()}] {finding.get('rule', '')}")
        lines.append(finding.get("message", ""))
        for evidence in finding.get("evidence", []):
            lines.append(
                f"- evidence: p.{evidence.get('page')} "
                f"{evidence.get('section', '')} — {evidence.get('quote', '')}"
            )
        if finding.get("suggestion"):
            lines.append(f"- suggestion: {finding.get('suggestion')}")
        lines.append("")

    if queries:
        lines += ["## Reviewed Q&A history", ""]
        for query in queries:
            lines.append(f"**Q:** {query.get('question', '')}")
            lines.append("")
            lines.append(query.get("answer", ""))
            lines.append("")
            for citation in query.get("citations", []):
                lines.append(f"  - {citation}")
            lines.append("")

    lines += [
        "---",
        "AI-generated content is traceable to approved source material and must be",
        "reviewed by an authorised engineering specialist before use in compliance,",
        "design approval, software release or vehicle validation.",
    ]
    return "\n".join(lines)


def comparison_markdown(report: dict[str, Any]) -> str:
    a = report.get("revision_a", {})
    b = report.get("revision_b", {})
    summary = report.get("summary", {})
    lines = [
        f"# Revision comparison: {a.get('name')} → {b.get('name')}",
        "",
        f"- A: version {a.get('version') or 'n/a'} ({a.get('pages')} pages, {a.get('status')})",
        f"- B: version {b.get('version') or 'n/a'} ({b.get('pages')} pages, {b.get('status')})",
        "",
        "## Summary",
        "",
        "| Change | Count |",
        "| --- | --- |",
        f"| Entities added | {summary.get('entities_added', 0)} |",
        f"| Entities removed | {summary.get('entities_removed', 0)} |",
        f"| Entities modified | {summary.get('entities_modified', 0)} |",
        f"| Sections added | {summary.get('sections_added', 0)} |",
        f"| Sections removed | {summary.get('sections_removed', 0)} |",
        f"| Sections changed | {summary.get('sections_changed', 0)} |",
        "",
    ]
    entities = report.get("entities", {})
    if entities.get("added"):
        lines += ["## Added entities", ""]
        lines += [f"- {e.get('kind')}: {e.get('name')} (p.{e.get('page')})" for e in entities["added"]]
        lines.append("")
    if entities.get("removed"):
        lines += ["## Removed entities", ""]
        lines += [f"- {e.get('kind')}: {e.get('name')} (p.{e.get('page')})" for e in entities["removed"]]
        lines.append("")
    if entities.get("modified"):
        lines += ["## Modified entities", ""]
        lines += [
            f"- {m.get('name')}: {m.get('from_kind')} → {m.get('to_kind')}"
            for m in entities["modified"]
        ]
        lines.append("")
    sections = report.get("sections", {})
    if sections.get("added"):
        lines += ["## Added sections", ""] + [f"- {s}" for s in sections["added"]] + [""]
    if sections.get("removed"):
        lines += ["## Removed sections", ""] + [f"- {s}" for s in sections["removed"]] + [""]
    changed = report.get("sections_changed", [])
    if changed:
        lines += ["## Changed sections (lowest similarity first)", ""]
        for item in changed:
            lines.append(
                f"- {item['section']} — similarity {item['similarity']} "
                f"(+{item['lines_added']}/-{item['lines_removed']} lines)"
            )
        lines.append("")
    return "\n".join(lines)


def write_exports(
    export_dir: Path | str,
    doc: dict[str, Any],
    inventory: dict[str, list[dict[str, Any]]],
    entities: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    queries: list[dict[str, Any]] | None = None,
) -> list[Path]:
    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    stem = _slug(str(doc.get("name", "document")))
    written: list[Path] = []

    targets = {
        f"{stem}_entities.csv": entities_csv(entities),
        f"{stem}_findings.csv": findings_csv(findings),
        f"{stem}_inventory.csv": inventory_csv(inventory),
        f"{stem}_report.md": report_markdown(doc, inventory, findings, queries),
        f"{stem}_report.json": json.dumps(
            {
                "document": {k: doc.get(k) for k in
                             ("id", "name", "version_label", "status", "pages", "chunks")},
                "inventory": inventory,
                "entities": entities,
                "findings": findings,
            },
            indent=2,
        ),
    }
    for filename, content in targets.items():
        path = export_dir / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def write_comparison_export(
    export_dir: Path | str, report: dict[str, Any]
) -> list[Path]:
    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    stem = _slug(str(report.get("revision_a", {}).get("name", "rev_a")) + "_vs_" +
                 str(report.get("revision_b", {}).get("name", "rev_b")))
    targets = {
        f"{stem}_comparison.json": json.dumps(report, indent=2),
        f"{stem}_comparison.md": comparison_markdown(report),
    }
    written = []
    for filename, content in targets.items():
        path = export_dir / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def _slug(value: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_" else "_" for c in value)
    return keep.strip("_")[:80] or "document"
