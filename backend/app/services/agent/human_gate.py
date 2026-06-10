from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.config import settings
from app.models import Risk


@dataclass
class HumanGateResult:
    pause: bool
    reason: str
    manual_count: int
    total_count: int
    critic_flag_count: int = 0


def evaluate_human_gate(risks: List[Risk], critic_flag_count: int = 0) -> HumanGateResult:
    """高风险 / 待复核过多时暂停自动完成，转人工复核。"""
    total = len(risks)
    manual = sum(1 for r in risks if r.manual_review_required)
    high = sum(1 for r in risks if r.risk_level == "高")

    threshold = settings.human_gate_manual_threshold
    ratio_threshold = settings.human_gate_manual_ratio
    high_threshold = settings.human_gate_high_threshold

    if high >= high_threshold:
        return HumanGateResult(
            pause=True,
            reason=f"高风险项 {high} 条，达到人工复核阈值（≥{high_threshold}）",
            manual_count=manual,
            total_count=total,
            critic_flag_count=critic_flag_count,
        )

    if manual >= threshold:
        return HumanGateResult(
            pause=True,
            reason=f"待人工复核 {manual} 条，达到阈值（≥{threshold}）",
            manual_count=manual,
            total_count=total,
            critic_flag_count=critic_flag_count,
        )

    if total > 0 and manual / total >= ratio_threshold:
        return HumanGateResult(
            pause=True,
            reason=f"待复核占比 {manual}/{total}，超过 {ratio_threshold:.0%}",
            manual_count=manual,
            total_count=total,
            critic_flag_count=critic_flag_count,
        )

    if critic_flag_count >= settings.human_gate_critic_threshold:
        return HumanGateResult(
            pause=True,
            reason=f"Critic 标记证据疑点 {critic_flag_count} 条",
            manual_count=manual,
            total_count=total,
            critic_flag_count=critic_flag_count,
        )

    return HumanGateResult(
        pause=False,
        reason="自动完成",
        manual_count=manual,
        total_count=total,
        critic_flag_count=critic_flag_count,
    )
