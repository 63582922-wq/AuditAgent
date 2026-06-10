from app.services.agent.skill_registry import (
    get_tools_for_agent,
    list_registered_agents,
    register_sub_agent,
    register_main_agent,
)


def test_register_sub_agent_tax():
    reg = register_sub_agent("tax")
    assert reg.agent_id == "tax"
    assert reg.name == "税务专员"
    assert "inspect_agent_domain" in reg.tool_names
    assert "tax_return" in reg.doc_types


def test_get_tools_for_agent():
    tools = get_tools_for_agent("invoice")
    names = {t["function"]["name"] for t in tools}
    assert "search_memory" in names
    assert "inspect_agent_domain" in names


def test_list_registered_agents():
    agents = list_registered_agents(["tax", "invoice"])
    assert agents[0]["id"] == "main"
    ids = {a["id"] for a in agents}
    assert "tax" in ids
    assert "invoice" in ids


def test_main_agent_tools():
    main = register_main_agent()
    assert main.agent_id == "main"
    assert "list_uploaded_files" in main.tool_names
