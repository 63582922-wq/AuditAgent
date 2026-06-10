"use client";

import { STATUS_LABEL } from "@/lib/workflow";
import { formatTime } from "@/lib/format";

export type ActivityLog = {
  id: string;
  step: string;
  status: string;
  detail_json?: Record<string, unknown>;
  duration_ms?: number;
  created_at: string;
};

const KIND_LABEL: Record<string, string> = {
  step: "步骤",
  tool: "工具",
  plan: "规划",
  llm: "推理",
  critic: "Critic",
  memory: "记忆",
  react: "ReAct",
  sub_agent: "子 Agent",
  main_agent: "主 Agent",
  orchestrator: "Orchestrator",
  mission: "任务拆解",
  runtime: "Runtime",
};

function logTitle(log: ActivityLog): string {
  const detail = log.detail_json || {};
  const kind = String(detail.kind || "step");
  const name = String(detail.name || log.step);
  if (kind === "plan") return "Agent 执行计划";
  if (kind === "mission") return "主 Agent 任务拆解";
  if (kind === "critic") return "Critic 证据链质检";
  if (kind === "memory") return "长期记忆沉淀";
  if (kind === "runtime") return "Agent Runtime";
  if (kind === "react") return "ReAct 调度";
  if (kind === "sub_agent") return `子 Agent · ${name}`;
  if (kind === "main_agent") return `主 Agent · ${name}`;
  if (kind === "orchestrator") return "Orchestrator";
  if (kind === "tool") {
    const mcp = detail.mcp === true || name.startsWith("mcp_");
    return mcp ? `MCP 工具 · ${name}` : `工具 · ${name}`;
  }
  if (log.step === "orchestrator") return "Orchestrator";
  return STATUS_LABEL[log.step] || STATUS_LABEL[name] || name;
}

function logMessage(log: ActivityLog): string | null {
  const detail = log.detail_json || {};
  const message = typeof detail.message === "string" ? detail.message : "";
  if (message) return message;
  if (detail.kind === "plan" && detail.execution_graph && typeof detail.execution_graph === "object") {
    const graph = detail.execution_graph as Record<string, unknown>;
    if (typeof graph.agent_message === "string") return graph.agent_message;
  }
  return null;
}

function logMeta(log: ActivityLog): string[] {
  const detail = log.detail_json || {};
  const parts: string[] = [log.status];
  const kind = detail.kind ? String(detail.kind) : "";
  if (kind && KIND_LABEL[kind]) parts.push(KIND_LABEL[kind]);
  if (log.duration_ms != null) parts.push(`${log.duration_ms} ms`);
  if (detail.modules && Array.isArray(detail.modules)) {
    parts.push(`模块: ${(detail.modules as string[]).join(", ")}`);
  }
  if (typeof detail.rule_hits === "number") parts.push(`命中 ${detail.rule_hits} 条`);
  if (typeof detail.risk_count === "number") parts.push(`${detail.risk_count} 项风险`);
  if (typeof detail.readjudicate_rounds === "number" && detail.readjudicate_rounds > 0) {
    parts.push(`重研判 ${detail.readjudicate_rounds} 轮`);
  }
  if (detail.brief && typeof detail.brief === "object") {
    const brief = detail.brief as { tools_used?: string[] };
    if (brief.tools_used?.length) parts.push(`工具 ${brief.tools_used.length} 次`);
  }
  return parts;
}

export function ActivityTimeline({ logs }: { logs: ActivityLog[] }) {
  if (!logs.length) {
    return <p className="timeline-empty">执行分析后，Agent 步骤、工具调用与耗时将在此记录</p>;
  }

  const sorted = [...logs].reverse();

  return (
    <div className="timeline">
      {sorted.map((log) => {
        const message = logMessage(log);
        const detail = log.detail_json || {};
        const showRaw =
          detail.kind !== "plan" &&
          Object.keys(detail).filter((k) => !["kind", "name", "message"].includes(k)).length > 0;

        return (
          <div className="timeline__item" key={log.id}>
            <time className="timeline__time">{formatTime(log.created_at)}</time>
            <div>
              <div className="timeline__title">{logTitle(log)}</div>
              {message && <p className="timeline__message">{message}</p>}
              <div className="timeline__meta">
                {logMeta(log).map((part) => (
                  <span key={part}>{part}</span>
                ))}
              </div>
              {showRaw && (
                <pre className="timeline__detail">{JSON.stringify(detail, null, 2)}</pre>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
