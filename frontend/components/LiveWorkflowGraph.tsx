"use client";

import { AgentGraph } from "@/components/AgentGraph";
import { pickHudAgents } from "@/lib/hud-agents";
import type { Job, ProjectStateJson } from "@/lib/api";

type Props = {
  live: { status: string; state_json?: ProjectStateJson | null };
  job?: Job | null;
  /** 运行中脉冲动画 */
  livePulse?: boolean;
  /** 嵌入父级区块：无独立卡片/重复标题 */
  embedded?: boolean;
  className?: string;
};

/** 沉降风格 · 实时 Agent 工作态图谱（Orchestrator 拓扑） */
export function LiveWorkflowGraph({
  live,
  job,
  livePulse = false,
  embedded = false,
  className,
}: Props) {
  const subAgents = pickHudAgents(live.state_json);
  const criticSummary = live.state_json?.runtime?.critic;

  const panelClass = [
    "workflow-graph-panel",
    embedded ? "workflow-graph-panel--embedded" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={panelClass}>
      <AgentGraph
        status={live.status}
        jobStep={job?.current_step}
        jobPct={job?.progress_pct}
        jobStatus={job?.status}
        live={livePulse}
        embedded={embedded}
        subAgents={subAgents}
        criticSummary={criticSummary}
      />
    </div>
  );
}
