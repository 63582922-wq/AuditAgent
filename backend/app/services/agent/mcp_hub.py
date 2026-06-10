from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FileRecord
from app.services.agent.skill_registry import build_agent_handlers, get_tools_for_agent
from app.services.agent.tool_registry import execute_tool_call

logger = logging.getLogger("fxpg.mcp")


@dataclass
class McpServerConfig:
    name: str
    url: str
    api_key: str = ""
    enabled: bool = True


def parse_mcp_servers(raw: str | None = None) -> List[McpServerConfig]:
    text = raw if raw is not None else getattr(settings, "mcp_servers", "[]")
    if not text or text.strip() in ("", "[]"):
        return []
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("MCP_SERVERS JSON 无效，已忽略")
        return []
    out: List[McpServerConfig] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        out.append(
            McpServerConfig(
                name=str(item.get("name") or item["url"]),
                url=str(item["url"]).rstrip("/"),
                api_key=str(item.get("api_key") or ""),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return out


class ExternalMcpClient:
    """HTTP JSON-RPC MCP 客户端（tools/list + tools/call）。"""

    def __init__(self, config: McpServerConfig):
        self.config = config
        self._tools: List[Dict[str, Any]] = []
        self._loaded = False

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(self.config.url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            body = resp.json()
            if "error" in body:
                raise RuntimeError(body["error"])
            return body.get("result")

    def load_tools(self) -> List[Dict[str, Any]]:
        if self._loaded:
            return self._tools
        try:
            result = self._rpc("tools/list")
            tools = result.get("tools") if isinstance(result, dict) else result
            if isinstance(tools, list):
                self._tools = [t for t in tools if isinstance(t, dict)]
        except Exception as exc:
            logger.warning("MCP %s tools/list 失败: %s", self.config.name, exc)
            self._tools = []
        self._loaded = True
        return self._tools

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict)]
                return "\n".join(t for t in texts if t)
            return json.dumps(result, ensure_ascii=False)
        return str(result)


class McpHub:
    """统一 MCP 工具层：本地 Skill 工具 + 可选外部 MCP Server。"""

    def __init__(
        self,
        agent_id: str,
        local_handlers: Dict[str, Callable],
        local_schemas: List[Dict[str, Any]],
        external_clients: Optional[List[ExternalMcpClient]] = None,
    ):
        self.agent_id = agent_id
        self._local_handlers = local_handlers
        self._local_schemas = local_schemas
        self._external = external_clients or []
        self._external_tools: List[Dict[str, Any]] = []
        self._external_by_name: Dict[str, ExternalMcpClient] = {}
        self._load_external_tools()

    @classmethod
    def for_agent(
        cls,
        db: Session,
        project_id: str,
        agent_id: str,
        file_records: List[FileRecord],
    ) -> McpHub:
        handlers = build_agent_handlers(agent_id, db, project_id, file_records)
        schemas = get_tools_for_agent(agent_id)
        clients = [ExternalMcpClient(c) for c in parse_mcp_servers() if c.enabled]
        return cls(agent_id, handlers, schemas, clients)

    def _load_external_tools(self) -> None:
        for client in self._external:
            for tool in client.load_tools():
                fn = tool.get("function") if tool.get("type") == "function" else tool
                if isinstance(fn, dict) and fn.get("name"):
                    name = str(fn["name"])
                    prefixed = f"mcp_{client.config.name}_{name}".replace(".", "_").replace("-", "_")
                    self._external_by_name[prefixed] = client
                    schema = dict(tool) if tool.get("type") == "function" else {
                        "type": "function",
                        "function": fn,
                    }
                    fn_copy = dict(schema.get("function") or {})
                    fn_copy["name"] = prefixed
                    fn_copy["description"] = f"[MCP:{client.config.name}] {fn_copy.get('description', name)}"
                    schema = {"type": "function", "function": fn_copy}
                    self._external_tools.append(schema)

    def tool_schemas(self) -> List[Dict[str, Any]]:
        return list(self._local_schemas) + self._external_tools

    def list_tool_names(self) -> List[str]:
        names = []
        for s in self.tool_schemas():
            fn = s.get("function") or {}
            if fn.get("name"):
                names.append(fn["name"])
        return names

    def call_tool(self, name: str, arguments: str | Dict[str, Any]) -> str:
        args_str = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
        if name in self._local_handlers:
            return execute_tool_call(name, args_str, self._local_handlers)
        client = self._external_by_name.get(name)
        if client:
            try:
                args = json.loads(args_str) if args_str else {}
                original = name
                for tool in client.load_tools():
                    fn = tool.get("function") or tool
                    prefixed = f"mcp_{client.config.name}_{fn.get('name', '')}".replace(".", "_").replace("-", "_")
                    if prefixed == name:
                        original = fn.get("name", name)
                        break
                return client.call_tool(str(original), args if isinstance(args, dict) else {})
            except Exception as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)

    def server_summary(self) -> List[Dict[str, str]]:
        return [
            {"name": c.config.name, "url": c.config.url, "tools": str(len(c.load_tools()))}
            for c in self._external
        ]
