from app.services.cross_checker import cross_check_amounts, detect_duplicate_invoices


def test_detect_duplicate_invoices_from_invoice_list():
    rows = [
        {"invoice_number": "INV001", "row": 2, "file_name": "inv.csv"},
        {"invoice_number": "INV001", "row": 5, "file_name": "inv.csv"},
        {"invoice_number": "INV003", "row": 3, "file_name": "inv.csv"},
    ]
    risks = detect_duplicate_invoices(rows)
    assert len(risks) == 1
    assert risks[0]["rule_triggered"] == "INV-001"
    assert risks[0]["risk_id"].startswith("INV-001-")


def test_amt002_only_same_invoice_number():
    docs = [
        {
            "file_id": "f1",
            "file_name": "expense.csv",
            "document_category": "expense_detail",
            "content_json": {
                "sheets": [
                    {
                        "sheet_name": "Sheet1",
                        "rows": [
                            {
                                "row_number": 2,
                                "values": {"金额": 32000, "发票号": "INV005", "摘要": "咨询"},
                            },
                            {
                                "row_number": 3,
                                "values": {"金额": 128000, "摘要": "咨询"},
                            },
                        ],
                    }
                ]
            },
        },
        {
            "file_id": "f2",
            "file_name": "invoice.csv",
            "document_category": "invoice_list",
            "content_json": {
                "sheets": [
                    {
                        "sheet_name": "Sheet1",
                        "rows": [
                            {"row_number": 3, "values": {"价税合计": 28000, "发票号码": "INV005"}},
                            {"row_number": 4, "values": {"价税合计": 106000, "发票号码": "88888888"}},
                        ],
                    }
                ]
            },
        },
    ]
    risks = cross_check_amounts(docs)
    amt002 = [r for r in risks if r["rule_triggered"] == "AMT-002"]
    assert len(amt002) == 1
    assert amt002[0]["evidence_json"]["invoice_number"] == "INV005"
