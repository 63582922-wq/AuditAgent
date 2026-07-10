"use client";

import { pickLiveAgentMessage } from "@/components/ActivityTimeline";
import { LiveExecutionTrace } from "@/components/LiveExecutionTrace";
import { LiveWorkflowGraph } from "@/components/LiveWorkflowGraph";
import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { MISSION_PHASES, resolveMissionPhase } from "@/lib/mission";
import { buildWorkflowSteps, statusLabel } from "@/lib/i18n/workflow-steps";
import { useI18n } from "@/lib/i18n";
import { isPipelineRunning, resolveLiveProgress } from "@/lib/workflow";

/** 子会议运行态 · 沉降风格实时进度（与 settling-theme 一致） */
export function MeetingRunStage() {
  const ctx = useProjectLiveOptional();
  const { t, messages } = useI18n();

  if (!ctx) return null;

  const { live, job, traceLogs, pendingRun, notFound } = ctx;
  if (notFound) return null;
  if (!live) {
    if (!pendingRun) return null;
    return (
      <section className="run-stage run-stage--pending run-stage--live" aria-busy="true" aria-live="polite">
        <p className="run-stage__kicker">
          {t("hud.startingSay")}
          <span className="run-stage__beacon" aria-hidden />
        </p>
        <div className="run-stage__hero run-stage__hero--ghost">
          <span aria-hidden>—</span>
          <em>%</em>
        </div>
        <div className="run-stage__bar" aria-hidden>
          <i className="run-stage__bar-indeterminate" style={{ width: "38%" }} />
        </div>
        <LiveWorkflowGraph
          live={{ status: "planning", state_json: {} }}
          job={undefined}
          livePulse
          embedded
          traceLogs={traceLogs}
          className="run-stage__graph"
        />
        <div className="run-stage__trace">
          <p className="run-stage__trace-label">{t("hud.traceLabel")}</p>
          <LiveExecutionTrace logs={traceLogs} live />
        </div>
      </section>
    );
  }

  const running = isPipelineRunning(live.status, job?.status);
  if (!running && !pendingRun) return null;

  const workflowSteps = buildWorkflowSteps(messages);
  const pct = running ? resolveLiveProgress(live, job, workflowSteps) : 0;
  const stepKey = job?.current_step || live.status;
  const stepName = statusLabel(stepKey, messages);
  const missionPhase = resolveMissionPhase(live, job);
  const phaseIdx = MISSION_PHASES.findIndex((p) => p.id === missionPhase);

  const workflowStep = messages.workflow.steps[stepKey as keyof typeof messages.workflow.steps];
  const agentMessage =
    (running ? pickLiveAgentMessage(traceLogs) : null) ||
    live.state_json?.runtime_live?.message ||
    (live.state_json?.execution_graph as { agent_message?: string } | undefined)?.agent_message ||
    (live.state_json?.agent_plan as { reasoning?: string } | undefined)?.reasoning ||
    (running ? workflowStep?.agentSay : undefined) ||
    t("hud.startingSay");

  return (
    <section
      className={`run-stage${running ? " run-stage--live" : " run-stage--pending"}`}
      aria-live="polite"
      aria-label={t("hud.workflowAria")}
    >
      <p className="run-stage__kicker">
        {running ? (
          <>
            {t("hud.liveRun")} · {stepName}
            <span className="run-stage__beacon" aria-hidden />
          </>
        ) : (
          t("hud.startingSay")
        )}
      </p>

      <div className="run-stage__hero" aria-label={running ? `${pct}%` : undefined}>
        {running ? pct : "—"}
        <em>%</em>
      </div>

      <p className="run-stage__desc">{agentMessage}</p>

      <div className="run-stage__bar" aria-hidden>
        <i style={{ width: `${running ? pct : 4}%` }} className={running ? undefined : "run-stage__bar-indeterminate"} />
      </div>

      <LiveWorkflowGraph live={live} job={job} livePulse={running} embedded traceLogs={traceLogs} className="run-stage__graph" />

      <div className="run-stage__trace">
        <p className="run-stage__trace-label">{t("hud.traceLabel")}</p>
        <LiveExecutionTrace logs={traceLogs} live={running || pendingRun} />
      </div>

      <ol className="run-stage__phases" aria-label={t("hud.workflowAria")}>
        {MISSION_PHASES.map((phase, i) => {
          const state =
            missionPhase === "failed"
              ? i <= phaseIdx
                ? i === phaseIdx
                  ? "is-failed"
                  : "is-done"
                : ""
              : i < phaseIdx
                ? "is-done"
                : i === phaseIdx
                  ? "is-live"
                  : "";
          const phaseLabel =
            phase.id === "failed"
              ? messages.mission.failedHeadline
              : messages.mission.phases[phase.id as "init" | "ingest" | "processing" | "deliver"]?.short ?? phase.short;
          return (
            <li key={phase.id} className={state || undefined}>
              <span className="run-stage__phase-num">{phase.icon}</span>
              <span className="run-stage__phase-label">{phaseLabel}</span>
              {state === "is-live" && running && (
                <span className="run-stage__phase-pct mono">{pct}%</span>
              )}
            </li>
          );
        })}
      </ol>

      <div className="run-stage__metrics">
        <div>
          <label>{t("meetingOverview.files")}</label>
          <b>{live.file_count ?? 0}</b>
        </div>
        <div>
          <label>{messages.domain.finding}</label>
          <b>{live.risk_count ?? 0}</b>
        </div>
        <div>
          <label>{t("meetingOverview.outputs")}</label>
          <b>{live.output_count ?? 0}</b>
        </div>
      </div>
    </section>
  );
}
