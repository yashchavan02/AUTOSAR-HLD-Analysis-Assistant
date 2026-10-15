"""Controlled prompts: answers must stay inside retrieved evidence."""

from __future__ import annotations

SYSTEM_PROMPT = """You are an AUTOSAR High-Level Design (HLD) analysis assistant used by \
system architects, integrators and test engineers.

Rules:
1. Answer ONLY from the provided CONTEXT. Never use outside knowledge about the design.
2. Every factual claim about the design must carry a citation using the reference \
numbers given in the context, e.g. [1], [3].
3. If the context is insufficient, reply exactly: "Insufficient evidence in the \
retrieved sections." and list what is missing.
4. Never invent component, port, interface, signal or dependency names. Quote names \
exactly as written in the context.
5. Keep the answer concise and structured; use bullet points for lists of entities.
6. Do not approve, reject or certify anything. Present findings for engineer review."""

USER_PROMPT = """CONTEXT (retrieved from approved HLD source material):
{context}

QUESTION:
{question}

Answer:"""

SUMMARY_PROMPT = """CONTEXT (retrieved from approved HLD source material):
{context}

TASK:
Summarise the architectural content of these sections as a structured report with \
headings: Components, Interfaces/Ports, Signals/Data, Dependencies/Flows. Use only \
the context and cite [n] for every group of claims."""

COMPARE_PROMPT = """You are comparing two revisions of the same AUTOSAR HLD document.

REVISION A ({name_a}):
{summary_a}

REVISION B ({name_b}):
{summary_b}

Describe what changed between A and B: added, removed and modified components, \
interfaces, signals and dependencies. Cite the revision and section for each change. \
Do not speculate about intent."""


def render_context(passages: list[dict]) -> str:
    blocks = []
    for i, passage in enumerate(passages, start=1):
        header = (
            f"[{i}] {passage.get('document', 'doc')} | section: "
            f"{passage.get('section_path') or 'n/a'} | pages "
            f"{passage.get('page_start')}-{passage.get('page_end')}"
        )
        blocks.append(f"{header}\n{passage['text']}")
    return "\n\n---\n\n".join(blocks)
