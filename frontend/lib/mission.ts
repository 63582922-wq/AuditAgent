import { Job, ProjectLive } from "@/lib/api";
import { FINDING } from "@/lib/domain";
import { WORKFLOW_STEPS, resolveLiveProgress } from "@/lib/workflow";

export type MissionPhase = "init" | "ingest" | "processing" | "deliver" | "review" | "failed";

export type MissionPhaseDef = {
  id: MissionPhase;
  label: string;
  short: string;
  icon: string;
};

/** 用户可感知的宏观链路：资料 → 分析 → 交付（复核为遗留路径） */
export const MISSION_PHASES: MissionPhaseDef[] = [
  { id: "init", label: "初始化", short: "初始化", icon: "01" },
  { id: "ingest", label: "资料接入", short: "接入", icon: "02" },
  { id: "processing", label: "合规分析", short: "分析", icon: "03" },
  { id: "deliver", label: "交付验收", short: "交付", icon: "04" },
];

export type MissionGuide = {
  phase: MissionPhase;
  phaseIndex: number;
  headline: string;
  detail: string;
  progress: number;
  live: boolean;
  action?: { label: string; href: string };
};

const PROCESSING = new Set([
  "planning",
  "classifying",
  "parsing",
  "extracting",
  "running_rules",
  "cross_checking",
  "adjudicating",
  "generating_report",
  "running",
  "queued",
]);

/** 任务引导所需的最小项目字段（完整 Project 或 ProjectLive 均可） */
export type MissionProjectSource = {
  id: string;
  status: string;
  files?: readonly unknown[] | null;
  risks?: readonly unknown[] | null;
  file_count?: number;
  risk_count?: number;
  state_json?: { deliverable?: { status?: string; comment?: string } } | null;
};

function isComplianceProject(project: MissionProjectSource): boolean {
  const state = project.state_json as { execution_mode?: string; agent_domain?: string } | undefined;
  return state?.execution_mode === "compliance_harness" || state?.agent_domain === "compliance";
}

function countFiles(p: MissionProjectSource): number {
  return p.file_count ?? p.files?.length ?? 0;
}

function countRisks(p: MissionProjectSource): number {
  return p.risk_count ?? p.risks?.length ?? 0;
}

function deliverableStatus(project: MissionProjectSource): string | undefined {
  return project.state_json?.deliverable?.status;
}

export function resolveMissionPhase(project: MissionProjectSource, job?: Job | null): MissionPhase {
  if (project.status === "failed" || job?.status === "failed") return "failed";
  if (project.status === "needs_review") return "review";
  if (project.status === "accepted" || deliverableStatus(project) === "accepted") return "deliver";
  if (project.status === "completed" || project.status === "deliverable_rejected") return "deliver";
  if (job?.status === "running" || PROCESSING.has(project.status)) return "processing";
  if (countFiles(project) > 0) return "ingest";
  return "init";
}

export function getMissionGuide(project: MissionProjectSource, job?: Job | null, projectId?: string): MissionGuide {
  const id = projectId ?? project.id;
  const phase = resolveMissionPhase(project, job);
  const phaseIndex =
    phase === "review"
      ? MISSION_PHASES.findIndex((p) => p.id === "deliver")
      : MISSION_PHASES.findIndex((p) => p.id === phase);
  const fileCount = countFiles(project);
  const riskCount = countRisks(project);
  const progress = resolveLiveProgress(project, job);
  const live =
    job?.status === "running" ||
    job?.status === "queued" ||
    (PROCESSING.has(project.status) && project.status !== "completed" && project.status !== "accepted");

  const base = { phase, phaseIndex, progress, live };

  switch (phase) {
    case "failed":
      return {
        ...base,
        headline: "观察链路中断",
        detail: job?.error_message || "分析异常终止，请查看执行日志排查",
        action: { label: "查看日志", href: `/projects/${id}/logs` },
      };
    case "deliver": {
      const dStatus = deliverableStatus(project);
      if (project.status === "accepted" || dStatus === "accepted") {
        return {
          ...base,
          headline: "验收通过",
          detail: `共识别 ${riskCount} 项 Finding · 交付物已确认`,
          action: { label: "查看交付验收", href: `/projects/${id}/outputs` },
        };
      }
      if (project.status === "deliverable_rejected" || dStatus === "rejected") {
        return {
          ...base,
          headline: "交付已退回",
          detail: "请调整资料或说明后重新分析",
          action: { label: "上传资料", href: `/projects/${id}/files` },
        };
      }
      return {
        ...base,
        headline: "待验收交付物",
        detail: `共识别 ${riskCount} 项 Finding · 请下载 ZIP 或逐项查阅后验收`,
        action: { label: "交付验收", href: `/projects/${id}/outputs` },
      };
    }
    case "review":
      return {
        ...base,
        phaseIndex: MISSION_PHASES.findIndex((p) => p.id === "deliver"),
        headline: "待人工复核",
        detail: `${riskCount} 项 ${FINDING} 需确认或调整`,
        action: { label: "逐条复核", href: `/projects/${id}/review` },
      };
    case "processing": {
      const step = WORKFLOW_STEPS.find((s) => s.id === (job?.current_step || project.status));
      return {
        ...base,
        headline: live ? `执行中 · ${step?.label ?? "分析"}` : "分析队列中",
        detail: step?.desc ?? "Agent 正在处理观察资料与证据链",
        action: { label: "实时日志", href: `/projects/${id}/logs` },
      };
    }
    case "ingest": {
      const compliance = isComplianceProject(project);
      const runLabel = compliance ? "运行合规分析" : "启动分析";
      return {
        ...base,
        headline: fileCount > 0 ? `已接入 ${fileCount} 份资料` : "等待资料接入",
        detail:
          fileCount > 0
            ? compliance
              ? "资料就绪，可运行合规分析并生成交付物"
              : "资料就绪，可启动观察分析"
            : "上传观察元数据、A1 导出、签到与证据截图",
        action: { label: fileCount > 0 ? runLabel : "上传资料", href: `/projects/${id}/files` },
      };
    }
    default:
      return {
        ...base,
        headline: "子会议已初始化",
        detail: "第一步：导入或上传会议观察资料",
        action: { label: "上传资料", href: `/projects/${id}/files` },
      };
  }
}
