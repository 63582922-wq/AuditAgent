"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { AgentBriefsPanel } from "@/components/AgentBriefsPanel";
import { PageSkeleton } from "@/components/PageSkeleton";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import { fetchProjectOverview, ProjectOverview, ProjectSummary, api } from "@/lib/api";
import { STATUS_LABEL, overallProgress } from "@/lib/workflow";

const RiskChart = dynamic(() => import("@/components/RiskChart").then((m) => ({ default: m.RiskChart })), {
  loading: () => <div className="page-skeleton__block" style={{ height: 160 }} />,
});

const ActivityTimeline = dynamic(
  () => import("@/components/ActivityTimeline").then((m) => ({ default: m.ActivityTimeline })),
  { loading: () => <div className="page-skeleton__block" style={{ height: 200 }} /> }
);

type Log = {
  id: string;
  step: string;
  status: string;
  detail_json?: Record<string, unknown>;
  duration_ms?: number;
  created_at: string;
};

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { live, job: liveJob } = useProjectLive();
  const [overview, setOverview] = useState<ProjectOverview | null>(null);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [logs, setLogs] = useState<Log[]>([]);
  const [logsReady, setLogsReady] = useState(false);

  useEffect(() => {
    fetchProjectOverview(id).then(setOverview).catch(console.error);
    api<ProjectSummary>(`/projects/${id}/summary`)
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [id]);

  useEffect(() => {
    setLogsReady(false);
    api<Log[]>(`/projects/${id}/logs`)
      .then(setLogs)
      .catch(console.error)
      .finally(() => setLogsReady(true));
  }, [id]);

  const shell = live ?? overview;
  if (!shell) return <PageSkeleton lines={4} />;

  const activeJob = liveJob;
  const pct = overallProgress(shell.status, activeJob?.current_step, activeJob?.progress_pct, activeJob?.status);
  const files = overview?.files ?? [];
  const riskPreview = overview?.risk_preview ?? [];
  const fileCount = overview?.file_count ?? live?.file_count ?? files.length;
  const riskCount = overview?.risk_count ?? live?.risk_count ?? riskPreview.length;
  const outputCount = overview?.output_count ?? live?.output_count ?? 0;

  const agentPlan = shell.state_json?.agent_plan as
    | { agent_mode?: string; reasoning?: string; priority_actions?: string[] }
    | undefined;

  return (
    <>
      <PageTop
        title={shell.name}
        desc={`${STATUS_LABEL[shell.status] || shell.status}${shell.summary ? ` · ${shell.summary}` : ""} · 进度 ${pct}%`}
        action={
          <Link href={`/projects/${id}/files`} className="btn">
            {fileCount === 0 ? "上传资料" : "管理资料"}
          </Link>
        }
      />

      <div className="quick-links">
        <Link href={`/projects/${id}/files`} className="quick-link">
          <span className="quick-link__icon">↑</span>
          <span className="quick-link__label">资料</span>
          <span className="quick-link__val">{fileCount}</span>
        </Link>
        <Link href={`/projects/${id}/risks`} className="quick-link">
          <span className="quick-link__icon">⚠</span>
          <span className="quick-link__label">风险</span>
          <span className="quick-link__val">{riskCount}</span>
        </Link>
        <Link href={`/projects/${id}/outputs`} className="quick-link">
          <span className="quick-link__icon">⬇</span>
          <span className="quick-link__label">交付验收</span>
          <span className="quick-link__val">
            {shell.status === "accepted"
              ? "OK"
              : outputCount > 0
                ? String(outputCount)
                : shell.status === "completed"
                  ? "!"
                  : "—"}
          </span>
        </Link>
        <Link href={`/projects/${id}/logs`} className="quick-link">
          <span className="quick-link__icon">≡</span>
          <span className="quick-link__label">日志</span>
          <span className="quick-link__val">{logsReady ? logs.length : "…"}</span>
        </Link>
      </div>

      {summary && summary.total_risks > 0 && (
        <Block title="风险分布">
          <RiskChart high={summary.high} medium={summary.medium} low={summary.low} total={summary.total_risks} />
        </Block>
      )}

      {agentPlan && (
        <Block title="Agent 计划" hint={agentPlan.agent_mode}>
          <p style={{ fontSize: "0.875rem", color: "var(--text-2)", lineHeight: 1.65, margin: "0 0 1rem" }}>
            {agentPlan.reasoning}
          </p>
          <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.8125rem", color: "var(--text-2)" }}>
            {(agentPlan.priority_actions || []).map((a: string) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Block>
      )}

      <AgentBriefsPanel state={shell.state_json} />

      <div className="grid-2">
        <Block title={`文件 · ${fileCount}`}>
          {files.length === 0 ? (
            <div>
              <p className="muted" style={{ marginBottom: "1rem" }}>
                尚未上传 · 请先导入财务原始文件
              </p>
              <Link href={`/projects/${id}/files`} className="btn-outline">
                前往上传
              </Link>
            </div>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: "none", fontSize: "0.8125rem" }}>
              {files.map((f) => (
                <li key={f.id} style={{ padding: "0.4rem 0", borderBottom: "1px solid var(--line)" }}>
                  {f.file_name}
                  <span className="muted"> · {f.document_category}</span>
                </li>
              ))}
            </ul>
          )}
        </Block>

        <Block title={`风险 · ${riskCount}`}>
          {riskPreview.length === 0 ? (
            <div>
              <p className="muted" style={{ marginBottom: "1rem" }}>
                分析完成后自动生成
              </p>
              {fileCount > 0 && shell.status === "uploaded" && (
                <Link href={`/projects/${id}/files`} className="btn-outline">
                  启动分析
                </Link>
              )}
            </div>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: "none", fontSize: "0.8125rem" }}>
              {riskPreview.map((r) => (
                <li
                  key={r.id}
                  style={{ padding: "0.4rem 0", borderBottom: "1px solid var(--line)", display: "flex", gap: "0.5rem" }}
                >
                  <span className={`badge ${r.risk_level === "高" ? "high" : r.risk_level === "中" ? "mid" : "low"}`}>
                    {r.risk_level}
                  </span>
                  {r.problem}
                </li>
              ))}
            </ul>
          )}
        </Block>
      </div>

      <Block title="执行日志">
        {logsReady ? <ActivityTimeline logs={logs} /> : <div className="page-skeleton__block" style={{ height: 200 }} />}
      </Block>
    </>
  );
}
