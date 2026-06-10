"use client";

import { WORKFLOW_STEPS, getStepStates, overallProgress } from "@/lib/workflow";

type SubAgent = { id: string; name: string; station: string; agent_say?: string };

type Props = {
  status: string;
  jobStep?: string;
  jobPct?: number;
  jobStatus?: string;
  demo?: boolean;
  live?: boolean;
  agentMessage?: string;
  subAgents?: SubAgent[];
};

const AGENT_NAME = "审计助手";

export function CyberWorkflow({
  status,
  jobStep,
  jobPct,
  jobStatus,
  demo,
  live,
  agentMessage,
  subAgents,
}: Props) {
  const steps = getStepStates(status, jobStep, jobStatus);
  const pct = overallProgress(status, jobStep, jobPct, jobStatus);
  const activeIdx = steps.findIndex((s) => s.state === "active");
  const active = activeIdx >= 0 ? steps[activeIdx] : undefined;
  const failed = status === "failed" || jobStatus === "failed";
  const isLive = live || jobStatus === "running";
  const isDone = status === "completed";

  const doneSteps = steps.filter((s) => s.state === "done").slice(-4);
  const pointerPct =
    steps.length > 1
      ? ((activeIdx >= 0 ? activeIdx : isDone ? steps.length - 1 : 0) + 0.5) / steps.length * 100
      : 50;

  const avatarMode = failed ? "failed" : isDone ? "done" : isLive ? "working" : active ? "idle" : "rest";

  const bubbleText = failed
    ? "抱歉，这一步遇到了问题，需要你看一下日志。"
    : isDone
      ? WORKFLOW_STEPS[WORKFLOW_STEPS.length - 1].agentSay
      : agentMessage && isLive
        ? agentMessage
        : active?.step.agentSay ?? "我在工位等你启动任务。";

  return (
    <section
      className={`agent-work${isLive ? " agent-work--live" : ""}${failed ? " agent-work--failed" : ""}${isDone ? " agent-work--done" : ""}`}
      aria-label="Agent 工作流程"
    >
      <div className="agent-work__hero">
        <div className={`agent-avatar agent-avatar--${avatarMode}`} aria-hidden>
          <div className="agent-avatar__head">
            <span className="agent-avatar__eye" />
            <span className="agent-avatar__eye" />
          </div>
          <div className="agent-avatar__body" />
          {isLive && (
            <div className="agent-avatar__hands">
              <span className="agent-avatar__hand agent-avatar__hand--l" />
              <span className="agent-avatar__hand agent-avatar__hand--r" />
            </div>
          )}
        </div>

        <div className="agent-work__speech">
          <div className="agent-work__speech-head">
            <strong>{AGENT_NAME}</strong>
            <span className="agent-work__pct">{pct}%</span>
          </div>
          <p className="agent-work__line">
            {bubbleText}
            {isLive && (
              <span className="agent-work__typing" aria-hidden>
                <span /><span /><span />
              </span>
            )}
          </p>
          {active && (
            <p className="agent-work__station">
              当前工位 · <em>{active.step.station}</em>
              {isLive && jobPct != null && ` · 本步 ${jobPct}%`}
            </p>
          )}
          {subAgents && subAgents.length > 0 && (
            <ul className="agent-work__team" aria-label="协同子 Agent">
              {subAgents.map((sa) => (
                <li key={sa.id} className="agent-work__team-chip" title={sa.station}>
                  {sa.name}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="agent-work__floor">
        <div
          className="agent-work__marker"
          style={{ left: `${pointerPct}%` }}
          aria-hidden
        >
          <span className="agent-work__marker-icon">▲</span>
        </div>
        <ol className="agent-work__stations">
          {steps.map(({ step, state }) => (
            <li
              key={step.id}
              className={`agent-work__station agent-work__station--${state}`}
              title={step.desc}
            >
              <span className="agent-work__station-desk">{step.station}</span>
              <span className="agent-work__station-name">{step.short}</span>
            </li>
          ))}
        </ol>
      </div>

      {doneSteps.length > 0 && (
        <ul className="agent-work__journal">
          {doneSteps.map(({ step }) => (
            <li key={step.id}>
              <span className="agent-work__journal-check">✓</span>
              {step.agentDone}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
