/**
 * Agent 管线拓扑 — 全节点（含子 Agent 专员）+ 双并行 ingest + 资料池 + 规则/比对分叉
 *
 * 入库 → 主Agent ─┬→ 视觉/OCR ──┐
 *                 └→ 文本Ingest ┴→ 资料池 ─┬→ 规则 → [子Agent…] ──┐
 *                                          └→ 比对 → [子Agent…] ──┴→ 研判 → Critic → 交付
 */

import type { ActivityLog } from "@/components/ActivityTimeline";
import {
  deriveLogGraphSignals,
  mergeSubAgentsFromLogs,
  primaryNodeFromJobStep,
  syncGraphWithLogs,
} from "@/lib/pipeline-graph-logs";
import { WorkflowStepId, getStepStates, isPipelineRunning, overallProgress } from "@/lib/workflow";
import { agentLabel } from "@/lib/domain";

export type GraphNodeKind = "stage" | "agent" | "gate" | "vision" | "ingest" | "pool";

export type GraphNodeDef = {
  id: string;
  label: string;
  short: string;
  kind: GraphNodeKind;
  x: number;
  y: number;
  stepIds?: WorkflowStepId[];
};

export type GraphEdgeDef = {
  from: string;
  to: string;
};

/** 固定状态拓扑（渲染层 viewBox 920×720）
 *  AgentGraph 将状态拓扑映射为知识图谱视图：上半区承载 Agent 链路，下半区承载全量日志事件映射。
 */
export const PIPELINE_NODES: GraphNodeDef[] = [
  {
    id: "upload",
    label: "资料入库",
    short: "入库",
    kind: "stage",
    x: 106,
    y: 318,
    stepIds: ["uploaded"],
  },
  {
    id: "main",
    label: "主 Agent",
    short: "主",
    kind: "agent",
    x: 228,
    y: 318,
    stepIds: ["planning", "adjudicating", "generating_report"],
  },
  {
    id: "vision",
    label: "视觉 Agent",
    short: "OCR",
    kind: "vision",
    x: 338,
    y: 170,
    stepIds: ["vision_parsing"],
  },
  {
    id: "textIngest",
    label: "文本 Ingest",
    short: "读档",
    kind: "ingest",
    x: 342,
    y: 452,
    stepIds: ["classifying", "parsing", "extracting"],
  },
  {
    id: "parsedPool",
    label: "资料池",
    short: "池",
    kind: "pool",
    x: 458,
    y: 318,
  },
  {
    id: "rules",
    label: "CMP 规则",
    short: "规则",
    kind: "stage",
    x: 572,
    y: 172,
    stepIds: ["running_rules"],
  },
  {
    id: "cross",
    label: "交叉比对",
    short: "比对",
    kind: "stage",
    x: 572,
    y: 452,
    stepIds: ["cross_checking"],
  },
  {
    id: "adjudicate",
    label: "Finding 研判",
    short: "研判",
    kind: "stage",
    x: 700,
    y: 318,
    stepIds: ["adjudicating"],
  },
  {
    id: "critic",
    label: "审核校验",
    short: "校验",
    kind: "gate",
    x: 812,
    y: 318,
    stepIds: [],
  },
  {
    id: "deliver",
    label: "交付物",
    short: "交付",
    kind: "stage",
    x: 808,
    y: 452,
    stepIds: ["generating_report", "completed"],
  },
];

export const PIPELINE_EDGES: GraphEdgeDef[] = [
  { from: "upload", to: "main" },
  { from: "main", to: "vision" },
  { from: "main", to: "textIngest" },
  { from: "vision", to: "parsedPool" },
  { from: "textIngest", to: "parsedPool" },
  { from: "parsedPool", to: "rules" },
  { from: "parsedPool", to: "cross" },
  { from: "rules", to: "adjudicate" },
  { from: "cross", to: "adjudicate" },
  { from: "adjudicate", to: "critic" },
  { from: "critic", to: "deliver" },
];

export type SubAgentNode = { id: string; name: string; station?: string };

export type GraphNodeState = "done" | "active" | "pending" | "failed";

export type RuntimeSubNode = {
  id: string;
  label: string;
  short: string;
  kind: GraphNodeKind;
  x: number;
  y: number;
  state: GraphNodeState;
  branch: "rules" | "cross";
};

const RULES_AGENT_IDS = new Set(["speaker", "policy", "meeting_plan", "invoice", "tax", "ledger"]);
const CROSS_AGENT_IDS = new Set(["attendance", "evidence", "treasury", "contract"]);

const RULES_SUB_Y = [126, 174, 222];
const CROSS_SUB_Y = [414, 462, 510];
const SUB_X = 650;

const POST_VISION_STEPS: WorkflowStepId[] = [
  "parsing",
  "extracting",
  "running_rules",
  "cross_checking",
  "adjudicating",
  "generating_report",
  "completed",
];

function partitionSubAgents(subAgents: SubAgentNode[]): { rules: SubAgentNode[]; cross: SubAgentNode[] } {
  const rules: SubAgentNode[] = [];
  const cross: SubAgentNode[] = [];
  const unassigned: SubAgentNode[] = [];

  for (const sa of subAgents) {
    if (RULES_AGENT_IDS.has(sa.id)) rules.push(sa);
    else if (CROSS_AGENT_IDS.has(sa.id)) cross.push(sa);
    else unassigned.push(sa);
  }

  for (const sa of unassigned) {
    if (rules.length <= cross.length) rules.push(sa);
    else cross.push(sa);
  }

  return { rules, cross };
}

function subAgentState(branch: "rules" | "cross", nodeStates: Map<string, GraphNodeState>): GraphNodeState {
  const anchor = nodeStates.get(branch) ?? "pending";
  const pool = nodeStates.get("parsedPool") ?? "pending";
  if (anchor === "failed") return "failed";
  if (anchor === "done") return "done";
  if (anchor === "active") return "active";
  if (pool === "done" || pool === "active") return "pending";
  return "pending";
}

function buildSubAgentNodes(
  subAgents: SubAgentNode[],
  nodeStates: Map<string, GraphNodeState>
): { subNodes: RuntimeSubNode[]; subEdges: GraphEdgeDef[] } {
  const { rules, cross } = partitionSubAgents(subAgents);
  const subNodes: RuntimeSubNode[] = [];
  const subEdges: GraphEdgeDef[] = [];

  rules.forEach((sa, i) => {
    const id = `sub-${sa.id}`;
    subNodes.push({
      id,
      label: sa.name || agentLabel(sa.id),
      short: (sa.station || agentLabel(sa.id)).slice(0, 2),
      kind: "agent",
      x: SUB_X,
      y: RULES_SUB_Y[i] ?? 126 + i * 48,
      state: subAgentState("rules", nodeStates),
      branch: "rules",
    });
    subEdges.push({ from: "rules", to: id });
    subEdges.push({ from: id, to: "adjudicate" });
  });

  cross.forEach((sa, i) => {
    const id = `sub-${sa.id}`;
    subNodes.push({
      id,
      label: sa.name || agentLabel(sa.id),
      short: (sa.station || agentLabel(sa.id)).slice(0, 2),
      kind: "agent",
      x: SUB_X,
      y: CROSS_SUB_Y[i] ?? 414 + i * 48,
      state: subAgentState("cross", nodeStates),
      branch: "cross",
    });
    subEdges.push({ from: "cross", to: id });
    subEdges.push({ from: id, to: "adjudicate" });
  });

  return { subNodes, subEdges };
}

function resolveParsedPoolState(nodeStates: Map<string, GraphNodeState>): GraphNodeState {
  const vision = nodeStates.get("vision") ?? "pending";
  const text = nodeStates.get("textIngest") ?? "pending";
  if (vision === "failed" || text === "failed") return "failed";

  const rules = nodeStates.get("rules") ?? "pending";
  const cross = nodeStates.get("cross") ?? "pending";
  const downstreamStarted = rules !== "pending" || cross !== "pending";

  const visionDone = vision === "done";
  const textDone = text === "done";
  const noVisionRun = vision === "pending" && downstreamStarted;

  if (downstreamStarted && textDone && (visionDone || noVisionRun)) return "done";
  if (vision === "active" || text === "active") return "active";
  if (visionDone && textDone) return "done";
  if (textDone && noVisionRun) return "done";
  if (visionDone || textDone) return "active";
  return "pending";
}

function resolveMainNodeState(
  steps: ReturnType<typeof getStepStates>,
  activeStep: string | undefined,
  status: string
): GraphNodeState {
  const planning = steps.find((s) => s.step.id === "planning")?.state ?? "pending";
  const adjudicating = steps.find((s) => s.step.id === "adjudicating")?.state ?? "pending";
  const report = steps.find((s) => s.step.id === "generating_report")?.state ?? "pending";

  if (planning === "failed" || adjudicating === "failed" || report === "failed") return "failed";
  if (activeStep === "planning" || activeStep === "adjudicating" || activeStep === "generating_report")
    return "active";
  if (planning === "done" && adjudicating === "done" && report === "done") return "done";
  if (status === "completed" || status === "accepted") return "done";
  if (planning === "done" && (adjudicating === "active" || report === "active" || adjudicating === "done"))
    return adjudicating === "done" && report === "done" ? "done" : "active";
  if (planning === "done") return "done";
  if (planning === "active") return "active";
  return "pending";
}

function resolveDeliverNodeState(
  steps: ReturnType<typeof getStepStates>,
  activeStep: string | undefined,
  status: string
): GraphNodeState {
  const report = steps.find((s) => s.step.id === "generating_report")?.state ?? "pending";
  if (report === "failed") return "failed";
  if (activeStep === "generating_report" || activeStep === "completed") return "active";
  if (status === "completed" || status === "accepted" || report === "done") return "done";
  return "pending";
}

export function buildRuntimeGraph(params: {
  status: string;
  jobStep?: string;
  jobPct?: number;
  jobStatus?: string;
  subAgents?: SubAgentNode[];
  criticDone?: boolean;
  criticActive?: boolean;
  traceLogs?: ActivityLog[];
}) {
  const { status, jobStep, jobStatus, criticDone, criticActive, traceLogs = [] } = params;
  const subAgents = mergeSubAgentsFromLogs(params.subAgents ?? [], traceLogs);
  const steps = getStepStates(status, jobStep, jobStatus);
  const failed = status === "failed" || jobStatus === "failed";
  const activeStep = steps.find((s) => s.state === "active")?.step.id;
  const progress = overallProgress(status, jobStep, params.jobPct, jobStatus);

  const nodeStates = new Map<string, GraphNodeState>();

  for (const n of PIPELINE_NODES) {
    if (failed) {
      nodeStates.set(n.id, "pending");
      continue;
    }
    if (n.id === "main") {
      nodeStates.set(n.id, resolveMainNodeState(steps, activeStep, status));
      continue;
    }
    if (n.id === "deliver") {
      nodeStates.set(n.id, resolveDeliverNodeState(steps, activeStep, status));
      continue;
    }
    if (n.id === "critic") {
      if (criticActive) nodeStates.set(n.id, "active");
      else if (criticDone || status === "completed" || status === "accepted") nodeStates.set(n.id, "done");
      else nodeStates.set(n.id, "pending");
      continue;
    }
    if (n.id === "vision") {
      if (activeStep === "vision_parsing") nodeStates.set(n.id, "active");
      else if (activeStep && POST_VISION_STEPS.includes(activeStep as WorkflowStepId))
        nodeStates.set(n.id, "done");
      else if (status === "completed" || status === "accepted") nodeStates.set(n.id, "done");
      else nodeStates.set(n.id, "pending");
      continue;
    }
    if (n.id === "parsedPool") {
      continue;
    }
    const related = n.stepIds ?? [];
    if (related.length === 0) {
      nodeStates.set(n.id, "pending");
      continue;
    }
    const states = related.map((sid) => steps.find((s) => s.step.id === sid)?.state ?? "pending");
    if (states.some((s) => s === "failed")) nodeStates.set(n.id, "failed");
    else if (states.some((s) => s === "active") || related.includes(activeStep as WorkflowStepId))
      nodeStates.set(n.id, "active");
    else if (states.every((s) => s === "done")) nodeStates.set(n.id, "done");
    else if (states.some((s) => s === "done")) nodeStates.set(n.id, "active");
    else nodeStates.set(n.id, "pending");
  }

  if (!failed) {
    nodeStates.set("parsedPool", resolveParsedPoolState(nodeStates));
  }

  if (status === "completed" || status === "accepted") {
    for (const n of PIPELINE_NODES) {
      if (nodeStates.get(n.id) !== "failed") nodeStates.set(n.id, "done");
    }
  }

  const { subNodes, subEdges } = buildSubAgentNodes(subAgents, nodeStates);

  const pipelineRunning = isPipelineRunning(status, jobStatus);
  const logSignals = deriveLogGraphSignals(traceLogs, subAgents);
  const jobBaseline = new Map(nodeStates);
  for (const sn of subNodes) jobBaseline.set(sn.id, sn.state);

  if (!failed && pipelineRunning && traceLogs.length > 0) {
    syncGraphWithLogs(nodeStates, subNodes, logSignals, jobBaseline);
  } else if (!failed && pipelineRunning) {
    const fallback = primaryNodeFromJobStep(activeStep);
    if (fallback) {
      for (const [id, st] of nodeStates) {
        if (st === "active" && id !== fallback) {
          nodeStates.set(id, jobBaseline.get(id) === "done" ? "done" : "pending");
        }
      }
      for (const sn of subNodes) {
        if (sn.state === "active" && sn.id !== fallback) {
          sn.state = jobBaseline.get(sn.id) === "done" ? "done" : "pending";
        }
      }
      nodeStates.set(fallback, "active");
      const sub = subNodes.find((s) => s.id === fallback);
      if (sub) sub.state = "active";
    }
  }

  if (!failed && !logSignals.activeNodeId && pipelineRunning) {
    nodeStates.set("parsedPool", resolveParsedPoolState(nodeStates));
  }

  if (status === "completed" || status === "accepted") {
    for (const sn of subNodes) {
      if (sn.state !== "failed") sn.state = "done";
    }
  }

  const hasSubs = subNodes.length > 0;
  const pipelineEdges = hasSubs
    ? PIPELINE_EDGES.filter(
        (e) =>
          !(e.from === "rules" && e.to === "adjudicate") &&
          !(e.from === "cross" && e.to === "adjudicate")
      )
    : PIPELINE_EDGES;

  const activeNodeId =
    logSignals.activeNodeId ??
    (pipelineRunning ? primaryNodeFromJobStep(activeStep) : null) ??
    PIPELINE_NODES.map((n) => n.id).find((id) => nodeStates.get(id) === "active") ??
    subNodes.find((sn) => sn.state === "active")?.id ??
    null;

  return {
    nodeStates,
    subNodes,
    subEdges,
    pipelineEdges,
    progress,
    activeStep,
    activeNodeId,
    logSignals,
    failed,
  };
}

export function buildCombinedNodeStates(
  nodeStates: Map<string, GraphNodeState>,
  subNodes: RuntimeSubNode[]
): Map<string, GraphNodeState> {
  const all = new Map(nodeStates);
  for (const sn of subNodes) {
    all.set(sn.id, sn.state);
  }
  return all;
}

export function edgeState(
  from: string,
  to: string,
  nodeStates: Map<string, GraphNodeState>
): GraphNodeState {
  const a = nodeStates.get(from) ?? "pending";
  const b = nodeStates.get(to) ?? "pending";
  if (a === "failed" || b === "failed") return "failed";
  if (b === "active") return "active";
  if (a === "done" && b === "done") return "done";
  if (a === "active") return "active";
  return "pending";
}

/** 主 Agent 当前阶段文案（图谱脚注） */
export function mainAgentPhaseLabel(activeStep?: string): string {
  switch (activeStep) {
    case "planning":
      return "主 Agent 读档预览并拆解任务，委派视觉/文本 Ingest 与子 Agent";
    case "classifying":
      return "文本 Ingest 分拣资料类型";
    case "vision_parsing":
      return "视觉 Agent（GLM-OCR）读图并抽取结构化字段";
    case "parsing":
    case "extracting":
      return "OCR 与文本读档汇入资料池（parsed_docs）";
    case "running_rules":
      return "规则子 Agent 从资料池读取并执行 CMP 规则扫描";
    case "cross_checking":
      return "比对子 Agent 从资料池读取并执行交叉比对与勾稽";
    case "adjudicating":
    case "generating_report":
      return "主 Agent 汇总研判并生成交付物";
    default:
      return "主 Agent 拆解调度 → 资料池 → 子 Agent 规则/比对 → 审核校验";
  }
}
