from hld_assistant.export import exporter


def test_entities_csv_has_expected_columns():
    csv_text = exporter.entities_csv(
        [
            {
                "kind": "Component",
                "name": "VehicleSpeedManager",
                "norm_name": "vehiclespeedmanager",
                "page": 3,
                "section_path": "3 Software architecture > 3.1 Component breakdown",
                "confidence": 0.95,
                "context": "VehicleSpeedManager | ApplicationSwComponentType",
            }
        ]
    )
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("kind,name,norm_name,page")
    assert "VehicleSpeedManager" in lines[1]


def test_findings_csv_flattens_evidence():
    csv_text = exporter.findings_csv(
        [
            {
                "rule": "empty_section",
                "severity": "info",
                "message": "Section '9 Open questions' has little or no content.",
                "suggestion": "Complete the section.",
                "status": "open",
                "evidence": [{"page": 5, "section": "9 Open questions", "quote": "9 Open questions"}],
            }
        ]
    )
    assert "empty_section" in csv_text
    assert "p.5" in csv_text


def test_report_markdown_contains_inventory_and_governance_note():
    text = exporter.report_markdown(
        {"id": "doc_1", "name": "hld.pdf", "version_label": "A", "status": "approved",
         "pages": 3, "chunks": 12},
        {"Component": [{"name": "VehicleSpeedManager", "page": 3,
                        "section_path": "3.1 Component breakdown", "occurrences": 2}]},
        [{"rule": "terminology_variance", "severity": "warning", "message": "spelling drift",
          "evidence": [{"page": 2, "section": "", "quote": "Vehicle_Speed"}],
          "suggestion": "align", "status": "open"}],
    )
    assert "# Architecture knowledge report: hld.pdf" in text
    assert "VehicleSpeedManager" in text
    assert "terminology_variance" in text
    assert "reviewed by an authorised engineering specialist" in text


def test_comparison_markdown_summary_table():
    text = exporter.comparison_markdown(
        {
            "revision_a": {"name": "a.pdf", "version": "A", "pages": 3, "status": "approved"},
            "revision_b": {"name": "b.pdf", "version": "B", "pages": 3, "status": "draft"},
            "summary": {"entities_added": 2, "entities_removed": 1, "entities_modified": 0,
                        "sections_added": 2, "sections_removed": 1, "sections_changed": 3},
            "entities": {"added": [], "removed": [], "modified": []},
            "sections": {"added": ["4.3 Traction control flow"], "removed": ["9 Open questions"],
                         "common": []},
            "sections_changed": [],
        }
    )
    assert "| Entities added | 2 |" in text
    assert "4.3 Traction control flow" in text
