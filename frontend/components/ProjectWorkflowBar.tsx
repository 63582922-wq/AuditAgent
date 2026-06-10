"use client";

import dynamic from "next/dynamic";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import { HudSkeleton } from "@/components/PageSkeleton";

const MissionControl = dynamic(
  () => import("@/components/MissionControl").then((m) => ({ default: m.MissionControl })),
  { loading: () => <div className="hud-skeleton__body" style={{ minHeight: 48 }} /> }
);

const CyberWorkflow = dynamic(
  () => import("@/components/CyberWorkflow").then((m) => ({ default: m.CyberWorkflow })),
  { loading: () => <div className="hud-skeleton__body" style={{ minHeight: 120 }} /> }
);

export function ProjectWorkflowBar() {
  const { live, job } = useProjectLive();

  if (!live) return <HudSkeleton />;

  const liveRunning = job?.status === "running";

  const agentMessage =
    (live.state_json?.execution_graph as { agent_message?: string } | undefined)?.agent_message ||
    (live.state_json?.agent_plan as { reasoning?: string } | undefined)?.reasoning;

  const subAgents =
    ((live.state_json?.mission as { registered_agents?: { id: string; name: string; station: string }[] } | undefined)
      ?.registered_agents?.filter((a) => a.id !== "main") ||
      (live.state_json?.execution_graph as { sub_agents?: { id: string; name: string; station: string }[] } | undefined)
        ?.sub_agents ||
      (live.state_json?.agent_plan as { sub_agents?: { id: string; name: string; station: string }[] } | undefined)
        ?.sub_agents) ??
    [];

  const executionMode =
    live.state_json?.execution_mode ||
    (live.state_json?.runtime as { execution_mode?: string } | undefined)?.execution_mode;

  return (
    <div className="project-hud">
      {executionMode === "orchestrator" && (
        <p className="project-hud__mode" aria-label="执行模式">
          Orchestrator · 主 Agent 拆解任务并调度子 Agent
        </p>
      )}
      {executionMode === "react" && (
        <p className="project-hud__mode" aria-label="执行模式">
          ReAct 外环 · LLM 逐步调度内环工具
        </p>
      )}
      <MissionControl project={live} job={job} />
      <CyberWorkflow
        status={live.status}
        jobStep={job?.current_step}
        jobPct={job?.progress_pct}
        jobStatus={job?.status}
        live={liveRunning}
        agentMessage={agentMessage}
        subAgents={subAgents}
      />
    </div>
  );
}
