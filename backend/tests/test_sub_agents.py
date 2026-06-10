from app.models import FileRecord
from app.services.agent.sub_agents import enrich_plan_with_sub_agents, route_sub_agents


def test_route_sub_agents_tax_and_invoice():
    files = [
        FileRecord(file_name="a.csv", document_category="expense_detail", confidence=0.9),
        FileRecord(file_name="b.csv", document_category="invoice_list", confidence=0.9),
    ]
    agents = route_sub_agents(files, {"focus_areas": ["税务风险"]})
    ids = {a["id"] for a in agents}
    assert "tax" in ids
    assert "invoice" in ids


def test_enrich_plan_adds_sub_agents():
    plan = {"focus_areas": ["合同风险"], "reasoning": ""}
    files = [FileRecord(file_name="c.docx", document_category="contract", confidence=0.9)]
    out = enrich_plan_with_sub_agents(plan, files)
    assert out["sub_agents"]
    assert out["sub_agents"][0]["id"] == "contract"
