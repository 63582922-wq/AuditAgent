export type WorkflowStepId =
  | "created"
  | "uploaded"
  | "planning"
  | "classifying"
  | "parsing"
  | "extracting"
  | "running_rules"
  | "cross_checking"
  | "adjudicating"
  | "generating_report"
  | "completed"
  | "needs_review"
  | "failed";

export type WorkflowStep = {
  id: WorkflowStepId;
  label: string;
  short: string;
  desc: string;
  pct: number;
  icon: string;
};

/** 完整评估流程（与后端 AgentWorkflow.STEPS 对齐，前置创建/上传） */
export const WORKFLOW_STEPS: WorkflowStep[] = [
  { id: "created", label: "创建项目", short: "创建", desc: "建立评估工作区", pct: 0, icon: "◆" },
  { id: "uploaded", label: "上传资料", short: "上传", desc: "导入财务原始文件", pct: 2, icon: "↑" },
  { id: "planning", label: "Agent 规划", short: "规划", desc: "LLM 制定分析路径", pct: 5, icon: "◎" },
  { id: "classifying", label: "资料分类", short: "分类", desc: "识别文档类型", pct: 10, icon: "▤" },
  { id: "parsing", label: "解析文档", short: "解析", desc: "OCR / 结构化抽取", pct: 25, icon: "⎘" },
  { id: "extracting", label: "实体抽取", short: "抽取", desc: "金额、日期、主体", pct: 40, icon: "⬡" },
  { id: "running_rules", label: "规则引擎", short: "规则", desc: "执行风险规则", pct: 55, icon: "⚙" },
  { id: "cross_checking", label: "交叉比对", short: "比对", desc: "多文件勾稽核对", pct: 75, icon: "⇄" },
  { id: "adjudicating", label: "Agent 研判", short: "研判", desc: "逐条综合判断", pct: 85, icon: "◉" },
  { id: "generating_report", label: "生成交付物", short: "交付", desc: "PDF / Excel 报告", pct: 92, icon: "⬇" },
  { id: "completed", label: "评估完成", short: "完成", desc: "可下载全部交付物", pct: 100, icon: "✓" },
];

export const STATUS_LABEL: Record<string, string> = {
  created: "已创建",
  uploaded: "文件已上传",
  planning: "Agent 规划中",
  classifying: "正在分类",
  parsing: "正在解析",
  extracting: "正在抽取实体",
  running_rules: "正在执行规则",
  cross_checking: "正在交叉比对",
  adjudicating: "Agent 综合研判",
  generating_report: "正在生成报告",
  needs_review: "需要人工复核",
  completed: "已完成",
  failed: "失败",
  running: "分析中",
  queued: "排队中",
};

export type StepState = "done" | "active" | "pending" | "failed";

export function resolveStepIndex(status: string): number {
  if (status === "failed") return -1;
  if (status === "needs_review") {
    const i = WORKFLOW_STEPS.findIndex((s) => s.id === "adjudicating");
    return i >= 0 ? i : WORKFLOW_STEPS.length - 2;
  }
  const idx = WORKFLOW_STEPS.findIndex((s) => s.id === status);
  if (idx >= 0) return idx;
  if (status === "running" || status === "queued") {
    return WORKFLOW_STEPS.findIndex((s) => s.id === "planning");
  }
  return 0;
}

export function getStepStates(
  status: string,
  jobStep?: string,
  jobStatus?: string
): { step: WorkflowStep; state: StepState }[] {
  const effective = jobStep && jobStatus === "running" ? jobStep : status;
  const failed = status === "failed" || jobStatus === "failed";
  const currentIdx = failed ? -1 : resolveStepIndex(effective);

  return WORKFLOW_STEPS.map((step, i) => {
    if (failed) {
      const failAt = resolveStepIndex(jobStep || status);
      if (i < failAt) return { step, state: "done" as StepState };
      if (i === failAt) return { step, state: "failed" as StepState };
      return { step, state: "pending" as StepState };
    }
    if (i < currentIdx) return { step, state: "done" as StepState };
    if (i === currentIdx) return { step, state: "active" as StepState };
    return { step, state: "pending" as StepState };
  });
}

export function overallProgress(
  status: string,
  jobStep?: string,
  jobPct?: number,
  jobStatus?: string
): number {
  if (status === "completed") return 100;
  if (jobPct != null && jobStatus === "running") return jobPct;
  const idx = resolveStepIndex(jobStep && jobStatus === "running" ? jobStep : status);
  if (idx < 0) return 0;
  return WORKFLOW_STEPS[idx]?.pct ?? 0;
}
