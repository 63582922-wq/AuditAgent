export type WorkflowStepId =
  | "created"
  | "uploaded"
  | "planning"
  | "classifying"
  | "vision_parsing"
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
  agentSay: string;
  agentDone: string;
  station: string;
};

/** 会议合规观察流程（与后端 AgentWorkflow.STEPS 对齐） */
export const WORKFLOW_STEPS: WorkflowStep[] = [
  {
    id: "created",
    label: "创建子会议",
    short: "创建",
    desc: "建立子会议工作区",
    pct: 0,
    icon: "◆",
    agentSay: "工位已就绪，等你把观察资料交给我。",
    agentDone: "准备好了观察工位",
    station: "立项台",
  },
  {
    id: "uploaded",
    label: "资料入库",
    short: "入库",
    desc: "上传 / 导入 FX 文件夹",
    pct: 2,
    icon: "↑",
    agentSay: "资料已入库，等待主 Agent 接手。",
    agentDone: "观察资料入库完成",
    station: "收发台",
  },
  {
    id: "planning",
    label: "主 Agent 读档·拆解",
    short: "拆解",
    desc: "预览资料结构并拆解子任务",
    pct: 5,
    icon: "◎",
    agentSay: "我先读一遍资料概要，再拆解这次观察要查什么。",
    agentDone: "完成读档预览与任务拆解",
    station: "指挥席",
  },
  {
    id: "classifying",
    label: "资料分类",
    short: "分类",
    desc: "文本 Ingest 识别 A1、签到、确认单等",
    pct: 10,
    icon: "▤",
    agentSay: "按拆解计划辨认 A1 导出、议程还是签到表。",
    agentDone: "完成资料分类",
    station: "分拣台",
  },
  {
    id: "vision_parsing",
    label: "GLM-OCR 读图",
    short: "OCR",
    desc: "视觉 Agent 读图并抽取结构化字段",
    pct: 18,
    icon: "◐",
    agentSay: "正在读图，抽取讲者时长、签到人数与材料编码。",
    agentDone: "完成图片视觉解析",
    station: "视觉席",
  },
  {
    id: "parsing",
    label: "解析文档",
    short: "解析",
    desc: "文本 Ingest · PDF/Excel 结构化解析",
    pct: 25,
    icon: "⎘",
    agentSay: "逐页阅读，整理会议编码与时长信息。",
    agentDone: "解析文档内容",
    station: "阅读席",
  },
  {
    id: "extracting",
    label: "实体抽取",
    short: "抽取",
    desc: "讲者、时长、材料编码",
    pct: 40,
    icon: "⬡",
    agentSay: "提取讲者、预算、材料编码与签到人数。",
    agentDone: "抽取关键实体",
    station: "摘录台",
  },
  {
    id: "running_rules",
    label: "合规规则",
    short: "规则",
    desc: "执行 CMP 检查点",
    pct: 55,
    icon: "⚙",
    agentSay: "对照罗氏政策逐项筛查 Finding。",
    agentDone: "执行合规规则",
    station: "规则台",
  },
  {
    id: "cross_checking",
    label: "交叉比对",
    short: "比对",
    desc: "计划 vs 实际 / 证据链",
    pct: 75,
    icon: "⇄",
    agentSay: "核对 A1 计划、签到与现场确认是否一致。",
    agentDone: "完成交叉比对",
    station: "核对席",
  },
  {
    id: "adjudicating",
    label: "Finding 研判",
    short: "研判",
    desc: "生成 Remote Finding 描述",
    pct: 85,
    icon: "◉",
    agentSay: "为每条命中项撰写 Finding 话术。",
    agentDone: "完成 Finding 研判",
    station: "研判席",
  },
  {
    id: "generating_report",
    label: "生成交付物",
    short: "交付",
    desc: "PDF / Excel Finding",
    pct: 90,
    icon: "⬇",
    agentSay: "整理成 Finding 报告，方便你验收。",
    agentDone: "生成交付物",
    station: "输出台",
  },
  {
    id: "completed",
    label: "观察完成",
    short: "完成",
    desc: "可下载全部交付物",
    pct: 100,
    icon: "✓",
    agentSay: "本轮观察做完了，结论都在交付物里。",
    agentDone: "观察任务完成",
    station: "归档台",
  },
];

export const STATUS_LABEL: Record<string, string> = {
  created: "已创建",
  uploaded: "资料已接入",
  planning: "Agent 规划中",
  classifying: "正在分类",
  parsing: "正在解析",
  extracting: "正在抽取实体",
  running_rules: "正在执行合规规则",
  cross_checking: "正在交叉比对",
  adjudicating: "Finding 研判中",
  generating_report: "正在生成交付物",
  needs_review: "需要人工复核",
  completed: "已完成",
  accepted: "验收通过",
  deliverable_rejected: "交付退回",
  failed: "失败",
  running: "分析中",
  queued: "排队中",
  tool: "工具调用",
  plan: "Agent 规划",
  workflow: "工作流",
  critic: "审核校验 Agent",
  memory: "记忆沉淀",
  runtime: "Agent Runtime",
  react: "ReAct 外环",
  orchestrator: "Orchestrator",
  compliance_harness: "合规分析",
};

export type StepState = "done" | "active" | "pending" | "failed";

export function resolveStepIndex(status: string, steps: WorkflowStep[] = WORKFLOW_STEPS): number {
  if (status === "failed") return -1;
  if (status === "needs_review") {
    const i = steps.findIndex((s) => s.id === "adjudicating");
    return i >= 0 ? i : steps.length - 2;
  }
  const idx = steps.findIndex((s) => s.id === status);
  if (idx >= 0) return idx;
  if (status === "running" || status === "queued") {
    return steps.findIndex((s) => s.id === "planning");
  }
  if (status === "incremental") {
    return steps.findIndex((s) => s.id === "planning");
  }
  return 0;
}

export function getStepStates(
  status: string,
  jobStep?: string,
  jobStatus?: string,
  steps: WorkflowStep[] = WORKFLOW_STEPS
): { step: WorkflowStep; state: StepState }[] {
  const effective = jobStep && jobStatus === "running" ? jobStep : status;
  const failed = status === "failed" || jobStatus === "failed";
  const currentIdx = failed ? -1 : resolveStepIndex(effective, steps);

  return steps.map((step, i) => {
    if (failed) {
      const failAt = resolveStepIndex(jobStep || status, steps);
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
  jobStatus?: string,
  steps: WorkflowStep[] = WORKFLOW_STEPS,
  runtimeLivePct?: number | null
): number {
  if (status === "completed" || status === "accepted") return 100;
  if (jobPct != null && jobStatus === "running") return clampPct(jobPct);
  if (runtimeLivePct != null && isPipelineRunning(status, jobStatus)) return clampPct(runtimeLivePct);
  const idx = resolveStepIndex(jobStep && jobStatus === "running" ? jobStep : status, steps);
  if (idx < 0) return 0;
  return steps[idx]?.pct ?? 0;
}

function clampPct(n: number): number {
  return Math.min(100, Math.max(0, Math.round(n)));
}

export type LiveProgressInput = {
  status: string;
  file_count?: number;
  state_json?: unknown;
};

/** 统一进度：job → runtime_live → 步骤内文件插值 → 步骤基准 */
export function resolveLiveProgress(
  live: LiveProgressInput | null | undefined,
  job?: { current_step?: string; progress_pct?: number; status?: string } | null,
  steps: WorkflowStep[] = WORKFLOW_STEPS
): number {
  if (!live) return 0;
  const state = (live.state_json ?? {}) as {
    runtime_live?: { pct?: number; progress?: number; step?: string };
    processed_file_ids?: string[];
  };
  const runtimePct = state.runtime_live?.pct ?? state.runtime_live?.progress;
  if (job?.progress_pct != null && job.status === "running") {
    return clampPct(job.progress_pct);
  }
  if (runtimePct != null && isPipelineRunning(live.status, job?.status)) {
    return clampPct(runtimePct);
  }
  const step = job?.current_step || state.runtime_live?.step || live.status;
  const total = live.file_count ?? 0;
  const processed = state.processed_file_ids?.length ?? 0;
  if (total > 0 && processed > 0 && (step === "parsing" || step === "classifying")) {
    const idx = steps.findIndex((s) => s.id === step);
    if (idx >= 0) {
      const base = steps[idx]!.pct;
      const next = steps[idx + 1]?.pct ?? base + 15;
      return clampPct(base + (next - base) * (processed / total) * 0.92);
    }
  }
  return overallProgress(live.status, job?.current_step, job?.progress_pct, job?.status, steps, runtimePct);
}

/** 后端正在执行管线步骤（含 Harness / Analyze job） */
export const PIPELINE_RUNNING_STATUSES = new Set<string>([
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

export function isPipelineRunning(status: string, jobStatus?: string | null): boolean {
  if (jobStatus === "running" || jobStatus === "queued") return true;
  return PIPELINE_RUNNING_STATUSES.has(status);
}
