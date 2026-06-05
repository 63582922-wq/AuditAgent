"use client";

import { StepState, WorkflowStep, getStepStates, overallProgress } from "@/lib/workflow";

type Props = {
  status: string;
  jobStep?: string;
  jobPct?: number;
  jobStatus?: string;
  compact?: boolean;
  showHeader?: boolean;
};

function StepNode({
  step,
  state,
  compact,
  isLast,
}: {
  step: WorkflowStep;
  state: StepState;
  compact?: boolean;
  isLast: boolean;
}) {
  return (
    <div className={`wf-step wf-step--${state}${compact ? " wf-step--compact" : ""}`}>
      <div className="wf-step__node-wrap">
        {state === "active" && <span className="wf-step__pulse" aria-hidden />}
        <div className="wf-step__node">
          <span className="wf-step__icon">{state === "done" ? "✓" : state === "failed" ? "!" : step.icon}</span>
        </div>
        {!isLast && <div className={`wf-step__connector wf-step__connector--${state}`} />}
      </div>
      <div className="wf-step__meta">
        <span className="wf-step__label">{compact ? step.short : step.label}</span>
        {!compact && <span className="wf-step__desc">{step.desc}</span>}
      </div>
    </div>
  );
}

export function WorkflowPipeline({
  status,
  jobStep,
  jobPct,
  jobStatus,
  compact = false,
  showHeader = true,
}: Props) {
  const steps = getStepStates(status, jobStep, jobStatus);
  const pct = overallProgress(status, jobStep, jobPct, jobStatus);
  const activeStep = steps.find((s) => s.state === "active")?.step;

  return (
    <div className={`wf-board${compact ? " wf-board--compact" : ""}`}>
      {showHeader && (
        <div className="wf-board__header">
          <div className="wf-board__title-block">
            <span className="wf-board__eyebrow">评估流程</span>
            <h2 className="wf-board__title">
              {status === "completed"
                ? "评估已完成"
                : status === "failed"
                  ? "分析中断"
                  : activeStep
                    ? `正在：${activeStep.label}`
                    : "等待开始"}
            </h2>
          </div>
          <div className="wf-board__ring-wrap">
            <svg className="wf-board__ring" viewBox="0 0 80 80">
              <circle className="wf-board__ring-bg" cx="40" cy="40" r="34" />
              <circle
                className="wf-board__ring-fill"
                cx="40"
                cy="40"
                r="34"
                style={{
                  strokeDasharray: `${2 * Math.PI * 34}`,
                  strokeDashoffset: `${2 * Math.PI * 34 * (1 - pct / 100)}`,
                }}
              />
            </svg>
            <span className="wf-board__pct">{pct}<small>%</small></span>
          </div>
        </div>
      )}

      <div className="wf-board__track">
        <div className="wf-board__track-fill" style={{ width: `${pct}%` }} />
        <div className="wf-board__steps">
          {steps.map(({ step, state }, i) => (
            <StepNode
              key={step.id}
              step={step}
              state={state}
              compact={compact}
              isLast={i === steps.length - 1}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
