"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { AgentStatus, Project, api } from "@/lib/api";

export default function ProjectFilesPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [files, setFiles] = useState<FileList | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    api<Project>(`/projects/${id}`).then(setProject).catch(console.error);
    api<AgentStatus>("/agent/status").then(setAgent).catch(console.error);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function upload() {
    if (!files?.length) return;
    setBusy(true);
    setMsg("");
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api"}/projects/${id}/files`, {
        method: "POST",
        body: fd,
      });
      setMsg("上传成功");
      load();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function analyze() {
    setBusy(true);
    setMsg("");
    try {
      await api(`/projects/${id}/analyze`, { method: "POST" });
      setMsg("分析已启动，见左侧流程进度");
      load();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTop title="资料" desc="上传 fixtures/ 下 5 个样例可跑完整测试流程。" />

      {agent && !agent.ready && <div className="alert danger">无法分析：{agent.message}</div>}
      {msg && <div className={`alert${msg.includes("成功") || msg.includes("启动") ? " success" : " danger"}`}>{msg}</div>}

      <Block
        title="上传"
        action={
          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button className="btn-outline" onClick={upload} disabled={busy || !files?.length}>
              上传
            </button>
            <button className="btn" onClick={analyze} disabled={busy || !agent?.ready}>
              开始分析
            </button>
          </div>
        }
      >
        <div className="file-zone">
          <input type="file" multiple onChange={(e) => setFiles(e.target.files)} />
        </div>
      </Block>

      <Block title={`已上传 · ${project?.files?.length || 0}`}>
        <table className="data-table">
          <thead>
            <tr>
              <th>文件</th>
              <th>类型</th>
              <th>类别</th>
              <th>置信度</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {(project?.files || []).map((f) => (
              <tr key={f.id}>
                <td className="strong">{f.file_name}</td>
                <td>{f.file_type}</td>
                <td>{f.document_category}</td>
                <td className="mono">{f.confidence != null ? `${(f.confidence * 100).toFixed(0)}%` : "—"}</td>
                <td>{f.parse_status}</td>
              </tr>
            ))}
            {!project?.files?.length && (
              <tr>
                <td colSpan={5} className="empty">
                  空
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Block>
    </>
  );
}
