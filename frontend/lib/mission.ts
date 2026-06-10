import { Job, ProjectLive } from "@/lib/api";
import { WORKFLOW_STEPS, overallProgress } from "@/lib/workflow";

export type MissionPhase = "init" | "ingest" | "processing" | "deliver" | "review" | "failed";

export type MissionPhaseDef = {
  id: MissionPhase;
  label: string;
  short: string;
  icon: string;
};

/** 用户可感知的宏观链路：资料 → 分析 → 交付（复核为遗留路径） */
export const MISSION_PHASES: MissionPhaseDef[] = [
  { id: "init", label: "初始化", short: "INIT", icon: "01" },
  { id: "ingest", label: "资料接入", short: "INGEST", icon: "02" },
  { id: "processing", label: "Agent 分析", short: "RUN", icon: "03" },
  { id: "deliver", label: "交付验收", short: "OUTPUT", icon: "04" },
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
  const phaseIndex = MISSION_PHASES.findIndex((p) => p.id === phase);
  const fileCount = countFiles(project);
  const riskCount = countRisks(project);
  const progress = overallProgress(project.status, job?.current_step, job?.progress_pct, job?.status);
  const live = job?.status === "running";

  const base = { phase, phaseIndex, progress, live };

  switch (phase) {
    case "failed":
      return {
        ...base,
        headline: "链路中断 · SIGNAL LOST",
        detail: job?.error_message || "分析异常终止，请查看执行日志排查",
        action: { label: "查看日志", href: `/projects/${id}/logs` },
      };
    case "deliver": {
      const dStatus = deliverableStatus(project);
      if (project.status === "accepted" || dStatus === "accepted") {
        return {
          ...base,
          headline: "验收通过 · ACCEPTED",
          detail: `共识别 ${riskCount} 项风险 · 交付物已确认`,
          action: { label: "查看交付物", href: `/projects/${id}/outputs` },
        };
      }
      if (project.status === "deliverable_rejected" || dStatus === "rejected") {
        return {
          ...base,
          headline: "已退回 · REJECTED",
          detail: "请调整资料或说明后重新分析",
          action: { label: "重新分析", href: `/projects/${id}/files` },
        };
      }
      return {
        ...base,
        headline: "待验收 · AWAITING SIGN-OFF",
        detail: `共识别 ${riskCount} 项风险 · PDF/Excel 已生成，请验收交付物`,
        action: { label: "验收交付物", href: `/projects/${id}/outputs` },
      };
    }
    case "review":
      return {
        ...base,
        headline: "待人工复核 · REVIEW REQUIRED",
        detail: `${riskCount} 项风险需确认或调整`,
        action: { label: "进入复核", href: `/projects/${id}/review` },
      };
    case "processing": {
      const step = WORKFLOW_STEPS.find((s) => s.id === (job?.current_step || project.status));
      return {
        ...base,
        headline: live ? `执行中 · ${step?.label ?? "分析"}` : "分析队列中",
        detail: step?.desc ?? "Agent 正在处理财务资料",
        action: { label: "实时日志", href: `/projects/${id}/logs` },
      };
    }
    case "ingest":
      return {
        ...base,
        headline: fileCount > 0 ? `已接入 ${fileCount} 份资料` : "等待资料接入",
        detail: fileCount > 0 ? "资料就绪，启动 Agent 全链路分析" : "上传 xlsx / csv / docx / pdf 等原始文件",
        action: { label: fileCount > 0 ? "启动分析" : "上传资料", href: `/projects/${id}/files` },
      };
    default:
      return {
        ...base,
        headline: "项目已初始化",
        detail: "第一步：上传财务原始资料，开启评估链路",
        action: { label: "上传资料", href: `/projects/${id}/files` },
      };
  }
}
