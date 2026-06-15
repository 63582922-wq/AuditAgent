"use client";

import { useMemo } from "react";
import {
  SubAgentNode,
  buildCombinedNodeStates,
  buildRuntimeGraph,
  edgeState,
} from "@/lib/pipeline-graph";
import { useI18n } from "@/lib/i18n";
import { localizedMainAgentPhase, localizedPipelineNodes } from "@/lib/i18n/pipeline-i18n";
import { useLiveTick } from "@/lib/useLiveTick";

type Props = {
  status: string;
  jobStep?: string;
  jobPct?: number;
  jobStatus?: string;
  live?: boolean;
  /** 嵌入 run-stage / Block 时隐藏重复标题与进度条，无独立卡片框 */
  embedded?: boolean;
  subAgents?: SubAgentNode[];
  criticSummary?: {
    validated?: number;
    flagged?: number;
    readjudicate_rounds?: number;
  };
};

function curvePath(x1: number, y1: number, x2: number, y2: number) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  if (Math.abs(dy) < 8) {
    return `M ${x1} ${y1} L ${x2} ${y2}`;
  }
  if (Math.abs(dx) < 8) {
    const midY = (y1 + y2) / 2;
    return `M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}`;
  }
  const bend = Math.min(Math.abs(dx) * 0.42, 56);
  const cx1 = x1 + Math.sign(dx) * bend;
  const cx2 = x2 - Math.sign(dx) * bend;
  return `M ${x1} ${y1} C ${cx1} ${y1}, ${cx2} ${y2}, ${x2} ${y2}`;
}

/** 节点半径（SVG 用户单位） */
function nodeRadius(kind: string) {
  if (kind === "agent") return 24;
  if (kind === "pool") return 22;
  return 20;
}

function labelOffset(r: number) {
  return r + 26;
}

export function AgentGraph({
  status,
  jobStep,
  jobPct,
  jobStatus,
  live,
  embedded = false,
  subAgents,
  criticSummary,
}: Props) {
  const { t, messages } = useI18n();
  useLiveTick(Boolean(live), 900);
  const pipelineNodes = useMemo(() => localizedPipelineNodes(messages), [messages]);
  const criticName = messages.domain.criticAgent;

  const criticDone = Boolean(
    criticSummary && (criticSummary.validated ?? 0) > 0 && (criticSummary.flagged ?? 0) === 0
  );

  const graph = useMemo(
    () =>
      buildRuntimeGraph({
        status,
        jobStep,
        jobPct,
        jobStatus,
        subAgents,
        criticDone: criticDone || Boolean(criticSummary?.validated),
        criticActive:
          status === "generating_report" ||
          status === "adjudicating" ||
          (status === "completed" && (criticSummary?.flagged ?? 0) > 0),
      }),
    [status, jobStep, jobPct, jobStatus, subAgents, criticDone, criticSummary]
  );

  const { nodeStates, subNodes, subEdges, pipelineEdges, progress, failed, activeStep } = graph;

  const allStates = useMemo(
    () => buildCombinedNodeStates(nodeStates, subNodes),
    [nodeStates, subNodes]
  );

  const nodes = [
    ...pipelineNodes.map((n) => ({
      ...n,
      label: n.id === "critic" ? criticName : n.label,
      state: nodeStates.get(n.id) ?? "pending",
    })),
    ...subNodes,
  ];

  const edges = [
    ...pipelineEdges.map((e) => ({
      ...e,
      state: edgeState(e.from, e.to, allStates),
    })),
    ...subEdges.map((e) => ({
      ...e,
      state: edgeState(e.from, e.to, allStates),
    })),
  ];

  const pos = (id: string) => {
    const n = nodes.find((x) => x.id === id);
    return n ? { x: n.x, y: n.y } : { x: 0, y: 0 };
  };

  return (
    <section
      className={`settling-graph${embedded ? " settling-graph--embedded" : ""}${live ? " settling-graph--live" : ""}${failed ? " settling-graph--failed" : ""}`}
      aria-label={t("pipelineGraph.aria")}
    >
      {!embedded && (
        <>
          <div className="settling-graph__header">
            <div className="settling-graph__intro">
              <span className="settling-graph__eyebrow">{t("pipelineGraph.eyebrow")}</span>
              <h3 className="settling-graph__title">{t("pipelineGraph.title")}</h3>
            </div>
            <div className="settling-graph__meta">
              {live && (
                <span className="settling-graph__live">
                  <span className="settling-graph__beacon" aria-hidden />
                  {t("hud.liveRun")}
                </span>
              )}
              <span className="settling-graph__pct mono">{progress}%</span>
            </div>
          </div>

          <div className="settling-graph__bar" aria-hidden>
            <i style={{ width: `${progress}%` }} />
          </div>
        </>
      )}

      <div className="settling-graph__canvas">
        <svg
          viewBox="0 0 980 440"
          preserveAspectRatio="xMidYMid meet"
          className="settling-graph__svg"
          role="img"
          aria-hidden={false}
        >
          <defs>
            <radialGradient id="settle-node-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" className="settling-graph__grad-glow-inner" />
              <stop offset="100%" className="settling-graph__grad-glow-outer" />
            </radialGradient>
            <linearGradient id="settle-edge-warm" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" className="settling-graph__grad-edge-a" />
              <stop offset="50%" className="settling-graph__grad-edge-b" />
              <stop offset="100%" className="settling-graph__grad-edge-c" />
            </linearGradient>
          </defs>

          {/* 沉降层线 · 替代机械网格 */}
          {[88, 220, 352].map((y, i) => (
            <line
              key={y}
              x1={32}
              y1={y}
              x2={948}
              y2={y}
              className={`settling-graph__stratum settling-graph__stratum--${i}`}
            />
          ))}

          {edges.map((e) => {
            const a = pos(e.from);
            const b = pos(e.to);
            const pathD = curvePath(a.x, a.y, b.x, b.y);
            return (
              <g key={`${e.from}-${e.to}`}>
                <path
                  d={pathD}
                  className={`settling-graph__edge settling-graph__edge--${e.state}`}
                  fill="none"
                />
                {live && e.state === "active" && (
                  <>
                    <circle r="2.2" className="settling-graph__grain settling-graph__grain--a">
                      <animateMotion dur="4.8s" repeatCount="indefinite" path={pathD} calcMode="spline" keyTimes="0;1" keySplines="0.42 0 0.2 1" />
                      <animate attributeName="opacity" values="0;0.85;0.45;0" dur="4.8s" repeatCount="indefinite" />
                    </circle>
                    <circle r="1.2" className="settling-graph__grain settling-graph__grain--b">
                      <animateMotion dur="6.2s" repeatCount="indefinite" path={pathD} calcMode="spline" keyTimes="0;1" keySplines="0.55 0 0.25 1" begin="1.4s" />
                      <animate attributeName="opacity" values="0;0.55;0.3;0" dur="6.2s" repeatCount="indefinite" begin="1.4s" />
                    </circle>
                  </>
                )}
              </g>
            );
          })}

          {nodes.map((n) => {
            const r = nodeRadius(n.kind);
            const isActive = n.state === "active";
            return (
              <g key={n.id} transform={`translate(${n.x}, ${n.y})`}>
                {live && isActive && (
                  <>
                    <circle r={42} className="settling-graph__halo settling-graph__halo--a" />
                    <circle r={42} className="settling-graph__halo settling-graph__halo--b" />
                  </>
                )}
                {isActive && <circle r={32} fill="url(#settle-node-glow)" className="settling-graph__glow-fill" />}
                <g className={`settling-graph__node settling-graph__node--${n.state} settling-graph__node--${n.kind}`}>
                  <circle r={r} className="settling-graph__node-ring" />
                  {isActive && (
                    <circle r={3} className="settling-graph__node-core">
                      <animate attributeName="r" values="2.4;3.6;2.4" dur="3.6s" repeatCount="indefinite" />
                      <animate attributeName="opacity" values="0.45;0.95;0.45" dur="3.6s" repeatCount="indefinite" />
                    </circle>
                  )}
                  <text className="settling-graph__node-short" textAnchor="middle" dy="0.35em">
                    {n.short}
                  </text>
                  <text className="settling-graph__node-label" textAnchor="middle" dy={labelOffset(r)}>
                    {n.label.length > 16 ? `${n.label.slice(0, 15)}…` : n.label}
                  </text>
                </g>
              </g>
            );
          })}
        </svg>
        {live && <div className="settling-graph__ambient settling-graph__ambient--live" aria-hidden />}
        {!live && <div className="settling-graph__ambient settling-graph__ambient--idle" aria-hidden />}
      </div>

      <p className="settling-graph__footnote">
        {criticSummary && (criticSummary.validated ?? 0) > 0
          ? `${t("pipelineGraph.criticValidated", { name: criticName, count: criticSummary.validated ?? 0 })}${
              (criticSummary.flagged ?? 0) > 0
                ? t("pipelineGraph.criticFlagged", { flagged: criticSummary.flagged ?? 0 })
                : t("pipelineGraph.criticPassed")
            }`
          : localizedMainAgentPhase(activeStep, messages)}
      </p>
    </section>
  );
}
