"use client";

import dynamic from "next/dynamic";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import { HudSkeleton } from "@/components/PageSkeleton";
import { CompactMissionBar } from "@/components/CompactMissionBar";
import { pickHudAgents } from "@/lib/hud-agents";
import { pickLiveAgentMessage } from "@/components/ActivityTimeline";
import { isPipelineRunning } from "@/lib/workflow";
import { buildWorkflowSteps } from "@/lib/i18n/workflow-steps";
import { useI18n } from "@/lib/i18n";
import { resolveLiveProgress } from "@/lib/workflow";

const PipelineHud = dynamic(
  () => import("@/components/PipelineHud").then((m) => ({ default: m.PipelineHud })),
  { loading: () => <div className="hud-skeleton__body" style={{ minHeight: 420 }} /> }
);

/** 子会议页顶栏：紧凑状态条（layout 用） */
export function MeetingStatusBar() {
  const { live } = useProjectLive();
  if (!live) return <HudSkeleton />;
  return <CompactMissionBar />;
}

/** 子会议概览：Agent 运行可视化（仅概览页） */
export function MeetingPipelinePanel() {
  const { live, job, traceLogs } = useProjectLive();
  const { messages } = useI18n();

  if (!live) return null;

  const liveRunning = isPipelineRunning(live.status, job?.status);
  const workflowSteps = buildWorkflowSteps(messages);
  const progressPct = resolveLiveProgress(live, job, workflowSteps);

  const agentMessage =
    (liveRunning ? pickLiveAgentMessage(traceLogs) : null) ||
    live.state_json?.runtime_live?.message ||
    (live.state_json?.execution_graph as { agent_message?: string } | undefined)?.agent_message ||
    (live.state_json?.agent_plan as { reasoning?: string } | undefined)?.reasoning;

  const subAgents = pickHudAgents(live.state_json);
  const criticSummary = live.state_json?.runtime?.critic;

  return (
    <div className="project-hud project-hud--overview">
      <PipelineHud
        status={live.status}
        jobStep={job?.current_step}
        jobPct={progressPct}
        jobStatus={job?.status}
        live={liveRunning}
        agentMessage={agentMessage}
        subAgents={subAgents}
        criticSummary={criticSummary}
        traceLogs={traceLogs}
        showGraph={false}
      />
    </div>
  );
}

/** @deprecated 使用 MeetingStatusBar + MeetingPipelinePanel */
export function ProjectWorkflowBar() {
  return (
    <>
      <MeetingStatusBar />
      <MeetingPipelinePanel />
    </>
  );
}
