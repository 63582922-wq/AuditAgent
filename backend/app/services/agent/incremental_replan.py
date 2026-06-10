from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set

from app.models import FileRecord


@dataclass
class IncrementalDiff:
    new_file_ids: List[str] = field(default_factory=list)
    new_categories: Set[str] = field(default_factory=set)
    previous_file_ids: Set[str] = field(default_factory=set)
    current_file_ids: Set[str] = field(default_factory=set)


# 新增资料类型 → 建议重跑的流水线阶段
_CATEGORY_IMPACT: Dict[str, Set[str]] = {
    "expense_detail": {"extract", "run_rules", "cross_check", "adjudicate"},
    "invoice_list": {"extract", "run_rules", "cross_check", "adjudicate"},
    "invoice_image": {"parse", "extract", "run_rules", "adjudicate"},
    "bank_statement": {"extract", "cross_check", "adjudicate"},
    "contract": {"parse", "extract", "run_rules", "cross_check", "adjudicate"},
    "tax_return": {"parse", "run_rules", "adjudicate"},
    "trial_balance": {"parse", "run_rules", "adjudicate"},
    "accounts_payable": {"parse", "run_rules", "adjudicate"},
    "accounts_receivable": {"parse", "run_rules", "adjudicate"},
}


def diff_uploaded_files(
    previous_state: Dict[str, Any] | None,
    files: Iterable[FileRecord],
) -> IncrementalDiff:
    file_list = list(files)
    prev_ids = set((previous_state or {}).get("processed_file_ids") or [])
    curr_ids = {f.id for f in file_list}
    new_ids = sorted(curr_ids - prev_ids)
    prev_cats = set((previous_state or {}).get("present_categories") or [])
    curr_cats = {f.document_category for f in file_list if f.document_category and f.document_category != "unknown"}
    new_cats = curr_cats - prev_cats

    if not prev_ids and file_list:
        new_ids = [f.id for f in file_list]
        new_cats = set(curr_cats)

    return IncrementalDiff(
        new_file_ids=new_ids,
        new_categories=new_cats,
        previous_file_ids=prev_ids,
        current_file_ids=curr_ids,
    )


def build_incremental_plan(base_plan: Dict[str, Any], diff: IncrementalDiff) -> Dict[str, Any]:
    """补资料后生成增量计划：只重跑受影响的阶段。"""
    if not diff.new_file_ids:
        raise ValueError("没有检测到新增资料，无需增量分析")

    impacted: Set[str] = set()
    for cat in diff.new_categories:
        impacted.update(_CATEGORY_IMPACT.get(cat, {"parse", "extract", "run_rules", "cross_check", "adjudicate"}))

    if not impacted:
        impacted = {"parse", "extract", "run_rules", "cross_check", "adjudicate"}

    steps: List[str] = []
    if diff.new_file_ids:
        steps.extend(["classify", "parse"])
    if impacted & {"extract", "run_rules", "cross_check", "adjudicate"}:
        if "extract" in impacted:
            steps.append("extract")
        if "run_rules" in impacted:
            steps.append("run_rules")
        if "cross_check" in impacted:
            steps.append("cross_check")
        if "adjudicate" in impacted:
            steps.append("adjudicate")
    steps.append("report")

    plan = dict(base_plan)
    plan["steps"] = steps
    plan["incremental"] = True
    plan["new_file_ids"] = diff.new_file_ids
    plan["new_categories"] = sorted(diff.new_categories)
    plan["reasoning"] = (
        f"增量分析：新增 {len(diff.new_file_ids)} 份资料"
        f"（{', '.join(sorted(diff.new_categories)) or '待分类'}），"
        f"重跑 {len(steps)} 个阶段。"
    )
    return plan
