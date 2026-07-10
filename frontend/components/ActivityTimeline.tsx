"use client";

import { formatTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { statusLabel } from "@/lib/i18n/workflow-steps";

export type ActivityLog = {
  id: string;
  step: string;
  status: string;
  detail_json?: Record<string, unknown>;
  duration_ms?: number;
  created_at: string;
};

export function traceLogTitle(
  log: ActivityLog,
  t: (k: string, v?: Record<string, string | number>) => string,
  messages: ReturnType<typeof useI18n>["messages"],
): string {
  const detail = log.detail_json || {};
  const kind = String(detail.kind || "step");
  const name = String(detail.name || log.step);
  if (kind === "plan") return t("workflow.logTitle.plan");
  if (kind === "mission") return t("workflow.logTitle.mission");
  if (kind === "critic") return t("workflow.logTitle.critic");
  if (kind === "memory") return t("workflow.logTitle.memory");
  if (kind === "runtime") return t("workflow.logTitle.runtime");
  if (kind === "react") return t("workflow.logTitle.react");
  if (kind === "sub_agent") return t("workflow.logTitle.subAgent", { name });
  if (kind === "main_agent") return t("workflow.logTitle.mainAgent", { name });
  if (kind === "orchestrator") return t("workflow.logTitle.orchestrator");
  if (kind === "vision_agent")
    return t("workflow.logTitle.visionAgent", { name: name || "视觉 Agent" });
  if (kind === "text_ingest")
    return t("workflow.logTitle.textIngest", { name: name || "文本 Ingest" });
  if (kind === "tool") {
    const mcp = detail.mcp === true || name.startsWith("mcp_");
    return mcp ? t("workflow.logTitle.mcpTool", { name }) : t("workflow.logTitle.tool", { name });
  }
  if (log.step === "orchestrator") return t("workflow.logTitle.orchestrator");
  return statusLabel(log.step, messages) || statusLabel(name, messages) || name;
}

function logMessage(log: ActivityLog): string | null {
  const detail = log.detail_json || {};
  const message = typeof detail.message === "string" ? detail.message : "";
  if (message) return message;
  const error = typeof detail.error === "string" ? detail.error : "";
  if (error) return error;
  if (
    detail.kind === "plan" &&
    detail.execution_graph &&
    typeof detail.execution_graph === "object"
  ) {
    const graph = detail.execution_graph as Record<string, unknown>;
    if (typeof graph.agent_message === "string") return graph.agent_message;
  }
  return null;
}

function logMeta(
  log: ActivityLog,
  t: (k: string, v?: Record<string, string | number>) => string,
  messages: ReturnType<typeof useI18n>["messages"],
): string[] {
  const detail = log.detail_json || {};
  const parts: string[] = [log.status];
  const kind = detail.kind ? String(detail.kind) : "";
  if (kind && messages.workflow.logKind[kind]) parts.push(messages.workflow.logKind[kind]);
  if (log.duration_ms != null) parts.push(`${log.duration_ms} ms`);
  if (detail.modules && Array.isArray(detail.modules)) {
    parts.push(t("settings.logMetaModules", { list: (detail.modules as string[]).join(", ") }));
  }
  if (typeof detail.rule_hits === "number")
    parts.push(t("settings.logMetaHits", { count: detail.rule_hits }));
  if (typeof detail.risk_count === "number")
    parts.push(t("settings.logMetaFindings", { count: detail.risk_count }));
  if (typeof detail.readjudicate_rounds === "number" && detail.readjudicate_rounds > 0) {
    parts.push(t("settings.logMetaRounds", { rounds: detail.readjudicate_rounds }));
  }
  if (typeof detail.retry_attempt === "number" && typeof detail.retry_max === "number") {
    parts.push(
      t("settings.logMetaRetry", { attempt: detail.retry_attempt, max: detail.retry_max }),
    );
  }
  if (typeof detail.wait_sec === "number") {
    parts.push(t("settings.logMetaWaitSec", { sec: detail.wait_sec }));
  }
  if (typeof detail.code === "string" && detail.code) {
    parts.push(detail.code);
  }
  if (detail.code_location && typeof detail.code_location === "object") {
    const loc = detail.code_location as {
      file?: unknown;
      line?: unknown;
      function?: unknown;
    };
    const file = typeof loc.file === "string" ? loc.file : "";
    const line =
      typeof loc.line === "number" || typeof loc.line === "string" ? String(loc.line) : "";
    const fn = typeof loc.function === "string" ? loc.function : "";
    if (file && line) {
      parts.push(`${file}:${line}${fn ? ` · ${fn}()` : ""}`);
    }
  }
  if (detail.brief && typeof detail.brief === "object") {
    const brief = detail.brief as { tools_used?: string[] };
    if (brief.tools_used?.length)
      parts.push(t("settings.logMetaTools", { count: brief.tools_used.length }));
  }
  return parts;
}

function auditDetail(detail: Record<string, unknown>) {
  // Preserve production auditability without exposing broad raw payloads.
  const allow = [
    "run_id",
    "kind",
    "name",
    "code_location",
    "agent_id",
    "tool_name",
    "mcp",
    "retry_attempt",
    "retry_max",
    "wait_sec",
    "code",
    "rule_outcome_counts",
    "evidence_gate",
    "job_id",
  ];
  return Object.fromEntries(allow.filter((key) => detail[key] !== undefined).map((key) => [key, detail[key]]));
}

export function pickLiveAgentMessage(logs: ActivityLog[]): string | null {
  for (let i = logs.length - 1; i >= 0; i -= 1) {
    const msg = logMessage(logs[i]!);
    if (msg) return msg;
  }
  return null;
}

export function pickRecentTraceLogs(logs: ActivityLog[], limit = 6): ActivityLog[] {
  return logs.slice(-limit);
}

export function ActivityTimeline({ logs }: { logs: ActivityLog[] }) {
  const { t, messages } = useI18n();

  if (!logs.length) {
    return <p className="timeline-empty">{t("settings.timelineEmpty")}</p>;
  }

  const sorted = [...logs].reverse();

  return (
    <div className="timeline">
      {sorted.map((log) => {
        const message = logMessage(log);
        const detail = log.detail_json || {};
        const showRaw =
          detail.kind !== "plan" &&
          Object.keys(detail).filter(
            (k) => !["kind", "name", "message", "code_location"].includes(k),
          ).length > 0;
        const audit = auditDetail(detail);
        const hasAudit = Object.keys(audit).length > 0;

        return (
          <div className="timeline__item" key={log.id}>
            <time className="timeline__time">{formatTime(log.created_at)}</time>
            <div>
              <div className="timeline__title">{traceLogTitle(log, t, messages)}</div>
              {message && <p className="timeline__message">{message}</p>}
              <div className="timeline__meta">
                {logMeta(log, t, messages).map((part) => (
                  <span key={part}>{part}</span>
                ))}
              </div>
              {hasAudit && (
                <details className="timeline__audit-detail">
                  <summary>审计详情</summary>
                  <pre>{JSON.stringify(audit, null, 2)}</pre>
                </details>
              )}
              {showRaw && process.env.NODE_ENV === "development" && (
                <pre className="timeline__detail">{JSON.stringify(detail, null, 2)}</pre>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
