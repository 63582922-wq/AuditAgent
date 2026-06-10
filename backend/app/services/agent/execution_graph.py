from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set

from app.models import FileRecord

# 规划 focus_areas → 风险类别 / 资料类型
FOCUS_TO_RISK_CATEGORIES: Dict[str, Set[str]] = {
    "税务风险": {"税务风险"},
    "票据风险": {"税务风险", "发票风险"},
    "发票风险": {"税务风险"},
    "合同风险": {"合同风险"},
    "资金风险": {"异常交易风险", "会计核算风险"},
    "银行流水": {"异常交易风险", "会计核算风险"},
    "账务风险": {"会计核算风险"},
    "会计核算风险": {"会计核算风险"},
    "异常交易": {"异常交易风险"},
    "异常交易风险": {"异常交易风险"},
}

FOCUS_TO_DOC_TYPES: Dict[str, Set[str]] = {
    "税务风险": {"tax_return", "invoice_list", "expense_detail"},
    "票据风险": {"invoice_list", "invoice_image", "expense_detail"},
    "发票风险": {"invoice_list", "invoice_image"},
    "合同风险": {"contract"},
    "资金风险": {"bank_statement", "expense_detail"},
    "银行流水": {"bank_statement"},
    "账务风险": {"trial_balance", "accounts_payable", "accounts_receivable"},
    "会计核算风险": {"trial_balance", "expense_detail"},
}

PLAN_STEP_ALIASES = {
    "plan": "planning",
    "classify": "classifying",
    "parse": "parsing",
    "extract": "extracting",
    "run_rules": "running_rules",
    "cross_check": "cross_checking",
    "adjudicate": "adjudicating",
    "report": "generating_report",
}

DEFAULT_PIPELINE_STEPS = frozenset(
    {
        "classifying",
        "parsing",
        "extracting",
        "running_rules",
        "cross_checking",
        "adjudicating",
        "generating_report",
    }
)


class ExecutionGraph:
    """将 Planner 输出转为可执行的步骤 / 规则 / 交叉比对策略。"""

    def __init__(
        self,
        plan: Dict[str, Any],
        present_categories: Set[str],
        file_count: int,
    ):
        self.plan = plan or {}
        self.present = {c for c in present_categories if c and c != "unknown"}
        self.file_count = file_count
        self.focus_areas: List[str] = list(self.plan.get("focus_areas") or [])
        self.priority_actions: List[str] = list(self.plan.get("priority_actions") or [])
        self.plan_steps = self._resolve_plan_steps()
        self.cross_modules = self._resolve_cross_modules()
        self.rule_focus_categories = self._resolve_rule_focus()
        self.reasoning = str(self.plan.get("reasoning") or "")
        self.sub_agents: List[Dict[str, Any]] = list(self.plan.get("sub_agents") or [])

    @classmethod
    def from_plan(cls, plan: Dict[str, Any], files: Iterable[FileRecord]) -> "ExecutionGraph":
        file_list = list(files)
        present = {f.document_category for f in file_list if f.document_category}
        return cls(plan, present, len(file_list))

    def _resolve_plan_steps(self) -> Set[str]:
        raw = self.plan.get("steps") or []
        if not raw:
            return set(DEFAULT_PIPELINE_STEPS)
        normalized: Set[str] = set()
        for step in raw:
            key = PLAN_STEP_ALIASES.get(str(step), str(step))
            normalized.add(key)
        if normalized & {"running_rules", "cross_checking", "adjudicating"}:
            normalized.add("generating_report")
        return normalized

    def _resolve_rule_focus(self) -> Set[str]:
        cats: Set[str] = set()
        for fa in self.focus_areas:
            cats.update(FOCUS_TO_RISK_CATEGORIES.get(fa, {fa}))
        return cats

    def _resolve_cross_modules(self) -> Set[str]:
        if "cross_checking" not in self.plan_steps:
            return set()

        modules: Set[str] = set()
        if len(self.present) >= 2:
            modules.add("amounts")
        if self.present & {"invoice_list", "expense_detail"}:
            modules.add("duplicates")
        if self.present & {"contract", "invoice_list", "expense_detail", "bank_statement"}:
            modules.add("three_way")
        if "expense_detail" in self.present:
            modules.add("anomalies")
            modules.add("cross_period")
        modules.add("record_links")

        actions = " ".join(self.priority_actions)
        if "交叉" in actions or "比对" in actions or "勾稽" in actions:
            modules.update({"amounts", "three_way", "record_links"})

        if self.file_count <= 1:
            modules.discard("three_way")
            modules.discard("amounts")

        return modules

    def should_run(self, step: str) -> bool:
        if self.file_count == 0:
            return step == "generating_report"
        return step in self.plan_steps

    def should_run_cross(self, module: str) -> bool:
        return module in self.cross_modules

    def rule_priority_boost(self, rule: Dict[str, Any]) -> int:
        boost = 0
        risk_cat = rule.get("risk_category") or ""
        doc_type = rule.get("applicable_document_type") or ""
        if self.rule_focus_categories and risk_cat in self.rule_focus_categories:
            boost += 50
        for fa in self.focus_areas:
            if doc_type in FOCUS_TO_DOC_TYPES.get(fa, set()) and doc_type in self.present:
                boost += 30
        return boost

    def sort_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            rules,
            key=lambda r: (self.rule_priority_boost(r) + int(r.get("priority") or 0), r.get("rule_id", "")),
            reverse=True,
        )

    def agent_message(self) -> str:
        if self.sub_agents:
            lead = self.sub_agents[0]
            team = "、".join(sa["name"] for sa in self.sub_agents[:3])
            return f"{team} 已就位，{lead.get('agent_say', '开始协同核查。')}"
        if self.file_count == 0:
            return "资料还没到位，我先整理一份补充清单。"
        if self.focus_areas:
            focus = "、".join(self.focus_areas[:3])
            return f"计划重点查 {focus}，按 {len(self.plan_steps)} 个阶段执行。"
        if self.reasoning:
            return self.reasoning[:120]
        return "按标准流程逐项核查。"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_steps": sorted(self.plan_steps),
            "focus_areas": self.focus_areas,
            "priority_actions": self.priority_actions,
            "present_categories": sorted(self.present),
            "cross_modules": sorted(self.cross_modules),
            "rule_focus_categories": sorted(self.rule_focus_categories),
            "file_count": self.file_count,
            "agent_message": self.agent_message(),
            "sub_agents": self.sub_agents,
        }
