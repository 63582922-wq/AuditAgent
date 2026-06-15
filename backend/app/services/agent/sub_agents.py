from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.models import FileRecord
from app.services.domain.registry import get_sub_agent_module


def _mod():
    return get_sub_agent_module()


class _SubAgentDefsProxy:
    def __getitem__(self, key: str) -> Dict[str, Any]:
        return _mod().SUB_AGENT_DEFS[key]

    def get(self, key: str, default: Any = None) -> Any:
        return _mod().SUB_AGENT_DEFS.get(key, default)

    def keys(self):
        return _mod().SUB_AGENT_DEFS.keys()

    def items(self):
        return _mod().SUB_AGENT_DEFS.items()

    def __contains__(self, key: object) -> bool:
        return key in _mod().SUB_AGENT_DEFS

    def __iter__(self):
        return iter(_mod().SUB_AGENT_DEFS)


SUB_AGENT_DEFS = _SubAgentDefsProxy()


def route_sub_agents(
    files: Iterable[FileRecord],
    plan: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return _mod().route_sub_agents(files, plan)


def pick_sub_agent_for_risk(risk: Dict[str, Any], sub_agents: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    return _mod().pick_sub_agent_for_risk(risk, sub_agents)


def enrich_plan_with_sub_agents(plan: Dict[str, Any], files: Iterable[FileRecord]) -> Dict[str, Any]:
    return _mod().enrich_plan_with_sub_agents(plan, files)
