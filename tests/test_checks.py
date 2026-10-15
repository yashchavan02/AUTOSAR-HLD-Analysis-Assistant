from hld_assistant.analysis.checks import run_checks
from hld_assistant.analysis.entities import extract_entities
from hld_assistant.ingest.chunker import chunk_document
from hld_assistant.ingest.pdf_extractor import extract_pdf


def _analyze(sample_pdfs, revision: str):
    doc = extract_pdf(sample_pdfs[revision])
    chunks = chunk_document(doc)
    entities = extract_entities(doc)
    return doc, chunks, entities, run_checks(doc, chunks, entities)


def test_revision_a_findings(sample_pdfs):
    _, _, _, findings = _analyze(sample_pdfs, "a")
    rules = {f["rule"] for f in findings}
    assert "port_direction_conflict" in rules
    assert "entity_kind_conflict" in rules
    assert "empty_section" in rules
    assert "undefined_reference" in rules
    for finding in findings:
        assert finding["severity"] in {"error", "warning", "info"}
        assert finding["message"]
        assert finding["evidence"]


def test_revision_b_adds_terminology_and_new_reference(sample_pdfs):
    _, _, _, findings = _analyze(sample_pdfs, "b")
    rules = {f["rule"] for f in findings}
    assert "terminology_variance" in rules
    undefined = [
        f for f in findings if f["rule"] == "undefined_reference"
        and "TractionControlUnit" in f["message"]
    ]
    assert undefined
    terminology = next(f for f in findings if f["rule"] == "terminology_variance")
    assert "ChassisSignalService" in terminology["message"]


def test_port_direction_finding_names_the_port(sample_pdfs):
    _, _, _, findings = _analyze(sample_pdfs, "a")
    conflict = next(f for f in findings if f["rule"] == "port_direction_conflict")
    assert "VehicleSpeedOut" in conflict["message"]
    assert conflict["severity"] == "error"
    assert len(conflict["evidence"]) == 2


def test_findings_are_sorted_by_severity(sample_pdfs):
    _, _, _, findings = _analyze(sample_pdfs, "a")
    order = {"error": 0, "warning": 1, "info": 2}
    severities = [order[f["severity"]] for f in findings]
    assert severities == sorted(severities)
