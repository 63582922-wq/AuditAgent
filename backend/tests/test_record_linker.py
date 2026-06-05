from app.services.cross_period_checker import detect_three_way_gaps
from app.services.record_linker import build_record_links


def test_build_record_links_by_invoice_number():
    entities = [
        {
            "project_id": "p1",
            "file_id": "f1",
            "entity_type": "invoice_number",
            "entity_value": "12345",
            "source_location": {},
        },
        {
            "project_id": "p1",
            "file_id": "f2",
            "entity_type": "invoice_number",
            "entity_value": "12345",
            "source_location": {},
        },
    ]
    links = build_record_links("p1", entities)
    assert any(l["link_type"] == "invoice_number_match" for l in links)


def test_three_way_gap_detection():
    docs = [
        {"file_id": "c1", "document_category": "contract", "file_name": "c.pdf"},
        {"file_id": "i1", "document_category": "invoice_list", "file_name": "i.xlsx"},
    ]
    risks = detect_three_way_gaps(docs, links=[])
    assert any(r["rule_triggered"] == "3WAY-001" for r in risks)
