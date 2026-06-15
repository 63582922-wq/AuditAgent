"use client";

import { FxPanel } from "@/components/FxPanel";
import { AgentCore } from "@/components/AgentCore";
import { getStepStates, overallProgress } from "@/lib/workflow";
import { useI18n } from "@/lib/i18n";
import { buildWorkflowSteps } from "@/lib/i18n/workflow-steps";

type SubAgent = { id: string; name: string; station: string; agent_say?: string; modality?: string };

type Props = {
  status: string;
  jobStep?: string;
  jobPct?: number;
  jobStatus?: string;
  live?: boolean;
  agentMessage?: string;
  subAgents?: SubAgent[];
};

export function CyberWorkflow({
  status,
  jobStep,
  jobPct,
  jobStatus,
  live,
  agentMessage,
  subAgents,
}: Props) {
  const { t, messages } = useI18n();
  const workflowSteps = buildWorkflowSteps(messages);
  const steps = getStepStates(status, jobStep, jobStatus, workflowSteps);
  const pct = overallProgress(status, jobStep, jobPct, jobStatus, workflowSteps);
  const activeIdx = steps.findIndex((s) => s.state === "active");
  const active = activeIdx >= 0 ? steps[activeIdx] : undefined;
  const failed = status === "failed" || jobStatus === "failed";
  const isLive = live || jobStatus === "running";
  const isDone = status === "completed";
  const trackPct =
    steps.length > 1
      ? ((activeIdx >= 0 ? activeIdx : isDone ? steps.length - 1 : 0) / (steps.length - 1)) * 100
      : 0;

  const coreMode = failed ? "failed" : isDone ? "done" : isLive ? "working" : active ? "idle" : "rest";

  const bubbleText = failed
    ? t("hud.failedSay")
    : isDone
      ? workflowSteps[workflowSteps.length - 1].agentSay
      : agentMessage && isLive
        ? agentMessage
        : active?.step.agentSay ?? t("hud.idleSay");

  const ringOffset = 251 * (1 - pct / 100);

  return (
    <FxPanel
      className={`cyber-flow${isLive ? " cyber-flow--live" : ""}${failed ? " cyber-flow--failed" : ""}${isDone ? " cyber-flow--done" : ""}`}
      glow={isLive}
    >
      <div className="cyber-flow__noise" aria-hidden />

      <div className="cyber-flow__hud">
        <div className="cyber-flow__left">
          <AgentCore mode={coreMode} pct={pct} />
          <div className="cyber-flow__copy">
            <span className="cyber-tag">{t("hud.agentName")}</span>
            <p className="cyber-flow__status">
              {active?.step.short ?? (isDone ? workflowSteps[workflowSteps.length - 1].short : "—")}
              {isLive && <span className="cyber-flow__pulse-dot cyber-flow__pulse-dot--fast" aria-hidden />}
            </p>
            <p className="cyber-flow__sub">
              {bubbleText}
              {isLive && (
                <span className="agent-work__typing" aria-hidden>
                  <span />
                  <span />
                  <span />
                </span>
              )}
            </p>
            {active && (
              <p className="cyber-flow__station">
                {active.step.station}
                {isLive && jobPct != null && ` · ${jobPct}%`}
              </p>
            )}
            {subAgents && subAgents.length > 0 && (
              <ul className="agent-work__team" aria-label="Sub-agents">
                {subAgents.map((sa) => (
                  <li
                    key={sa.id}
                    className={`agent-work__team-chip${sa.modality === "vision" ? " agent-work__team-chip--vision" : ""}`}
                    title={sa.station}
                  >
                    {sa.name}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="cyber-ring" aria-hidden>
          <svg viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="40" className="cyber-ring__track" />
            <circle
              cx="50"
              cy="50"
              r="40"
              className="cyber-ring__fill"
              style={{ strokeDasharray: 251, strokeDashoffset: ringOffset }}
            />
          </svg>
          <div className="cyber-ring__text">
            <span className="cyber-ring__num">{pct}</span>
            <span className="cyber-ring__unit">%</span>
          </div>
        </div>
      </div>

      <div className="cyber-flow__track-wrap">
        <div className="cyber-flow__track-bg" aria-hidden />
        <div className="cyber-flow__track-fill" style={{ width: `${trackPct}%` }} aria-hidden />
        <ol className="cyber-flow__nodes">
          {steps.map(({ step, state }, i) => (
            <li
              key={step.id}
              className={`cyber-node cyber-node--${state}`}
              title={step.desc}
            >
              {state === "active" && isLive && <span className="cyber-node__scan" aria-hidden />}
              <span className="cyber-node__hex">
                <span className="cyber-node__idx">{String(i + 1).padStart(2, "0")}</span>
              </span>
              <span className="cyber-node__label">{step.short}</span>
            </li>
          ))}
        </ol>
      </div>

      {active && isLive && (
        <div className="cyber-flow__spotlight">
          <span className="cyber-flow__spotlight-step">{String(activeIdx + 1).padStart(2, "0")}</span>
          <span className="cyber-flow__spotlight-name">{active.step.label}</span>
          <span className="cyber-flow__spotlight-desc">{active.step.desc}</span>
          <span className="cyber-flow__spotlight-pct">{jobPct ?? pct}%</span>
        </div>
      )}

      <div className="cyber-flow__meta">
        {isLive ? (
          <>
            <span className="cyber-flow__pulse-dot" aria-hidden />
            {t("hud.liveRun")}
          </>
        ) : isDone ? (
          t("workflow.status.completed")
        ) : failed ? (
          t("workflow.status.failed")
        ) : (
          t("hud.idleSay")
        )}
      </div>
    </FxPanel>
  );
}
