"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ActivityTimeline } from "@/components/ActivityTimeline";
import { Block, PageTop } from "@/components/PageChrome";
import { RiskChart } from "@/components/RiskChart";
import { Job, Project, ProjectSummary, api } from "@/lib/api";
import { STATUS_LABEL, overallProgress } from "@/lib/workflow";

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
  const [project, setProject] = useState<Project | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [logs, setLogs] = useState<Log[]>([]);

  const load = useCallback(() => {
    api<Project>(`/projects/${id}`).then(setProject).catch(console.error);
    api<Job>(`/projects/${id}/jobs/latest`)
      .then(setJob)
      .catch(() => setJob(null));
    api<ProjectSummary>(`/projects/${id}/summary`)
      .then(setSummary)
      .catch(() => setSummary(null));
    api<Log[]>(`/projects/${id}/logs`).then(setLogs).catch(console.error);
  }, [id]);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [load]);

  if (!project) return <p className="loading">加载中</p>;

  const agentPlan = project.state_json?.agent_plan as
    | { agent_mode?: string; reasoning?: string; priority_actions?: string[] }
    | undefined;

  const pct = overallProgress(project.status, job?.current_step, job?.progress_pct, job?.status);

  return (
    <>
      <PageTop
        title={project.name}
        desc={`${STATUS_LABEL[project.status] || project.status}${project.summary ? ` · ${project.summary}` : ""} · 进度 ${pct}%`}
      />

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

      <div className="grid-2">
        <Block title={`文件 · ${project.files?.length || 0}`}>
          {(project.files || []).length === 0 ? (
            <p className="muted">尚未上传</p>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: "none", fontSize: "0.8125rem" }}>
              {(project.files || []).map((f) => (
                <li key={f.id} style={{ padding: "0.4rem 0", borderBottom: "1px solid var(--line)" }}>
                  {f.file_name}
                  <span className="muted"> · {f.document_category}</span>
                </li>
              ))}
            </ul>
          )}
        </Block>

        <Block title={`风险 · ${project.risks?.length || 0}`}>
          {(project.risks || []).length === 0 ? (
            <p className="muted">暂无</p>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: "none", fontSize: "0.8125rem" }}>
              {(project.risks || []).slice(0, 6).map((r) => (
                <li key={r.id} style={{ padding: "0.4rem 0", borderBottom: "1px solid var(--line)", display: "flex", gap: "0.5rem" }}>
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
        <ActivityTimeline logs={logs} />
      </Block>
    </>
  );
}
