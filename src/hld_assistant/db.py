"""SQLite persistence for documents, chunks, entities, queries and reviews."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    version_label TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',
    pages         INTEGER NOT NULL DEFAULT 0,
    scanned_pages INTEGER NOT NULL DEFAULT 0,
    headings      INTEGER NOT NULL DEFAULT 0,
    chunks        INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id           TEXT PRIMARY KEY,
    doc_id       TEXT NOT NULL,
    ordinal      INTEGER NOT NULL,
    section_path TEXT NOT NULL,
    page_start   INTEGER NOT NULL,
    page_end     INTEGER NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'text',
    text         TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

CREATE TABLE IF NOT EXISTS entities (
    id           TEXT PRIMARY KEY,
    doc_id       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    name         TEXT NOT NULL,
    norm_name    TEXT NOT NULL,
    page         INTEGER NOT NULL,
    section_path TEXT NOT NULL DEFAULT '',
    context      TEXT NOT NULL DEFAULT '',
    confidence   REAL NOT NULL DEFAULT 1.0,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_entities_doc ON entities(doc_id);
CREATE INDEX IF NOT EXISTS idx_entities_norm ON entities(norm_name);

CREATE TABLE IF NOT EXISTS queries (
    id         TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    citations  TEXT NOT NULL DEFAULT '[]',
    grounded   INTEGER NOT NULL DEFAULT 0,
    mode       TEXT NOT NULL DEFAULT 'generate'
);

CREATE TABLE IF NOT EXISTS reviews (
    id         TEXT PRIMARY KEY,
    target     TEXT NOT NULL,
    target_id  TEXT NOT NULL DEFAULT '',
    verdict    TEXT NOT NULL,
    comment    TEXT NOT NULL DEFAULT '',
    reviewer   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id        TEXT PRIMARY KEY,
    doc_id    TEXT NOT NULL,
    rule      TEXT NOT NULL,
    severity  TEXT NOT NULL,
    message   TEXT NOT NULL,
    evidence  TEXT NOT NULL DEFAULT '[]',
    suggestion TEXT NOT NULL DEFAULT '',
    status    TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_doc ON findings(doc_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Store:
    """Thin persistence layer. A fresh connection per operation keeps it
    safe under Streamlit's thread-per-request execution model."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    # -- documents ------------------------------------------------------
    def add_document(self, **doc: Any) -> str:
        doc_id = doc.get("id") or _new_id("doc")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO documents (id, name, source_path, sha256, version_label,
                       status, pages, scanned_pages, headings, chunks, metadata_json, created_at)
                   VALUES (:id, :name, :source_path, :sha256, :version_label, :status,
                       :pages, :scanned_pages, :headings, :chunks, :metadata_json, :created_at)""",
                {
                    "id": doc_id,
                    "name": doc.get("name", ""),
                    "source_path": doc.get("source_path", ""),
                    "sha256": doc.get("sha256", ""),
                    "version_label": doc.get("version_label", ""),
                    "status": doc.get("status", "draft"),
                    "pages": int(doc.get("pages", 0)),
                    "scanned_pages": int(doc.get("scanned_pages", 0)),
                    "headings": int(doc.get("headings", 0)),
                    "chunks": int(doc.get("chunks", 0)),
                    "metadata_json": json.dumps(doc.get("metadata", {})),
                    "created_at": doc.get("created_at") or _now(),
                },
            )
        return doc_id

    def update_document(self, doc_id: str, **fields: Any) -> None:
        if not fields:
            return
        if "metadata" in fields:
            fields["metadata_json"] = json.dumps(fields.pop("metadata"))
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.connect() as conn:
            conn.execute(f"UPDATE documents SET {cols} WHERE id = ?", (*fields.values(), doc_id))

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return self._doc_row(row) if row else None

    def list_documents(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [self._doc_row(r) for r in rows]

    def delete_document(self, doc_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    @staticmethod
    def _doc_row(row: sqlite3.Row) -> dict[str, Any]:
        doc = dict(row)
        doc["metadata"] = json.loads(doc.pop("metadata_json") or "{}")
        return doc

    # -- chunks ---------------------------------------------------------
    def add_chunks(self, doc_id: str, chunks: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.executemany(
                """INSERT INTO chunks (id, doc_id, ordinal, section_path, page_start,
                       page_end, kind, text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        c["id"],
                        doc_id,
                        c["ordinal"],
                        c["section_path"],
                        c["page_start"],
                        c["page_end"],
                        c.get("kind", "text"),
                        c["text"],
                    )
                    for c in chunks
                ],
            )

    def get_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE doc_id = ? ORDER BY ordinal", (doc_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def all_chunks(self, doc_ids: list[str] | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM chunks"
        args: tuple[Any, ...] = ()
        if doc_ids:
            marks = ", ".join("?" for _ in doc_ids)
            query += f" WHERE doc_id IN ({marks})"
            args = tuple(doc_ids)
        query += " ORDER BY doc_id, ordinal"
        with self.connect() as conn:
            rows = conn.execute(query, args).fetchall()
        return [dict(r) for r in rows]

    def count_chunks(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
        return int(row["n"]) if row else 0

    # -- entities -------------------------------------------------------
    def replace_entities(self, doc_id: str, entities: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM entities WHERE doc_id = ?", (doc_id,))
            conn.executemany(
                """INSERT INTO entities (id, doc_id, kind, name, norm_name, page,
                       section_path, context, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        e.get("id") or _new_id("ent"),
                        doc_id,
                        e["kind"],
                        e["name"],
                        e["norm_name"],
                        e.get("page", 0),
                        e.get("section_path", ""),
                        e.get("context", ""),
                        float(e.get("confidence", 1.0)),
                    )
                    for e in entities
                ],
            )

    def get_entities(self, doc_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM entities WHERE doc_id = ? ORDER BY kind, name", (doc_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -- queries --------------------------------------------------------
    def add_query(self, question: str, answer: str, citations: list[dict[str, Any]],
                  grounded: bool, mode: str) -> str:
        qid = _new_id("q")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO queries (id, created_at, question, answer, citations, grounded, mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (qid, _now(), question, answer, json.dumps(citations), int(grounded), mode),
            )
        return qid

    def list_queries(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM queries ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["citations"] = json.loads(item.get("citations") or "[]")
            item["grounded"] = bool(item["grounded"])
            out.append(item)
        return out

    # -- reviews --------------------------------------------------------
    def add_review(self, target: str, target_id: str, verdict: str, comment: str,
                   reviewer: str) -> str:
        rid = _new_id("rev")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO reviews (id, target, target_id, verdict, comment, reviewer, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (rid, target, target_id, verdict, comment, reviewer, _now()),
            )
        return rid

    def list_reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -- findings -------------------------------------------------------
    def replace_findings(self, doc_id: str, findings: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM findings WHERE doc_id = ?", (doc_id,))
            conn.executemany(
                """INSERT INTO findings (id, doc_id, rule, severity, message, evidence,
                       suggestion, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        f.get("id") or _new_id("fnd"),
                        doc_id,
                        f["rule"],
                        f["severity"],
                        f["message"],
                        json.dumps(f.get("evidence", [])),
                        f.get("suggestion", ""),
                        f.get("status", "open"),
                        _now(),
                    )
                    for f in findings
                ],
            )

    def get_findings(self, doc_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM findings WHERE doc_id = ? ORDER BY severity, rule", (doc_id,)
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["evidence"] = json.loads(item.get("evidence") or "[]")
            out.append(item)
        return out
