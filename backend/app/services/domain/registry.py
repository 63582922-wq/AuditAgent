from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings


@dataclass
class DomainPack:
    name: str
    label: str
    required_docs: list[tuple[str, str, str]]
    category_keywords: dict[str, list[str]]
    sub_agent_module: str
    planner_focus: list[str]


def resolve_agent_domain(project: Any = None, *, state_json: dict | None = None) -> str:
    """优先读项目 state_json.agent_domain，否则回退全局 settings。"""
    if state_json is None and project is not None:
        state_json = getattr(project, "state_json", None) or {}
    if state_json:
        domain = state_json.get("agent_domain")
        if domain:
            return str(domain).lower()
    return (settings.agent_domain or "compliance").lower()


def get_domain_pack(project: Any = None, *, domain: str | None = None) -> DomainPack:
    domain = (domain or resolve_agent_domain(project)).lower()
    if domain == "accounting":
        from app.services import constants as acc

        return DomainPack(
            name="accounting",
            label="会计风险评估",
            required_docs=acc.REQUIRED_DOCS,
            category_keywords=acc.CATEGORY_KEYWORDS,
            sub_agent_module="app.services.domain.accounting.sub_agents",
            planner_focus=["税务风险", "票据风险", "异常交易"],
        )

    from app.services.domain.compliance import constants as cmp

    return DomainPack(
        name="compliance",
        label=cmp.DOMAIN_LABEL,
        required_docs=cmp.REQUIRED_EVIDENCE,
        category_keywords=cmp.CATEGORY_KEYWORDS,
        sub_agent_module="app.services.domain.compliance.sub_agents",
        planner_focus=["远程观察", "讲者时长", "材料编码", "签到一致性", "证据链"],
    )


def get_sub_agent_module(project: Any = None):
    import importlib

    pack = get_domain_pack(project)
    return importlib.import_module(pack.sub_agent_module)
