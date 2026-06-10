from app.models import FileRecord
from app.services.agent.execution_graph import ExecutionGraph


def test_execution_graph_from_plan_steps():
    plan = {
        "steps": ["parse", "run_rules", "adjudicate", "report"],
        "focus_areas": ["税务风险"],
        "priority_actions": ["交叉比对金额"],
        "reasoning": "重点查税务",
        "agent_mode": "agent",
    }
    files = [
        FileRecord(file_name="a.csv", document_category="expense_detail", confidence=0.9),
        FileRecord(file_name="b.csv", document_category="invoice_list", confidence=0.9),
    ]
    graph = ExecutionGraph.from_plan(plan, files)

    assert graph.should_run("parsing")
    assert graph.should_run("running_rules")
    assert not graph.should_run("cross_checking")  # plan 未含 cross_check
    assert graph.should_run("adjudicating")
    assert "amounts" not in graph.cross_modules  # cross_checking skipped entirely


def test_execution_graph_cross_modules_single_file():
    plan = {"steps": ["cross_check"], "focus_areas": [], "agent_mode": "agent"}
    files = [FileRecord(file_name="a.csv", document_category="expense_detail", confidence=0.9)]
    graph = ExecutionGraph.from_plan(plan, files)

    assert graph.should_run("cross_checking")
    assert "three_way" not in graph.cross_modules
    assert "anomalies" in graph.cross_modules


def test_execution_graph_rule_boost():
    plan = {"focus_areas": ["税务风险"], "agent_mode": "agent"}
    graph = ExecutionGraph.from_plan(plan, [])
    rules = [
        {"rule_id": "A", "risk_category": "会计核算风险", "priority": 90},
        {"rule_id": "B", "risk_category": "税务风险", "priority": 50},
    ]
    sorted_rules = graph.sort_rules(rules)
    assert sorted_rules[0]["rule_id"] == "B"
