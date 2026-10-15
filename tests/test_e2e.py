"""End-to-end workflow test through the service layer."""


def test_full_workflow(services, sample_pdfs):
    result_a = services.ingest(
        sample_pdfs["a"], name="hld_revision_a.pdf", version_label="A", status="approved"
    )
    assert result_a["pages"] >= 3
    assert result_a["chunks"] >= 8
    assert result_a["entities"] > 20

    duplicate = services.ingest(sample_pdfs["a"], name="same-content.pdf")
    assert "duplicate_of" in duplicate

    result_b = services.ingest(
        sample_pdfs["b"], name="hld_revision_b.pdf", version_label="B", status="draft"
    )
    assert services.status()["documents"] == 2

    passages = services.search(
        "vehicle speed signal routing", doc_ids=[result_a["doc_id"]]
    )
    assert passages
    assert passages[0].citation.startswith("hld_revision_a.pdf")
    assert all(p.chunk_id and p.text for p in passages)

    answer = services.ask("Which component publishes the VehicleSpeed signal?")
    assert answer["mode"] == "retrieval"
    assert answer["grounded"] is True
    assert answer["citations"]
    assert "VehicleSpeed" in answer["answer"]
    assert services.list_queries(5)

    inventory = services.inventory(result_a["doc_id"])
    component_names = {e["name"] for e in inventory.get("Component", [])}
    assert "VehicleSpeedManager" in component_names

    findings = services.checks(result_b["doc_id"])
    assert findings
    assert {f["rule"] for f in findings} & {"terminology_variance", "undefined_reference"}
    assert services.get_findings(result_b["doc_id"])

    report = services.compare(result_a["doc_id"], result_b["doc_id"])
    assert report["summary"]["entities_added"] >= 1
    assert report["summary"]["entities_removed"] >= 1

    export_files = services.export_document(result_a["doc_id"])
    assert len(export_files) >= 5
    assert all(path.is_file() for path in export_files)
    report_files = services.export_comparison(report)
    assert len(report_files) == 2

    services.delete_document(result_b["doc_id"])
    assert services.get_document(result_b["doc_id"]) is None
    assert services.status()["documents"] == 1
