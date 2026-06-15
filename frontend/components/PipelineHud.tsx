"use client";

import dynamic from "next/dynamic";
import { FxPanel } from "@/components/FxPanel";
import { HudAgent } from "@/lib/hud-agents";
import { ActivityLog } from "@/components/ActivityTimeline";
import { useI18n } from "@/lib/i18n";
import { statusLabel } from "@/lib/i18n/workflow-steps";

const CyberWorkflow = dynamic(
  () => import("@/components/CyberWorkflow").then((m) => ({ default: m.CyberWorkflow })),
  { loading: () => <div className="hud-skeleton__body" style={{ minHeight: 220 }} /> }
);

const AgentGraph = dynamic(
  () => import("@/components/AgentGraph").then((m) => ({ default: m.AgentGraph })),
  { loading: () => <div className="hud-skeleton__body" style={{ minHeight: 280 }} /> }
);

const LiveExecutionTrace = dynamic(
  () => import("@/components/LiveExecutionTrace").then((m) => ({ default: m.LiveExecutionTrace })),
  { loading: () => <div className="hud-skeleton__body" style={{ minHeight: 72 }} /> }
);

type Props = {
  status?: string;
  jobStep?: string;
  jobPct?: number;
  jobStatus?: string;
  live?: boolean;
  agentMessage?: string;
  subAgents?: HudAgent[];
  criticSummary?: {
    validated?: number;
    flagged?: number;
    readjudicate_rounds?: number;
  };
  traceLogs?: ActivityLog[];
  /** 概览页默认隐藏图谱，避免与 CyberWorkflow 重复进度环 */
  showGraph?: boolean;
};

export function PipelineHud({
  status = "created",
  jobStep,
  jobPct,
  jobStatus,
  live,
  agentMessage,
  subAgents = [],
  criticSummary,
  traceLogs = [],
  showGraph = true,
}: Props) {
  const { t, messages } = useI18n();
  const stepKey = jobStep || status;
  const label = statusLabel(stepKey, messages);

  return (
    <div className={`pipeline-hud${live ? " pipeline-hud--live" : ""}`}>
      {live && (
        <p className="pipeline-hud__eyebrow">
          <span className="pipeline-hud__live-beacon" aria-hidden />
          {t("hud.liveRun")} · {label} · {jobPct ?? 0}%
        </p>
      )}
      <CyberWorkflow
        status={status}
        jobStep={jobStep}
        jobPct={jobPct}
        jobStatus={jobStatus}
        live={live}
        agentMessage={agentMessage}
        subAgents={subAgents}
      />
      {showGraph && (
        <FxPanel className="pipeline-graph-panel" glow={live}>
          <AgentGraph
            status={status}
            jobStep={jobStep}
            jobPct={jobPct}
            jobStatus={jobStatus}
            live={live}
            subAgents={subAgents}
            criticSummary={criticSummary}
          />
        </FxPanel>
      )}
      {(live || traceLogs.length > 0) && (
        <FxPanel className="trace-terminal" glow={live}>
          <div className="trace-terminal__head">
            <span className="trace-terminal__dots" aria-hidden>
              <i />
              <i />
              <i />
            </span>
            <span className="pipeline-hud__trace-label">{t("hud.traceLabel")}</span>
          </div>
          <LiveExecutionTrace logs={traceLogs} live={live} />
        </FxPanel>
      )}
    </div>
  );
}
