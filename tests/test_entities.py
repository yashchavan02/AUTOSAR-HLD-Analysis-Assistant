from hld_assistant.analysis.entities import extract_entities, normalize_name
from hld_assistant.ingest.pdf_extractor import extract_pdf


def _entities(sample_pdfs, revision: str = "a") -> list[dict]:
    doc = extract_pdf(sample_pdfs[revision])
    return extract_entities(doc)


def test_component_and_port_entities_from_tables(sample_pdfs):
    entities = _entities(sample_pdfs)
    by_kind: dict[str, set[str]] = {}
    for entity in entities:
        by_kind.setdefault(entity["kind"], set()).add(entity["name"])
    assert "VehicleSpeedManager" in by_kind["Component"]
    assert "VehicleMotionComposition" in by_kind["Component"]
    assert "VehicleSpeedOut" in by_kind["Port"]
    assert "WheelSpeedFL" in by_kind["Signal"]
    assert "VehicleSpeedI" in by_kind["Interface"]


def test_bsw_and_runnable_entities_from_prose(sample_pdfs):
    entities = _entities(sample_pdfs)
    names = {(e["kind"], e["name"]) for e in entities}
    assert ("BswModule", "PduR") in names
    assert ("BswModule", "Rte") in names
    assert any(kind == "Runnable" for kind, _ in names)
    assert any(kind == "Event" for kind, _ in names)


def test_entities_carry_citation_context(sample_pdfs):
    entities = _entities(sample_pdfs)
    vehicle_speed = next(e for e in entities if e["name"] == "VehicleSpeedManager")
    assert vehicle_speed["page"] >= 1
    assert vehicle_speed["confidence"] > 0.9
    assert vehicle_speed["context"]


def test_normalize_name_collapses_separators():
    assert normalize_name("Vehicle_Speed") == normalize_name("vehicle speed")
