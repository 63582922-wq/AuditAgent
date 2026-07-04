/**
 * 执行日志 → 管线图谱（以日志为准，单一 active 节点）
 */

import type { ActivityLog } from "@/components/ActivityTimeline";
import type { GraphNodeState, SubAgentNode } from "@/lib/pipeline-graph";
import { COMPLIANCE_AGENT_LABELS, agentLabel } from "@/lib/domain";

const STEP_PRIMARY: Record<string, string> = {
  uploaded: "upload",
  planning: "main",
  classifying: "textIngest",
  vision_parsing: "vision",
  parsing: "textIngest",
  extracting: "textIngest",
  running_rules: "rules",
  cross_checking: "cross",
  adjudicating: "adjudicate",
  generating_report: "deliver",
  completed: "deliver",
};

function inferAgentIdFromName(name: string): string {
  for (const [id, label] of Object.entries(COMPLIANCE_AGENT_LABELS)) {
    if (name === label || name.includes(label)) return id;
  }
  return `agent-${name.replace(/\s+/g, "_").slice(0, 32)}`;
}

function resolveSubAgentId(
  detail: Record<string, unknown>,
  name: string,
  subAgents: SubAgentNode[]
): string | null {
  const brief = detail.brief;
  if (brief && typeof brief === "object") {
    const agentId = (brief as { agent_id?: string }).agent_id;
    if (agentId) return agentId;
  }
  if (typeof detail.agent_id === "string" && detail.agent_id) return detail.agent_id;
  for (const sa of subAgents) {
    if (sa.name === name || agentLabel(sa.id) === name) return sa.id;
  }
  if (name) return inferAgentIdFromName(name);
  return null;
}

/** 一条日志 → 唯一图谱节点 id */
export function pickPrimaryNodeFromLog(
  log: ActivityLog,
  subAgents: SubAgentNode[] = []
): string | null {
  const detail = log.detail_json || {};
  const kind = String(detail.kind || "step");
  const name = String(detail.name || log.step);

  if (kind === "vision_agent") return "vision";
  if (kind === "text_ingest") return "textIngest";
  if (kind === "critic") return "critic";
  if (kind === "plan" || kind === "mission" || kind === "react") return "main";
  if (kind === "main_agent") {
    const steps = Array.isArray(detail.steps) ? (detail.steps as string[]) : [];
    if (steps.includes("generating_report")) return "deliver";
    if (steps.includes("adjudicating")) return "adjudicate";
    return "main";
  }
  if (kind === "sub_agent") {
    const agentId = resolveSubAgentId(detail, name, subAgents);
    return agentId ? `sub-${agentId}` : null;
  }
  if (kind === "step") return STEP_PRIMARY[log.step] ?? STEP_PRIMARY[name] ?? null;
  if (log.step === "orchestrator") return "main";

  return STEP_PRIMARY[log.step] ?? null;
}

export type LogGraphSignals = {
  activeNodeId: string | null;
  doneNodeIds: Set<string>;
  failedNodeIds: Set<string>;
  runningLog: ActivityLog | null;
  footnoteLog: ActivityLog | null;
};

/** 从日志补全 state_json 里还没有的子 Agent 节点 */
export function mergeSubAgentsFromLogs(
  subAgents: SubAgentNode[],
  logs: ActivityLog[]
): SubAgentNode[] {
  const map = new Map(subAgents.map((s) => [s.id, s]));

  for (const log of logs) {
    const detail = log.detail_json || {};
    const kind = String(detail.kind || "");
    const name = String(detail.name || "");

    if (kind === "sub_agent") {
      const id = resolveSubAgentId(detail, name, [...map.values()]);
      if (id && !map.has(id)) {
        map.set(id, { id, name: name || agentLabel(id) });
      }
      continue;
    }

    if (kind === "tool" && typeof detail.agent_id === "string" && detail.agent_id) {
      const id = detail.agent_id;
      if (!["main", "vision_agent", "text_ingest"].includes(id) && !map.has(id)) {
        map.set(id, { id, name: agentLabel(id) });
      }
    }
  }

  return [...map.values()];
}

export function deriveLogGraphSignals(
  logs: ActivityLog[],
  subAgents: SubAgentNode[] = []
): LogGraphSignals {
  const doneNodeIds = new Set<string>();
  const failedNodeIds = new Set<string>();
  let runningLog: ActivityLog | null = null;
  let activeNodeId: string | null = null;
  let footnoteLog: ActivityLog | null = null;

  for (const log of logs) {
    const detail = log.detail_json || {};
    const kind = String(detail.kind || "step");
    if (kind === "tool" || kind === "memory" || kind === "runtime" || kind === "harness") continue;

    const primary = pickPrimaryNodeFromLog(log, subAgents);
    if (!primary) continue;

    if (log.status === "failed" || log.status === "error") {
      failedNodeIds.add(primary);
    } else if (log.status === "running" || log.status === "planned") {
      runningLog = log;
      activeNodeId = primary;
    } else {
      doneNodeIds.add(primary);
    }

    const message = typeof detail.message === "string" ? detail.message : "";
    if (message) footnoteLog = log;
  }

  return {
    activeNodeId,
    doneNodeIds,
    failedNodeIds,
    runningLog,
    footnoteLog: runningLog ?? footnoteLog,
  };
}

export function primaryNodeFromJobStep(step?: string): string | null {
  if (!step) return null;
  return STEP_PRIMARY[step] ?? null;
}

/** 运行中以日志为准重写节点状态（仅一个 active） */
export function syncGraphWithLogs(
  nodeStates: Map<string, GraphNodeState>,
  subNodes: { id: string; state: GraphNodeState }[],
  signals: LogGraphSignals,
  jobBaseline: Map<string, GraphNodeState>
): void {
  const allIds = [...new Set([...nodeStates.keys(), ...subNodes.map((s) => s.id)])];

  for (const id of allIds) {
    const base = jobBaseline.get(id) ?? "pending";
    if (signals.failedNodeIds.has(id)) nodeStates.set(id, "failed");
    else if (signals.doneNodeIds.has(id) || base === "done") nodeStates.set(id, "done");
    else if (base === "failed") nodeStates.set(id, "failed");
    else nodeStates.set(id, "pending");
  }

  for (const sn of subNodes) {
    sn.state = nodeStates.get(sn.id) ?? "pending";
  }

  if (signals.activeNodeId) {
    nodeStates.set(signals.activeNodeId, "active");
    const sub = subNodes.find((s) => s.id === signals.activeNodeId);
    if (sub) sub.state = "active";
  }
}
