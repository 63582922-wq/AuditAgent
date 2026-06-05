"use client";

import { WORKFLOW_STEPS, getStepStates, overallProgress } from "@/lib/workflow";
import { STATUS_LABEL } from "@/lib/workflow";

type Props = {
  status: string;
  jobStep?: string;
  jobPct?: number;
  jobStatus?: string;
  /** 首页演示：无真实任务时播放循环进度 */
  demo?: boolean;
};

export function CyberWorkflow({ status, jobStep, jobPct, jobStatus, demo }: Props) {
  const steps = getStepStates(status, jobStep, jobStatus);
  const pct = overallProgress(status, jobStep, jobPct, jobStatus);
  const active = steps.find((s) => s.state === "active");
  const failed = status === "failed" || jobStatus === "failed";

  return (
    <div className={`cyber-flow${demo ? " cyber-flow--demo" : ""}`}>
      <div className="cyber-flow__hud">
        <div className="cyber-flow__hud-left">
          <span className="cyber-tag">PIPELINE</span>
          <h2 className="cyber-flow__status">
            {failed
              ? "SIGNAL LOST"
              : status === "completed"
                ? "MISSION COMPLETE"
                : active
                  ? active.step.label.toUpperCase()
                  : "STANDBY"}
          </h2>
          <p className="cyber-flow__sub">
            {failed ? "分析中断，请检查日志" : STATUS_LABEL[active?.step.id ?? status] ?? "等待任务启动"}
          </p>
        </div>

        <div className="cyber-flow__hud-right">
          <div className="cyber-ring" style={{ "--p": pct } as React.CSSProperties}>
            <svg viewBox="0 0 120 120">
              <circle className="cyber-ring__track" cx="60" cy="60" r="52" />
              <circle
                className="cyber-ring__fill"
                cx="60"
                cy="60"
                r="52"
                style={{
                  strokeDasharray: 326.7,
                  strokeDashoffset: 326.7 * (1 - pct / 100),
                }}
              />
            </svg>
            <div className="cyber-ring__text">
              <span className="cyber-ring__num">{pct}</span>
              <span className="cyber-ring__unit">%</span>
            </div>
          </div>
        </div>
      </div>

      <div className="cyber-flow__track-wrap">
        <div className="cyber-flow__track-bg" />
        <div className="cyber-flow__track-fill" style={{ width: `${pct}%` }} />
        <div className="cyber-flow__nodes">
          {steps.map(({ step, state }, i) => (
            <div
              key={step.id}
              className={`cyber-node cyber-node--${state}`}
              style={{ "--i": i } as React.CSSProperties}
            >
              <div className="cyber-node__hex">
                <span className="cyber-node__idx">{String(i + 1).padStart(2, "0")}</span>
              </div>
              <span className="cyber-node__label">{step.short}</span>
              {state === "active" && <span className="cyber-node__scan" aria-hidden />}
            </div>
          ))}
        </div>
      </div>

      <div className="cyber-flow__meta">
        <span>
          STEP{" "}
          {(steps.findIndex((s) => s.state === "active") >= 0
            ? steps.findIndex((s) => s.state === "active")
            : steps.filter((s) => s.state === "done").length - 1) + 1}{" "}
          / {WORKFLOW_STEPS.length}
        </span>
        <span className="cyber-flow__pulse-dot" />
        <span>{jobStatus === "running" ? "LIVE" : status === "completed" ? "DONE" : "IDLE"}</span>
      </div>
    </div>
  );
}
