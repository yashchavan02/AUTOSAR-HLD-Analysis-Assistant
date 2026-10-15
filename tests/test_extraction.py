from hld_assistant.ingest.chunker import chunk_document
from hld_assistant.ingest.pdf_extractor import build_section_paths, extract_pdf


def test_extract_pdf_finds_headings_and_tables(sample_pdfs):
    doc = extract_pdf(sample_pdfs["a"])
    assert doc.page_count >= 3
    labels = [h.label for h in doc.headings]
    assert "3.1 Component breakdown" in labels
    assert "6 Basic software integration" in labels
    assert any(doc.pages[i].tables for i in range(doc.page_count))
    component_table = next(t for p in doc.pages for t in p.tables if t[0][0] == "Component")
    assert ["Component", "Type", "Description"] == component_table[0]
    assert any(row[0] == "VehicleSpeedManager" for row in component_table[1:])


def test_section_paths_breadcrumb(sample_pdfs):
    doc = extract_pdf(sample_pdfs["a"])
    paths = dict(build_section_paths(doc))
    joined = [" > ".join(p) for p in paths.values()]
    assert any("3 Software architecture" in p and "3.1 Component breakdown" in p for p in joined)


def test_chunks_carry_section_and_pages(sample_pdfs):
    doc = extract_pdf(sample_pdfs["a"])
    chunks = chunk_document(doc, chunk_chars=600, overlap=80)
    assert len(chunks) >= 10
    assert len({c.id for c in chunks}) == len(chunks)
    assert all(1 <= c.page_start <= doc.page_count for c in chunks)
    assert any(c.kind == "table" for c in chunks)
    assert any("3.1 Component breakdown" in c.section_path for c in chunks)
    assert all(c.text.strip() for c in chunks)
