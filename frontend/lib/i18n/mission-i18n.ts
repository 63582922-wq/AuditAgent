import type { Job } from "@/lib/api";
import type { Messages } from "./zh";
import type { MissionGuide, MissionPhase, MissionProjectSource } from "@/lib/mission";
import { resolveMissionPhase } from "@/lib/mission";
import { resolveLiveProgress } from "@/lib/workflow";
import { buildWorkflowSteps } from "./workflow-steps";

type TFn = (key: string, vars?: Record<string, string | number>) => string;

export function localizeMissionGuide(
  project: MissionProjectSource,
  job: Job | null | undefined,
  basePath: string,
  messages: Messages,
  t: TFn
): MissionGuide {
  const phase = resolveMissionPhase(project, job);
  const phases = [
    { id: "init" as MissionPhase, ...messages.mission.phases.init, icon: "01" },
    { id: "ingest" as MissionPhase, ...messages.mission.phases.ingest, icon: "02" },
    { id: "processing" as MissionPhase, ...messages.mission.phases.processing, icon: "03" },
    { id: "deliver" as MissionPhase, ...messages.mission.phases.deliver, icon: "04" },
  ];
  const phaseIndex =
    phase === "review"
      ? phases.findIndex((p) => p.id === "deliver")
      : phases.findIndex((p) => p.id === phase);
  const fileCount = project.file_count ?? project.files?.length ?? 0;
  const riskCount = project.risk_count ?? project.risks?.length ?? 0;
  const steps = buildWorkflowSteps(messages);
  const progress = resolveLiveProgress(project, job, steps);
  const live =
    job?.status === "running" ||
    job?.status === "queued" ||
    (["planning", "classifying", "vision_parsing", "parsing", "extracting", "running_rules", "cross_checking", "adjudicating", "generating_report", "running", "queued"].includes(project.status) &&
      project.status !== "completed" &&
      project.status !== "accepted");

  const base = { phase, phaseIndex, progress, live };
  const dStatus = project.state_json?.deliverable?.status;
  const state = project.state_json as { execution_mode?: string; agent_domain?: string } | undefined;
  const compliance = state?.execution_mode === "compliance_harness" || state?.agent_domain === "compliance";

  switch (phase) {
    case "failed":
      return {
        ...base,
        headline: t("mission.failedHeadline"),
        detail: job?.error_message || t("mission.failedDetail"),
        action: { label: t("mission.viewLogs"), href: `${basePath}/logs` },
      };
    case "deliver": {
      if (project.status === "accepted" || dStatus === "accepted") {
        return {
          ...base,
          headline: t("mission.acceptedHeadline"),
          detail: t("mission.acceptedDetail", { count: riskCount }),
          action: { label: t("mission.viewOutputs"), href: `${basePath}/outputs` },
        };
      }
      if (project.status === "deliverable_rejected" || dStatus === "rejected") {
        return {
          ...base,
          headline: t("mission.rejectedHeadline"),
          detail: t("mission.rejectedDetail"),
          action: { label: t("mission.uploadFiles"), href: `${basePath}/files` },
        };
      }
      return {
        ...base,
        headline: t("mission.pendingHeadline"),
        detail: t("mission.pendingDetail", { count: riskCount }),
        action: { label: t("mission.deliverAction"), href: `${basePath}/outputs` },
      };
    }
    case "review":
      return {
        ...base,
        phaseIndex: phases.findIndex((p) => p.id === "deliver"),
        headline: t("mission.reviewHeadline"),
        detail: t("mission.reviewDetail", { count: riskCount }),
        action: { label: t("mission.itemReview"), href: `${basePath}/review` },
      };
    case "processing": {
      const step = steps.find((s) => s.id === (job?.current_step || project.status));
      return {
        ...base,
        headline: live
          ? t("mission.processingLive", { step: step?.label ?? t("mission.analysisFallback") })
          : t("mission.processingQueue"),
        detail: step?.desc ?? t("mission.processingDetail"),
        action: { label: t("mission.liveLogs"), href: `${basePath}/logs` },
      };
    }
    case "ingest":
      return {
        ...base,
        headline: fileCount > 0 ? t("mission.ingestReady", { count: fileCount }) : t("mission.ingestWait"),
        detail: fileCount > 0 ? t("mission.ingestDetailReady") : t("mission.ingestDetailEmpty"),
        action: {
          label: fileCount > 0 ? (compliance ? t("mission.runHarness") : t("mission.runAnalysis")) : t("mission.uploadFiles"),
          href: `${basePath}/files`,
        },
      };
    default:
      return {
        ...base,
        headline: t("mission.initHeadline"),
        detail: t("mission.initDetail"),
        action: { label: t("mission.uploadFiles"), href: `${basePath}/files` },
      };
  }
}

export function missionPhaseTitle(phase: MissionPhase, t: TFn): string {
  const map: Record<MissionPhase, string> = {
    init: t("hud.phaseInit"),
    ingest: t("hud.phaseIngest"),
    processing: t("hud.phaseProcessing"),
    review: t("hud.phaseReview"),
    deliver: t("hud.phaseDeliver"),
    failed: t("hud.phaseFailed"),
  };
  return map[phase];
}

export function missionPhasesForUi(messages: Messages) {
  return [
    { id: "init" as MissionPhase, label: messages.mission.phases.init.label, short: messages.mission.phases.init.short, icon: "01" },
    { id: "ingest" as MissionPhase, label: messages.mission.phases.ingest.label, short: messages.mission.phases.ingest.short, icon: "02" },
    { id: "processing" as MissionPhase, label: messages.mission.phases.processing.label, short: messages.mission.phases.processing.short, icon: "03" },
    { id: "deliver" as MissionPhase, label: messages.mission.phases.deliver.label, short: messages.mission.phases.deliver.short, icon: "04" },
  ];
}
