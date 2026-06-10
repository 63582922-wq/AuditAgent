import json

from app.services.agent.mcp_hub import McpHub, McpServerConfig, parse_mcp_servers


def test_parse_mcp_servers_empty():
    assert parse_mcp_servers("[]") == []
    assert parse_mcp_servers("") == []


def test_parse_mcp_servers_valid():
    raw = json.dumps([{"name": "demo", "url": "http://localhost:9000/mcp", "api_key": "k"}])
    servers = parse_mcp_servers(raw)
    assert len(servers) == 1
    assert servers[0].name == "demo"
    assert servers[0].url == "http://localhost:9000/mcp"


def test_mcp_hub_local_tools(db):
    from app.models import FileRecord, Project

    project = Project(name="mcp-test", status="created")
    db.add(project)
    db.commit()
    files = [
        FileRecord(
            project_id=project.id,
            file_name="a.csv",
            file_type="csv",
            storage_path="/tmp/a.csv",
            document_category="expense_detail",
        )
    ]
    hub = McpHub.for_agent(db, project.id, "tax", files)
    names = hub.list_tool_names()
    assert "search_memory" in names
    assert "inspect_agent_domain" in names


def test_mcp_hub_call_local_tool(db, monkeypatch):
    from app.models import FileRecord, Project

    monkeypatch.setattr(
        "app.services.agent.tool_registry.retrieve_memories",
        lambda db, **kwargs: [],
    )
    monkeypatch.setattr(
        "app.services.agent.tool_registry.format_memories_for_prompt",
        lambda mems: "无记忆",
    )

    project = Project(name="mcp-call", status="created")
    db.add(project)
    db.commit()
    files = [
        FileRecord(
            project_id=project.id,
            file_name="a.csv",
            file_type="csv",
            storage_path="/tmp/a.csv",
            document_category="expense_detail",
        )
    ]
    hub = McpHub.for_agent(db, project.id, "invoice", files)
    result = hub.call_tool("search_memory", {"query": "发票重复"})
    assert "无记忆" in result or "[]" in result
