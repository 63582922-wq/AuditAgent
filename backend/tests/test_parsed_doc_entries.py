from app.services.parsers.parsed_doc_entries import expand_parsed_doc_entries, flatten_parsed_docs


def test_expand_plain_doc_unchanged():
    doc = {
        "file_id": "f1",
        "file_name": "a.xlsx",
        "document_category": "a1_meeting_export",
        "content_json": {"text_content": "hello"},
        "text_content": "hello",
    }
    assert expand_parsed_doc_entries(doc) == [doc]


def test_expand_hybrid_pdf():
    doc = {
        "file_id": "f1",
        "file_name": "slides.pdf",
        "document_category": "meeting_agenda",
        "content_json": {
            "ingest_mode": "hybrid",
            "text_content": "议程第一页",
            "pages": [{"page_number": 1, "text": "议程"}],
            "vision_slices": [
                {
                    "slice_id": "p2-page",
                    "page_number": 2,
                    "ingest_mode": "vision_page",
                    "document_category": "sign_in_record",
                    "content_json": {
                        "text_content": "签到 7 人",
                        "fields": {"actual_sign_in_count": 7},
                    },
                }
            ],
        },
        "text_content": "议程第一页",
    }
    entries = expand_parsed_doc_entries(doc)
    assert len(entries) == 2
    assert entries[0]["ingest_mode"] == "text"
    assert entries[1]["ingest_mode"] == "vision_page"
    assert entries[1]["content_json"]["fields"]["actual_sign_in_count"] == 7


def test_flatten_multiple_files():
    docs = [
        {"file_id": "a", "content_json": {"text_content": "x"}},
        {
            "file_id": "b",
            "content_json": {
                "ingest_mode": "vision_only",
                "vision_slices": [
                    {
                        "slice_id": "p1-page",
                        "page_number": 1,
                        "ingest_mode": "vision_page",
                        "content_json": {"text_content": "scan"},
                    }
                ],
            },
        },
    ]
    flat = flatten_parsed_docs(docs)
    assert len(flat) == 2
