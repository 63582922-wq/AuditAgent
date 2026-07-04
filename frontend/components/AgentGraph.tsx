"use client";

import { useMemo } from "react";
import { buildCombinedNodeStates, buildRuntimeGraph, edgeState } from "@/lib/pipeline-graph";
import { pickPrimaryNodeFromLog } from "@/lib/pipeline-graph-logs";
import type { GraphNodeState, SubAgentNode } from "@/lib/pipeline-graph";
import type { ActivityLog } from "@/components/ActivityTimeline";
import { traceLogTitle } from "@/components/ActivityTimeline";
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
  traceLogs?: ActivityLog[];
  criticSummary?: {
    validated?: number;
    flagged?: number;
    readjudicate_rounds?: number;
  };
};

type RenderNode = {
  id: string;
  label: string;
  short: string;
  kind: string;
  x: number;
  y: number;
  state: GraphNodeState;
  meta?: string;
  branch?: "rules" | "cross";
  labelSide?: "top" | "bottom" | "right";
};

type RenderEdge = {
  from: string;
  to: string;
  state: GraphNodeState;
  lane?: "source" | "parse" | "audit" | "delivery" | "service";
};

type TraceEvent = {
  log: ActivityLog;
  nodeId: string;
  x: number;
  y: number;
  kind: string;
  state: "done" | "active" | "failed";
};

type TrackBand = {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

const STAGE_LABELS: { x: number; label: string }[] = [];

const SERVICE_NODE_DEFS = [
  { id: "svc-dispatch", label: "调度任务", short: "调度", x: 190 },
  { id: "svc-tool", label: "tool 调用", short: "工具", x: 370 },
  { id: "svc-memory", label: "memory 写入", short: "记忆", x: 550 },
  { id: "svc-harness", label: "系统事件", short: "系统", x: 730 },
];

const TRACE_LANES = [
  { id: "agent", label: "Agent", y: 626 },
  { id: "tool", label: "Tool", y: 650 },
  { id: "memory", label: "Memory", y: 674 },
  { id: "system", label: "System", y: 698 },
] as const;

const TRACK_BANDS: TrackBand[] = [
  { id: "ingest", label: "输入识别簇", x: 38, y: 108, width: 278, height: 350 },
  { id: "core", label: "证据知识核心", x: 332, y: 84, width: 246, height: 394 },
  { id: "audit", label: "规则研判簇", x: 596, y: 108, width: 286, height: 350 },
  { id: "service", label: "代码 / 工具 / 记忆事件", x: 58, y: 506, width: 804, height: 58 },
];

function safeClass(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 32) || "event";
}

function logKind(log: ActivityLog) {
  return String(log.detail_json?.kind || log.step || "event");
}

function logName(log: ActivityLog) {
  return String(log.detail_json?.name || log.step || "");
}

function logState(log: ActivityLog): "done" | "active" | "failed" {
  if (log.status === "failed" || log.status === "error") return "failed";
  if (log.status === "running" || log.status === "planned") return "active";
  return "done";
}

function traceLaneIndex(log: ActivityLog) {
  const kind = logKind(log);
  if (kind === "tool") return 1;
  if (kind === "memory") return 2;
  if (kind === "runtime" || kind === "harness") return 3;
  return 0;
}

function serviceNodeFromLog(log: ActivityLog): string | null {
  const kind = logKind(log);
  const name = logName(log);
  if (name === "dispatch_agent_task" || log.step === "dispatch_agent_task") return "svc-dispatch";
  if (kind === "tool") return "svc-tool";
  if (kind === "memory") return "svc-memory";
  if (kind === "runtime" || kind === "harness") return "svc-harness";
  return "svc-harness";
}

function nodeIdFromLog(log: ActivityLog, subAgents: SubAgentNode[]): string | null {
  return pickPrimaryNodeFromLog(log, subAgents) ?? serviceNodeFromLog(log);
}

function eventNodes(
  logs: ActivityLog[],
  nodeMap: Map<string, RenderNode>,
  subAgents: SubAgentNode[],
): TraceEvent[] {
  if (!logs.length) return [];
  const clusters = new Map<string, number>();
  return logs.flatMap((log) => {
    const nodeId = nodeIdFromLog(log, subAgents);
    const node = nodeId ? nodeMap.get(nodeId) : null;
    if (!node || !nodeId) return [];
    const lane = TRACE_LANES[traceLaneIndex(log)];
    const clusterKey = `${nodeId}:${lane.id}`;
    const clusterIndex = clusters.get(clusterKey) ?? 0;
    clusters.set(clusterKey, clusterIndex + 1);
    const offset = ((clusterIndex % 9) - 4) * 7;
    const stack = Math.min(Math.floor(clusterIndex / 9) * 4, 14);
    return {
      log,
      nodeId,
      x: node.x + offset,
      y: lane.y + stack,
      kind: safeClass(logKind(log)),
      state: logState(log),
    };
  });
}

function nodeEventCounts(logs: ActivityLog[], subAgents: SubAgentNode[]) {
  const counts = new Map<string, number>();
  for (const log of logs) {
    const nodeId = nodeIdFromLog(log, subAgents);
    if (!nodeId) continue;
    counts.set(nodeId, (counts.get(nodeId) ?? 0) + 1);
  }
  return counts;
}

function truncate(value: string, max = 14) {
  return value.length > max ? `${value.slice(0, max - 1)}...` : value;
}

function serviceState(logs: ActivityLog[], serviceId: string): GraphNodeState {
  const matches = logs.filter((log) => {
    const kind = logKind(log);
    const name = logName(log);
    if (serviceId === "svc-dispatch")
      return name === "dispatch_agent_task" || log.step === "dispatch_agent_task";
    if (serviceId === "svc-tool") return kind === "tool";
    if (serviceId === "svc-memory") return kind === "memory";
    return serviceNodeFromLog(log) === "svc-harness";
  });

  if (!matches.length) return "pending";
  if (matches.some((log) => logState(log) === "failed")) return "failed";
  if (matches.some((log) => logState(log) === "active")) return "active";
  return "done";
}

function virtualGateState(
  criticState: GraphNodeState,
  deliverState: GraphNodeState,
): GraphNodeState {
  if (criticState === "failed" || deliverState === "failed") return "failed";
  if (deliverState === "done") return "done";
  if (deliverState === "active" || criticState === "done" || criticState === "active")
    return "active";
  return "pending";
}

function arrangeSubAgents(subNodes: RenderNode[]) {
  const rules = subNodes.filter((node) => node.branch === "rules");
  const cross = subNodes.filter((node) => node.branch === "cross");

  const assign = (nodes: RenderNode[], startY: number) =>
    nodes.map((node, index) => {
      const col = Math.floor(index / 3);
      const row = index % 3;
      return {
        ...node,
        x: 650 + col * 98,
        y: startY + row * 48,
        labelSide: "right" as const,
      };
    });

  return [...assign(rules, 126), ...assign(cross, 414)];
}

function curvePath(a: RenderNode, b: RenderNode) {
  const aSize = stationSize(a);
  const bSize = stationSize(b);
  const direction = b.x >= a.x ? 1 : -1;
  const startX = a.x + direction * (aSize.w / 2 - 2);
  const endX = b.x - direction * (bSize.w / 2 - 2);
  if (Math.abs(a.y - b.y) < 6) return `M ${startX} ${a.y} L ${endX} ${b.y}`;
  const bend = Math.min(Math.abs(endX - startX) * 0.5, 76);
  return `M ${startX} ${a.y} C ${startX + direction * bend} ${a.y}, ${endX - direction * bend} ${b.y}, ${endX} ${b.y}`;
}

function stationSize(node: RenderNode) {
  if (node.id.startsWith("svc-")) return { w: 124, h: 40 };
  if (node.id.startsWith("sub-")) return { w: 122, h: 42 };
  if (node.kind === "pool") return { w: 126, h: 56 };
  if (node.kind === "gate") return { w: 130, h: 46 };
  if (node.id === "excel" || node.id === "zip") return { w: 120, h: 42 };
  return { w: 118, h: 46 };
}

function statusText(state: GraphNodeState) {
  switch (state) {
    case "done":
      return "已完成";
    case "active":
      return "运行中";
    case "failed":
      return "异常";
    default:
      return "待执行";
  }
}

export function AgentGraph({
  status,
  jobStep,
  jobPct,
  jobStatus,
  live,
  embedded = false,
  subAgents,
  traceLogs = [],
  criticSummary,
}: Props) {
  const { t, messages } = useI18n();
  useLiveTick(Boolean(live), 900);
  const pipelineNodes = useMemo(() => localizedPipelineNodes(messages), [messages]);
  const criticName = messages.domain.criticAgent;

  const criticDone = Boolean(
    criticSummary && (criticSummary.validated ?? 0) > 0 && (criticSummary.flagged ?? 0) === 0,
  );

  const graph = useMemo(
    () =>
      buildRuntimeGraph({
        status,
        jobStep,
        jobPct,
        jobStatus,
        subAgents,
        traceLogs,
        criticDone: criticDone || Boolean(criticSummary?.validated),
        criticActive:
          status === "generating_report" ||
          status === "adjudicating" ||
          (status === "completed" && (criticSummary?.flagged ?? 0) > 0),
      }),
    [status, jobStep, jobPct, jobStatus, subAgents, traceLogs, criticDone, criticSummary],
  );

  const {
    nodeStates,
    subNodes,
    subEdges,
    pipelineEdges,
    progress,
    failed,
    activeStep,
    activeNodeId,
    logSignals,
  } = graph;

  const allStates = useMemo(
    () => buildCombinedNodeStates(nodeStates, subNodes),
    [nodeStates, subNodes],
  );

  const localizedNodes = useMemo(
    () =>
      new Map(
        pipelineNodes.map((node) => [
          node.id,
          {
            ...node,
            label: node.id === "critic" ? criticName : node.label,
            state: nodeStates.get(node.id) ?? "pending",
          },
        ]),
      ),
    [pipelineNodes, nodeStates, criticName],
  );

  const nodes: RenderNode[] = useMemo(() => {
    const getNode = (id: string, overrides: Partial<RenderNode> = {}): RenderNode => {
      const base = localizedNodes.get(id);
      return {
        id,
        label: base?.label ?? id,
        short: base?.short ?? id.slice(0, 2),
        kind: base?.kind ?? "stage",
        x: base?.x ?? 0,
        y: base?.y ?? 0,
        state: (base?.state ?? "pending") as GraphNodeState,
        ...overrides,
      };
    };

    const visionState = nodeStates.get("vision") ?? "pending";
    const criticState = nodeStates.get("critic") ?? "pending";
    const deliverState = nodeStates.get("deliver") ?? "pending";
    const templateState = virtualGateState(criticState, deliverState);

    const baseNodes: RenderNode[] = [
      getNode("upload", { x: 106, y: 318, meta: "资料入库" }),
      getNode("main", { x: 228, y: 318, meta: "拆解/调度" }),
      getNode("vision", { x: 338, y: 170, meta: "图片/PDF图像页", labelSide: "top" }),
      {
        id: "handwriting",
        label: "手写增强",
        short: "手写",
        kind: "vision",
        x: 386,
        y: 238,
        state: visionState,
        meta: "扫描/手写页",
        labelSide: "top",
      },
      getNode("textIngest", { x: 342, y: 452, meta: "PDF文本层/Excel" }),
      getNode("parsedPool", { x: 458, y: 318, meta: "结构化资料池" }),
      getNode("rules", { x: 572, y: 172, meta: "143列规则", labelSide: "top" }),
      getNode("cross", { x: 572, y: 452, meta: "证据勾稽" }),
      getNode("adjudicate", { x: 700, y: 318, meta: "Finding" }),
      getNode("critic", { x: 812, y: 318, meta: "复核 Agent", label: "审核校验" }),
      {
        id: "templateGate",
        label: "固定模板143列",
        short: "143",
        kind: "gate",
        x: 808,
        y: 190,
        state: templateState,
        meta: "字段质检",
        labelSide: "bottom",
      },
      getNode("deliver", { x: 808, y: 452, meta: "交付编排", label: "交付编排" }),
      {
        id: "excel",
        label: "Excel主交付",
        short: "Excel",
        kind: "stage",
        x: 852,
        y: 238,
        state: deliverState,
        meta: "固定模板",
      },
      {
        id: "zip",
        label: "ZIP归档",
        short: "ZIP",
        kind: "stage",
        x: 852,
        y: 402,
        state: deliverState,
        meta: "全量附件",
      },
    ];

    const arrangedSubNodes = arrangeSubAgents(
      subNodes.map((node) => ({
        ...node,
        label: node.label,
        short: node.short,
        meta: node.branch === "rules" ? "规则专员" : "比对专员",
      })),
    );

    const serviceNodes: RenderNode[] = SERVICE_NODE_DEFS.map((node) => ({
      ...node,
      y: 536,
      kind: "service",
      meta: node.id === "svc-dispatch" ? "分发子任务" : "运行事件",
      state: serviceState(traceLogs, node.id),
      labelSide: "bottom",
    }));

    return [...baseNodes, ...arrangedSubNodes, ...serviceNodes];
  }, [localizedNodes, nodeStates, subNodes, traceLogs, criticName]);

  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);

  const visualStates = useMemo(() => {
    const states = new Map(allStates);
    for (const node of nodes) states.set(node.id, node.state);
    return states;
  }, [allStates, nodes]);

  const edges: RenderEdge[] = useMemo(() => {
    const edge = (from: string, to: string, lane?: RenderEdge["lane"]): RenderEdge => ({
      from,
      to,
      lane,
      state: edgeState(from, to, visualStates),
    });

    const subEdgesByBranch = subEdges.map((e) => edge(e.from, e.to, "audit"));
    const hasRulesSubAgents = subNodes.some((node) => node.branch === "rules");
    const hasCrossSubAgents = subNodes.some((node) => node.branch === "cross");
    const baseEdges = pipelineEdges
      .filter(
        (e) =>
          e.to !== "deliver" &&
          e.from !== "critic" &&
          !(e.from === "vision" && e.to === "parsedPool") &&
          !(e.from === "rules" && e.to === "adjudicate") &&
          !(e.from === "cross" && e.to === "adjudicate"),
      )
      .map((e) =>
        edge(
          e.from,
          e.to,
          e.from === "parsedPool" || e.from === "rules" || e.from === "cross" ? "audit" : "source",
        ),
      );

    return [
      ...baseEdges.filter((e) => e.from !== "main" || e.to !== "vision"),
      edge("main", "vision", "parse"),
      edge("vision", "handwriting", "parse"),
      edge("handwriting", "parsedPool", "parse"),
      ...subEdgesByBranch,
      ...(hasRulesSubAgents ? [] : [edge("rules", "adjudicate", "audit")]),
      ...(hasCrossSubAgents ? [] : [edge("cross", "adjudicate", "audit")]),
      edge("critic", "templateGate", "delivery"),
      edge("templateGate", "deliver", "delivery"),
      edge("deliver", "excel", "delivery"),
      edge("deliver", "zip", "delivery"),
      edge("svc-dispatch", "svc-tool", "service"),
      edge("svc-tool", "svc-memory", "service"),
      edge("svc-memory", "svc-harness", "service"),
    ];
  }, [pipelineEdges, subEdges, subNodes, visualStates, nodeMap]);

  const activeNode = activeNodeId ? nodeMap.get(activeNodeId) : null;
  const coreNode = nodeMap.get("parsedPool");
  const graphSubAgents = subAgents ?? [];
  const eventCounts = useMemo(
    () => nodeEventCounts(traceLogs, graphSubAgents),
    [traceLogs, graphSubAgents],
  );
const events = useMemo(
    () => eventNodes(traceLogs, nodeMap, graphSubAgents),
    [traceLogs, nodeMap, graphSubAgents],
  );
  const unmappedEventCount = Math.max(traceLogs.length - events.length, 0);
  const doneCount = nodes.filter((node) => node.state === "done").length;
  const activeCount = nodes.filter((node) => node.state === "active").length;
  const issueCount =
    nodes.filter((node) => node.state === "failed").length + (criticSummary?.flagged ?? 0);

  return (
    <section
      className={`runtime-graph${embedded ? " runtime-graph--embedded" : ""}${live ? " runtime-graph--live" : ""}${failed ? " runtime-graph--failed" : ""}`}
      data-runtime-graph="true"
      aria-label={t("pipelineGraph.aria")}
    >
      {!embedded && (
        <>
          <div className="runtime-graph__header">
            <div className="runtime-graph__intro">
              <span className="runtime-graph__eyebrow">{t("pipelineGraph.eyebrow")}</span>
              <h3 className="runtime-graph__title">{t("pipelineGraph.title")}</h3>
            </div>
            <div className="runtime-graph__meta">
              {live && (
                <span className="runtime-graph__live">
                  <span className="runtime-graph__beacon" aria-hidden />
                  {t("hud.liveRun")}
                </span>
              )}
              <span className="runtime-graph__pct mono">{progress}%</span>
            </div>
          </div>

          <div className="runtime-graph__bar" aria-hidden>
            <i style={{ width: `${progress}%` }} />
          </div>
        </>
      )}

      <div className="runtime-graph__canvas">
        <svg
          viewBox="0 0 920 720"
          preserveAspectRatio="xMidYMid meet"
          className="runtime-graph__svg"
          role="img"
          aria-hidden={false}
        >
          <defs>
            <linearGradient id="runtime-flow-done" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" className="runtime-graph__grad-done-a" />
              <stop offset="100%" className="runtime-graph__grad-done-b" />
            </linearGradient>
            <linearGradient id="runtime-flow-active" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" className="runtime-graph__grad-active-a" />
              <stop offset="50%" className="runtime-graph__grad-active-b" />
              <stop offset="100%" className="runtime-graph__grad-active-c" />
            </linearGradient>
            <filter id="runtime-soft-glow" x="-45%" y="-45%" width="190%" height="190%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <pattern id="runtime-mesh" width="34" height="34" patternUnits="userSpaceOnUse">
              <path d="M 34 0 L 0 0 0 34" className="runtime-graph__mesh-path" fill="none" />
            </pattern>
          </defs>

          <rect
            x="16"
            y="18"
            width="888"
            height="684"
            rx="22"
            className="runtime-graph__surface"
          />
          <rect x="30" y="38" width="860" height="536" rx="18" className="runtime-graph__mesh" />

          {TRACK_BANDS.map((track) => (
            <g key={track.id} className={`runtime-graph__track runtime-graph__track--${track.id}`}>
              <rect
                x={track.x}
                y={track.y}
                width={track.width}
                height={track.height}
                rx="16"
                className="runtime-graph__track-band"
              />
              <text x={track.x + 16} y={track.y + 28} className="runtime-graph__track-label">
                {track.label}
              </text>
            </g>
          ))}

          {STAGE_LABELS.map((stage) => (
            <g key={stage.label} className="runtime-graph__stage">
              <line
                x1={stage.x}
                y1="72"
                x2={stage.x}
                y2="586"
                className="runtime-graph__stage-line"
              />
              <text x={stage.x + 10} y="60" className="runtime-graph__stage-label">
                {stage.label}
              </text>
            </g>
          ))}

          {coreNode && (
            <g
              className="runtime-graph__core-field"
              transform={`translate(${coreNode.x}, ${coreNode.y})`}
            >
              <circle
                r="132"
                className="runtime-graph__core-ring runtime-graph__core-ring--outer"
              />
              <circle
                r="92"
                className="runtime-graph__core-ring runtime-graph__core-ring--inner"
              />
              {live && <circle r="116" className="runtime-graph__core-scan" />}
              <text y="-114" textAnchor="middle" className="runtime-graph__core-caption">
                Evidence Pool
              </text>
            </g>
          )}

          {edges.map((edge) => {
            const from = nodeMap.get(edge.from);
            const to = nodeMap.get(edge.to);
            if (!from || !to) return null;
            const pathD = curvePath(from, to);
            return (
              <g
                key={`${edge.from}-${edge.to}`}
                className={`runtime-graph__rail runtime-graph__rail--${edge.state} runtime-graph__rail--${edge.lane ?? "source"}`}
              >
                <path d={pathD} className="runtime-graph__rail-path" fill="none" />
                {(edge.state === "active" || edge.state === "done") && (
                  <circle
                    r={edge.state === "active" ? "4.5" : "3"}
                    className={`runtime-graph__rail-packet runtime-graph__rail-packet--${edge.state}`}
                  >
                    <animateMotion
                      dur={edge.state === "active" ? "2.6s" : "7.5s"}
                      repeatCount="indefinite"
                      path={pathD}
                    />
                    <animate
                      attributeName="opacity"
                      values={edge.state === "active" ? "0;1;0.75;0" : "0;0.44;0.2;0"}
                      dur={edge.state === "active" ? "2.6s" : "7.5s"}
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
              </g>
            );
          })}

          {events.map((event, index) => {
            const node = nodeMap.get(event.nodeId);
            if (!node) return null;
            return (
              <line
                key={`event-link-${event.log.id || index}`}
                x1={event.x}
                y1={event.y - 12}
                x2={node.x}
                y2={node.y}
                className={`runtime-graph__event-link runtime-graph__event-link--${event.state}`}
              />
            );
          })}

          {nodes.map((node) => {
            const count = eventCounts.get(node.id) ?? 0;
            const nodeRadius = node.kind === "pool" ? 26 : node.id.startsWith("svc-") ? 15 : 21;
            const labelSide = node.labelSide ?? "right";
            const labelX = labelSide === "right" ? nodeRadius + 12 : labelSide === "top" || labelSide === "bottom" ? 0 : -nodeRadius - 12;
            const labelY = labelSide === "top" ? -nodeRadius - 26 : labelSide === "bottom" ? nodeRadius + 18 : -8;
            const labelAnchor = labelSide === "right" ? "start" : labelSide === "top" || labelSide === "bottom" ? "middle" : "end";
            const chipX = labelAnchor === "middle" ? -52 : labelAnchor === "end" ? -104 : -8;
            const chipY = labelY - 15;
            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                className={`runtime-graph__station runtime-graph__station--${node.state} runtime-graph__station--${node.kind}`}
                data-node-id={node.id}
                data-node-state={node.state}
              >
                <title>{`${node.label} · ${statusText(node.state)}${node.meta ? ` · ${node.meta}` : ""}`}</title>
                <circle
                  r={nodeRadius + 14}
                  className="runtime-graph__station-glow"
                />
                <circle
                  r={nodeRadius}
                  className="runtime-graph__station-card"
                />
                <circle r={nodeRadius - 5} className="runtime-graph__station-orb" />
                <circle r={Math.max(nodeRadius - 13, 5)} className="runtime-graph__station-core" />
                <text
                  y="3"
                  textAnchor="middle"
                  className="runtime-graph__station-short"
                >
                  {truncate(node.short, 4)}
                </text>
                <rect
                  x={chipX}
                  y={chipY}
                  width="112"
                  height={node.meta ? "36" : "22"}
                  rx="12"
                  className="runtime-graph__station-label-chip"
                />
                <text
                  x={labelX}
                  y={labelY}
                  textAnchor={labelAnchor}
                  className="runtime-graph__station-label"
                >
                  {truncate(node.label, node.id.startsWith("sub-") ? 9 : 12)}
                </text>
                {node.meta && (
                  <text
                    x={labelX}
                    y={labelY + 15}
                    textAnchor={labelAnchor}
                    className="runtime-graph__station-meta"
                  >
                    {truncate(node.meta, node.id.startsWith("sub-") ? 9 : 10)}
                  </text>
                )}
                {count > 0 && (
                  <g
                    className="runtime-graph__station-badge"
                    transform={`translate(${nodeRadius + 12}, ${-nodeRadius - 8})`}
                  >
                    <rect x="-16" y="-9" width="32" height="18" rx="9" />
                    <text y="4" textAnchor="middle">
                      {count > 99 ? "99+" : count}
                    </text>
                  </g>
                )}
                {node.state === "active" && (
                  <circle r={nodeRadius + 10} className="runtime-graph__station-pulse" />
                )}
              </g>
            );
          })}

          <g className="runtime-graph__inspector" transform="translate(50 42)">
            <rect width="250" height="78" rx="14" className="runtime-graph__inspector-box" />
            <text x="18" y="28" className="runtime-graph__inspector-kicker">
              当前断点
            </text>
            <text x="18" y="55" className="runtime-graph__inspector-title">
              {activeNode ? truncate(activeNode.label, 13) : "待命"}
            </text>
            <text x="18" y="76" className="runtime-graph__inspector-body">
              {activeNode
                ? truncate(`${statusText(activeNode.state)} · ${activeNode.meta ?? localizedMainAgentPhase(activeStep, messages)}`, 16)
                : truncate(localizedMainAgentPhase(activeStep, messages), 20)}
            </text>
            <text x="162" y="28" className="runtime-graph__inspector-stat">
              节点 {doneCount}/{nodes.length}
            </text>
            <text x="162" y="52" className="runtime-graph__inspector-stat">
              活动 {activeCount}
            </text>
            <text
              x="162"
              y="76"
              className="runtime-graph__inspector-stat runtime-graph__inspector-stat--risk"
            >
              风险 {issueCount}
            </text>
          </g>

          <g className="runtime-graph__trace">
            <rect
              x="36"
              y="594"
              width="848"
              height="112"
              rx="16"
              className="runtime-graph__trace-box"
            />
            <text x="54" y="616" className="runtime-graph__trace-title">
              全量事件映射 · {events.length}/{traceLogs.length} events · 映射到 {eventCounts.size} 个节点
              {unmappedEventCount > 0 ? ` · 未映射 ${unmappedEventCount}` : ""}
            </text>
            {TRACE_LANES.map((lane) => (
              <g key={lane.id}>
                <text x="54" y={lane.y + 4} className="runtime-graph__trace-lane-label">
                  {lane.label}
                </text>
                <line
                  x1="110"
                  y1={lane.y}
                  x2="858"
                  y2={lane.y}
                  className="runtime-graph__trace-lane"
                />
              </g>
            ))}
            {events.map((event, index) => {
              const title = traceLogTitle(event.log, t, messages);
              const detail = event.log.detail_json || {};
              const message = typeof detail.message === "string" ? detail.message : "";
              const node = nodeMap.get(event.nodeId);
              return (
                <g
                  key={event.log.id || `${event.log.step}-${index}`}
                  transform={`translate(${event.x}, ${event.y})`}
                  className={`runtime-graph__trace-event runtime-graph__trace-event--${event.state} runtime-graph__trace-event--${event.kind}`}
                  data-event-log-id={event.log.id}
                  data-event-kind={logKind(event.log)}
                  data-event-state={event.state}
                >
                  <title>{`${node?.label ?? event.nodeId} · ${message ? `${title} - ${message}` : title}`}</title>
                  <line y1="-10" y2="10" className="runtime-graph__trace-tick" />
                  {event.state === "active" && (
                    <circle r="8" className="runtime-graph__trace-pulse" />
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      <div className="runtime-graph__foot">
        <p className="runtime-graph__footnote">
          {(() => {
            const syncLog = logSignals.footnoteLog;
            if (live && syncLog) {
              const title = traceLogTitle(syncLog, t, messages);
              const detail = syncLog.detail_json || {};
              const message = typeof detail.message === "string" ? detail.message : "";
              return message ? `${title} - ${message}` : title;
            }
            if (criticSummary && (criticSummary.validated ?? 0) > 0) {
              return `${t("pipelineGraph.criticValidated", { name: criticName, count: criticSummary.validated ?? 0 })}${
                (criticSummary.flagged ?? 0) > 0
                  ? t("pipelineGraph.criticFlagged", { flagged: criticSummary.flagged ?? 0 })
                  : t("pipelineGraph.criticPassed")
              }`;
            }
            return localizedMainAgentPhase(activeStep, messages);
          })()}
        </p>
        <span className="runtime-graph__active-node">
          {activeNode ? `${activeNode.short} · ${truncate(activeNode.label, 12)}` : "待命"}
        </span>
      </div>
    </section>
  );
}
