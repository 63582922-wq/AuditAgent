"use client";

import { useMemo, useState } from "react";
import { traceLogTitle, type ActivityLog } from "@/components/ActivityTimeline";
import { useI18n } from "@/lib/i18n";
import { useLiveTick } from "@/lib/useLiveTick";

type Props = {
  status: string;
  jobStep?: string;
  jobPct?: number;
  jobStatus?: string;
  live?: boolean;
  embedded?: boolean;
  subAgents?: { id: string; name: string; station?: string }[];
  traceLogs?: ActivityLog[];
  criticSummary?: {
    validated?: number;
    flagged?: number;
    readjudicate_rounds?: number;
  };
};

type Category = "evidence" | "agent" | "tool" | "validation" | "memory" | "system";
type EventState = "done" | "active" | "failed" | "skipped";

type GraphEvent = {
  id: string;
  log: ActivityLog;
  category: Category;
  state: EventState;
  label: string;
  message: string;
  x: number;
  y: number;
};

const LANES: { id: Category; label: string }[] = [
  { id: "evidence", label: "证据识别" },
  { id: "agent", label: "Agent" },
  { id: "tool", label: "工具" },
  { id: "validation", label: "规则与校验" },
  { id: "memory", label: "记忆" },
  { id: "system", label: "系统" },
];

const LANE_Y: Record<Category, number> = {
  evidence: 130,
  agent: 205,
  tool: 280,
  validation: 355,
  memory: 430,
  system: 505,
};

function categoryFor(log: ActivityLog): Category {
  const kind = String(log.detail_json?.kind || "");
  if (["vision_agent", "text_ingest", "evidence"].includes(kind)) return "evidence";
  if (["tool", "react"].includes(kind)) return "tool";
  if (["critic", "evaluation", "rule", "cross_check"].includes(kind)) return "validation";
  if (kind === "memory") return "memory";
  if (["runtime", "harness"].includes(kind)) return "system";
  return "agent";
}

function stateFor(log: ActivityLog): EventState {
  if (log.status === "failed" || log.status === "error") return "failed";
  if (log.status === "running" || log.status === "planned") return "active";
  if (log.status === "skipped") return "skipped";
  return "done";
}

function eventMessage(log: ActivityLog) {
  const detail = log.detail_json || {};
  if (typeof detail.message === "string" && detail.message) return detail.message;
  if (typeof detail.error === "string" && detail.error) return detail.error;
  return String(detail.name || log.step || "运行事件");
}

function eventPath(from: GraphEvent, to: GraphEvent) {
  const direction = to.x - from.x;
  const bend = Math.max(24, Math.min(Math.abs(direction) * 0.46, 72));
  return `M ${from.x} ${from.y} C ${from.x + bend} ${from.y}, ${to.x - bend} ${to.y}, ${to.x} ${to.y}`;
}

function codeLocation(log: ActivityLog) {
  const value = log.detail_json?.code_location;
  if (!value || typeof value !== "object") return "未记录代码位置";
  const item = value as { file?: unknown; line?: unknown; function?: unknown };
  const file = typeof item.file === "string" ? item.file : "";
  const line = typeof item.line === "string" || typeof item.line === "number" ? String(item.line) : "";
  const fn = typeof item.function === "string" ? item.function : "";
  return file ? `${file}${line ? `:${line}` : ""}${fn ? ` · ${fn}()` : ""}` : "未记录代码位置";
}

/**
 * Evidence knowledge graph backed solely by persisted run logs.
 * Every dot is an actual event for the current run.  The canvas grows with
 * the trace instead of collapsing many nodes into overlapping labels.
 */
export function AgentGraph({
  status,
  jobStep,
  jobPct,
  jobStatus,
  live,
  embedded = false,
  traceLogs = [],
  criticSummary,
}: Props) {
  const { t, messages } = useI18n();
  useLiveTick(Boolean(live), 900);
  const [enabled, setEnabled] = useState<Set<Category>>(() => new Set(LANES.map((lane) => lane.id)));
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const events = useMemo(() => {
    const visible = traceLogs.filter((log) => enabled.has(categoryFor(log)));
    return visible.map((log, index): GraphEvent => {
      const category = categoryFor(log);
      return {
        id: log.id || `${log.created_at}-${index}`,
        log,
        category,
        state: stateFor(log),
        label: traceLogTitle(log, t, messages),
        message: eventMessage(log),
        x: 180 + index * 48,
        y: LANE_Y[category],
      };
    });
  }, [enabled, messages, t, traceLogs]);

  const selected = useMemo(
    () => events.find((event) => event.id === selectedId) ?? events.at(-1) ?? null,
    [events, selectedId],
  );
  const width = Math.max(920, 260 + Math.max(events.length - 1, 0) * 48 + 180);
  const failed = events.filter((event) => event.state === "failed").length;
  const active = events.filter((event) => event.state === "active").length;
  const progress = Math.max(0, Math.min(100, jobPct ?? (status === "completed" ? 100 : 0)));

  function toggle(category: Category) {
    setEnabled((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  }

  return (
    <section
      className={`runtime-graph knowledge-graph${embedded ? " runtime-graph--embedded" : ""}${live ? " runtime-graph--live" : ""}${failed ? " runtime-graph--failed" : ""}`}
      data-runtime-graph="true"
      aria-label={t("pipelineGraph.aria")}
    >
      {!embedded && (
        <div className="runtime-graph__header knowledge-graph__header">
          <div className="runtime-graph__intro">
            <span className="runtime-graph__eyebrow">真实运行图谱</span>
            <h3 className="runtime-graph__title">证据与执行事件</h3>
          </div>
          <div className="runtime-graph__meta">
            {live && <span className="runtime-graph__live"><span className="runtime-graph__beacon" aria-hidden />运行中</span>}
            <span className="runtime-graph__pct mono">{progress}%</span>
          </div>
        </div>
      )}

      {!embedded && <div className="runtime-graph__bar" aria-hidden><i style={{ width: `${progress}%` }} /></div>}

      <div className="knowledge-graph__controls" aria-label="图谱筛选">
        {LANES.map((lane) => (
          <button
            key={lane.id}
            type="button"
            className={enabled.has(lane.id) ? "is-active" : ""}
            onClick={() => toggle(lane.id)}
            aria-pressed={enabled.has(lane.id)}
          >
            {lane.label}
          </button>
        ))}
        <span className="knowledge-graph__summary mono">{events.length} events · {active} active · {failed} failed</span>
      </div>

      <div className="runtime-graph__canvas knowledge-graph__canvas">
        {!events.length ? (
          <div className="knowledge-graph__empty">
            当前 Run 尚未写入事件。开始分析后，这里只显示实际发生的 Agent、工具、证据、规则和交付事件。
          </div>
        ) : (
          <svg
            viewBox={`0 0 ${width} 590`}
            width={width}
            height="590"
            style={{ "--knowledge-graph-width": `${width}px` } as React.CSSProperties}
            className="runtime-graph__svg knowledge-graph__svg"
            role="img"
            aria-label="当前运行的全量事件知识图谱"
          >
            <defs>
              <pattern id="runtime-mesh" width="32" height="32" patternUnits="userSpaceOnUse">
                <path d="M 32 0 L 0 0 0 32" className="runtime-graph__mesh-path" fill="none" />
              </pattern>
              <filter id="knowledge-graph-glow" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
            </defs>
            <rect x="16" y="14" width={width - 32} height="562" rx="14" className="runtime-graph__surface" />
            <rect x="32" y="32" width={width - 64} height="526" rx="10" className="runtime-graph__mesh" />
            {LANES.filter((lane) => enabled.has(lane.id)).map((lane) => (
              <g key={lane.id} className={`knowledge-graph__lane knowledge-graph__lane--${lane.id}`}>
                <text x="54" y={LANE_Y[lane.id] - 14} className="runtime-graph__track-label">{lane.label}</text>
                <line x1="150" y1={LANE_Y[lane.id]} x2={width - 54} y2={LANE_Y[lane.id]} className="knowledge-graph__lane-line" />
              </g>
            ))}
            {events.slice(1).map((event, index) => {
              const previous = events[index];
              if (!previous) return null;
              const path = eventPath(previous, event);
              return (
                <g key={`edge-${previous.id}-${event.id}`} className={`knowledge-graph__edge knowledge-graph__edge--${event.state}`}>
                  <path d={path} fill="none" />
                  {event.state === "active" && (
                    <circle r="3.5" className="knowledge-graph__packet">
                      <animateMotion dur="2.2s" repeatCount="indefinite" path={path} />
                    </circle>
                  )}
                </g>
              );
            })}
            {events.map((event, index) => (
              <g
                key={event.id}
                className={`knowledge-graph__event knowledge-graph__event--${event.category} knowledge-graph__event--${event.state}${selected?.id === event.id ? " is-selected" : ""}`}
                transform={`translate(${event.x}, ${event.y})`}
                onClick={() => setSelectedId(event.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(keyboardEvent) => {
                  if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") setSelectedId(event.id);
                }}
              >
                <title>{`${index + 1}. ${event.label} · ${event.message}`}</title>
                <circle r="14" className="knowledge-graph__event-halo" />
                <circle r="8" className="knowledge-graph__event-node" filter={event.state === "active" ? "url(#knowledge-graph-glow)" : undefined} />
                <text y="4" textAnchor="middle" className="knowledge-graph__event-index">{index + 1}</text>
                {event.state === "active" && <circle r="18" className="knowledge-graph__event-pulse" />}
              </g>
            ))}
            <g className="runtime-graph__trace">
              <text x="54" y="542" className="runtime-graph__trace-title">全量事件映射 · 每个节点均来自当前 Run 的持久化日志</text>
            </g>
          </svg>
        )}
      </div>

      <div className="knowledge-graph__inspector" aria-live="polite">
        {selected ? (
          <>
            <span className={`knowledge-graph__state knowledge-graph__state--${selected.state}`}>{selected.category}</span>
            <strong>{selected.label}</strong>
            <p>{selected.message}</p>
            <span className="mono">{codeLocation(selected.log)} · {selected.log.duration_ms ?? 0} ms</span>
          </>
        ) : (
          <span>尚无可查看的运行事件。</span>
        )}
        {criticSummary && <span className="knowledge-graph__critic">审核校验：{criticSummary.validated ?? 0} 已验证 · {criticSummary.flagged ?? 0} 疑点</span>}
        <span className="knowledge-graph__run-state mono">{jobStatus || status}{jobStep ? ` · ${jobStep}` : ""}</span>
      </div>
    </section>
  );
}
