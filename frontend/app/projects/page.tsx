"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageTop } from "@/components/PageChrome";
import { Project, api } from "@/lib/api";
import { STATUS_LABEL, overallProgress } from "@/lib/workflow";
import { formatDate } from "@/lib/format";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api<Project[]>("/projects")
      .then(setProjects)
      .catch(console.error)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function remove(id: string, name: string) {
    if (!confirm(`确定删除「${name}」？关联资料、风险与日志将一并清除。`)) return;
    try {
      await api(`/projects/${id}`, { method: "DELETE" });
      load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除失败");
    }
  }

  return (
    <>
      <PageTop
        title="Projects"
        desc="点击进入 · 顶部 HUD 实时追踪 11 步分析链路"
        action={
          <Link href="/projects/new" className="btn">
            新建
          </Link>
        }
      />

      <table className="data-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>进度</th>
            <th>阶段</th>
            <th>创建</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={5} className="loading">
                加载中
              </td>
            </tr>
          )}
          {!loading &&
            projects.map((p) => {
              const pct = overallProgress(p.status);
              return (
                <tr key={p.id}>
                  <td>
                    <Link href={`/projects/${p.id}`} className="strong">
                      {p.name}
                    </Link>
                    {p.summary && (
                      <div className="muted" style={{ fontSize: "0.75rem", marginTop: "0.2rem" }}>
                        {p.summary}
                      </div>
                    )}
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span className="mono">{pct}%</span>
                      <div className="row-progress" style={{ width: 64 }}>
                        <span style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  </td>
                  <td>{STATUS_LABEL[p.status] || p.status}</td>
                  <td className="mono">{formatDate(p.created_at)}</td>
                  <td style={{ textAlign: "right" }}>
                    <button type="button" className="link-btn" onClick={() => remove(p.id, p.name)}>
                      删除
                    </button>
                  </td>
                </tr>
              );
            })}
          {!loading && projects.length === 0 && (
            <tr>
              <td colSpan={5} className="empty">
                暂无项目 · <Link href="/projects/new">创建</Link>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
