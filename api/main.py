"""FastAPI service endpoints for the HLD analysis assistant."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from hld_assistant.config import get_settings
from hld_assistant.services import AssistantServices

settings = get_settings()
services = AssistantServices(settings)

app = FastAPI(
    title="AUTOSAR HLD Analysis Assistant",
    version="0.1.0",
    description=(
        "Ingestion, retrieval, cited Q&A, consistency checks and revision "
        "comparison for AUTOSAR High-Level Design documents."
    ),
)


class QueryBody(BaseModel):
    question: str = Field(min_length=3)
    doc_ids: list[str] | None = None
    k: int | None = Field(default=None, ge=1, le=30)


class ReviewBody(BaseModel):
    target: str
    target_id: str = ""
    verdict: str
    comment: str = ""
    reviewer: str = ""


@app.get("/health")
def health() -> dict[str, Any]:
    return services.status()


@app.get("/documents")
def documents() -> list[dict[str, Any]]:
    return services.list_documents()


@app.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    version_label: str = Form(default=""),
    status: str = Form(default="draft"),
) -> dict[str, Any]:
    suffix = Path(file.filename or "document.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        content = await file.read()
        handle.write(content)
        tmp_path = Path(handle.name)
    try:
        result = services.ingest(
            tmp_path,
            name=file.filename,
            version_label=version_label,
            status=status,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Ingestion failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    return result


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str) -> dict[str, Any]:
    if not services.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    services.delete_document(doc_id)
    return {"deleted": doc_id}


@app.post("/search")
def search(body: QueryBody) -> list[dict[str, Any]]:
    passages = services.search(body.question, doc_ids=body.doc_ids, k=body.k)
    return [p.to_dict() for p in passages]


@app.post("/ask")
def ask(body: QueryBody) -> dict[str, Any]:
    return services.ask(body.question, doc_ids=body.doc_ids, k=body.k)


@app.get("/documents/{doc_id}/inventory")
def inventory(doc_id: str) -> dict[str, Any]:
    if not services.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return services.inventory(doc_id)


@app.post("/documents/{doc_id}/checks")
def checks(doc_id: str) -> list[dict[str, Any]]:
    try:
        return services.checks(doc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CompareBody(BaseModel):
    doc_id_a: str
    doc_id_b: str


@app.post("/compare")
def compare(body: CompareBody) -> dict[str, Any]:
    try:
        return services.compare(body.doc_id_a, body.doc_id_b)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/documents/{doc_id}/export")
def export(doc_id: str) -> dict[str, Any]:
    try:
        paths = services.export_document(doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"exported": [str(p) for p in paths]}


@app.get("/exports/{name}")
def read_export(name: str) -> PlainTextResponse:
    path = (settings.export_dir / name).resolve()
    if not str(path).startswith(str(settings.export_dir.resolve())) or not path.is_file():
        raise HTTPException(status_code=404, detail="Export not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.get("/queries")
def queries(limit: int = 50) -> list[dict[str, Any]]:
    return services.list_queries(limit)


@app.post("/reviews")
def add_review(body: ReviewBody) -> dict[str, Any]:
    review_id = services.add_review(
        target=body.target,
        target_id=body.target_id,
        verdict=body.verdict,
        comment=body.comment,
        reviewer=body.reviewer,
    )
    return {"id": review_id}


@app.get("/reviews")
def reviews(limit: int = 100) -> list[dict[str, Any]]:
    return services.list_reviews(limit)


@app.get("/")
def root() -> JSONResponse:
    return JSONResponse(
        {
            "service": settings.app_title,
            "docs": "/docs",
            "health": "/health",
        }
    )
