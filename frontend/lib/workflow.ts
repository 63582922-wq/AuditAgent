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
  /** 拟人：正在做 */
  agentSay: string;
  /** 拟人：做完后 */
  agentDone: string;
  /** 工位名 */
  station: string;
};

/** 完整评估流程（与后端 AgentWorkflow.STEPS 对齐，前置创建/上传） */
export const WORKFLOW_STEPS: WorkflowStep[] = [
  {
    id: "created",
    label: "创建项目",
    short: "创建",
    desc: "建立评估工作区",
    pct: 0,
    icon: "◆",
    agentSay: "工位已就绪，等你把资料交给我。",
    agentDone: "准备好了评估工位",
    station: "立项台",
  },
  {
    id: "uploaded",
    label: "上传资料",
    short: "上传",
    desc: "导入财务原始文件",
    pct: 2,
    icon: "↑",
    agentSay: "收到资料，我先过目一遍都有什么。",
    agentDone: "接收入库原始资料",
    station: "收发台",
  },
  {
    id: "planning",
    label: "Agent 规划",
    short: "规划",
    desc: "LLM 制定分析路径",
    pct: 5,
    icon: "◎",
    agentSay: "我在构思这次要重点查哪些风险。",
    agentDone: "制定分析计划",
    station: "规划席",
  },
  {
    id: "classifying",
    label: "资料分类",
    short: "分类",
    desc: "识别文档类型",
    pct: 10,
    icon: "▤",
    agentSay: "正在辨认每份文件是发票、台账还是合同。",
    agentDone: "完成资料分类",
    station: "分拣台",
  },
  {
    id: "parsing",
    label: "解析文档",
    short: "解析",
    desc: "OCR / 结构化抽取",
    pct: 25,
    icon: "⎘",
    agentSay: "逐页阅读，把表格和文字整理出来。",
    agentDone: "解析文档内容",
    station: "阅读席",
  },
  {
    id: "extracting",
    label: "实体抽取",
    short: "抽取",
    desc: "金额、日期、主体",
    pct: 40,
    icon: "⬡",
    agentSay: "从材料里找出金额、日期和往来单位。",
    agentDone: "抽取关键实体",
    station: "摘录台",
  },
  {
    id: "running_rules",
    label: "规则引擎",
    short: "规则",
    desc: "执行风险规则",
    pct: 55,
    icon: "⚙",
    agentSay: "拿着规则清单，一项项筛查可疑点。",
    agentDone: "执行风险规则",
    station: "规则台",
  },
  {
    id: "cross_checking",
    label: "交叉比对",
    short: "比对",
    desc: "多文件勾稽核对",
    pct: 75,
    icon: "⇄",
    agentSay: "把不同资料摆在一起，对账、勾稽。",
    agentDone: "完成交叉比对",
    station: "核对席",
  },
  {
    id: "adjudicating",
    label: "Agent 研判",
    short: "研判",
    desc: "逐条综合判断",
    pct: 85,
    icon: "◉",
    agentSay: "综合判断每条疑点的风险等级。",
    agentDone: "完成风险研判",
    station: "研判席",
  },
  {
    id: "generating_report",
    label: "生成交付物",
    short: "交付",
    desc: "PDF / Excel 报告",
    pct: 90,
    icon: "⬇",
    agentSay: "整理成报告和清单，方便你复核。",
    agentDone: "生成交付物",
    station: "输出台",
  },
  {
    id: "completed",
    label: "评估完成",
    short: "完成",
    desc: "可下载全部交付物",
    pct: 100,
    icon: "✓",
    agentSay: "这一轮评估做完了，结论都在交付物里。",
    agentDone: "评估任务完成",
    station: "归档台",
  },
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
  accepted: "验收通过",
  deliverable_rejected: "交付退回",
  failed: "失败",
  running: "分析中",
  queued: "排队中",
  tool: "工具调用",
  plan: "Agent 规划",
  workflow: "工作流",
  critic: "Critic 质检",
  memory: "记忆沉淀",
  runtime: "Agent Runtime",
  react: "ReAct 外环",
  orchestrator: "Orchestrator",
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
  // 局部/增量任务 scope（后端 job.current_step）
  if (status === "incremental") {
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
  if (status === "completed" || status === "accepted") return 100;
  if (jobPct != null && jobStatus === "running") return jobPct;
  const idx = resolveStepIndex(jobStep && jobStatus === "running" ? jobStep : status);
  if (idx < 0) return 0;
  return WORKFLOW_STEPS[idx]?.pct ?? 0;
}
