"""向后兼容：请优先使用 tool_registry。"""
from app.services.agent.tool_registry import (
    build_tool_handlers,
    execute_tool_call,
    execution_capabilities,
    tool_schemas,
)

__all__ = [
    "build_tool_handlers",
    "execute_tool_call",
    "execution_capabilities",
    "tool_schemas",
]
