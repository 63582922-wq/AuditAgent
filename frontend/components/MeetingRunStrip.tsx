"use client";

import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { useI18n } from "@/lib/i18n";
import { buildWorkflowSteps, statusLabel } from "@/lib/i18n/workflow-steps";
import { isPipelineRunning, resolveLiveProgress } from "@/lib/workflow";

/** 子会议子页顶栏：运行中显示步骤与进度（概览页由 SettlingStage 负责） */
export function MeetingRunStrip() {
  const ctx = useProjectLiveOptional();
  const { t, messages } = useI18n();
  if (!ctx?.live) return null;

  const { live, job } = ctx;
  if (!isPipelineRunning(live.status, job?.status)) return null;

  const pct = resolveLiveProgress(live, job, buildWorkflowSteps(messages));
  const stepKey = job?.current_step || live.status;
  const label = statusLabel(stepKey, messages);

  return (
    <div className="meeting-run-strip" aria-live="polite">
      <span className="meeting-run-strip__kicker">{t("hud.liveRun")}</span>
      <span className="meeting-run-strip__step">{label}</span>
      <span className="meeting-run-strip__pct">{pct}%</span>
    </div>
  );
}
