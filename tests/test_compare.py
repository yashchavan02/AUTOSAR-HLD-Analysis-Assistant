from pathlib import Path

from hld_assistant.analysis.compare import build_comparison
from hld_assistant.analysis.entities import extract_entities
from hld_assistant.ingest.chunker import chunk_document
from hld_assistant.ingest.pdf_extractor import extract_pdf


def _snapshot(path: Path) -> dict:
    doc = extract_pdf(path)
    meta = {"name": path.name, "version_label": path.suffix, "status": "approved",
            "pages": doc.page_count}
    headings = [{"label": h.label, "page": h.page, "level": h.level} for h in doc.headings]
    return {
        "meta": meta,
        "headings": headings,
        "entities": extract_entities(doc),
        "chunks": [c.__dict__ for c in chunk_document(doc)],
    }


def test_comparison_reports_added_removed_and_changed(sample_pdfs):
    a = _snapshot(sample_pdfs["a"])
    b = _snapshot(sample_pdfs["b"])
    report = build_comparison(
        a["meta"], b["meta"],
        a["entities"], b["entities"],
        a["headings"], b["headings"],
        a["chunks"], b["chunks"],
    )
    added = {e["name"] for e in report["entities"]["added"]}
    removed = {e["name"] for e in report["entities"]["removed"]}
    assert "TractionControlAssist" in added
    assert "SteeringAnglePreprocessor" in added
    assert "SteeringAngleReader" in removed
    assert "4.3 Traction control flow" in report["sections"]["added"]
    assert "9 Open questions" in report["sections"]["removed"]
    assert report["summary"]["sections_changed"] >= 1
    assert report["summary"]["entities_added"] >= 2


def test_comparison_similarity_between_zero_and_one(sample_pdfs):
    a = _snapshot(sample_pdfs["a"])
    b = _snapshot(sample_pdfs["b"])
    report = build_comparison(
        a["meta"], b["meta"],
        a["entities"], b["entities"],
        a["headings"], b["headings"],
        a["chunks"], b["chunks"],
    )
    for item in report["sections_changed"]:
        assert 0.0 <= item["similarity"] < 1.0
        assert item["diff"]
