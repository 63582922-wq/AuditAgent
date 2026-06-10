"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Block, PageTop } from "@/components/PageChrome";
import { UploadDropzone } from "@/components/UploadDropzone";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import { fetchProjectFiles, FileRecord, api, isNetworkError } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export default function ProjectFilesPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { live, agent, refresh: refreshLive } = useProjectLive();
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [pending, setPending] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const loadFiles = useCallback(() => {
    fetchProjectFiles(id)
      .then(setFiles)
      .catch((e) => {
        if (!isNetworkError(e)) console.error(e);
      });
  }, [id]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const uploaded = files.length || live?.file_count || 0;
  const hasPriorRun = Boolean(live?.state_json?.agent_plan);
  const canAnalyze = uploaded > 0 && agent?.ready;
  const hasPending = pending.length > 0;

  async function upload() {
    if (!pending.length) return;
    setBusy(true);
    setMsg("");
    const fd = new FormData();
    pending.forEach((f) => fd.append("files", f));
    try {
      const headers: Record<string, string> = {};
      if (API_KEY) headers["X-API-Key"] = API_KEY;
      const res = await fetch(`${API_BASE}/projects/${id}/files`, { method: "POST", body: fd, headers });
      if (!res.ok) throw new Error(await res.text());
      setPending([]);
      setMsg("上传成功 · 可启动分析");
      loadFiles();
      refreshLive();
    } catch (e) {
      if (isNetworkError(e)) {
        setMsg("无法连接后端 · 请先启动 backend（8000 端口）");
      } else {
        setMsg(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  async function analyze(full = false) {
    setMsg("");
    router.push(`/projects/${id}`);
    try {
      const path = full || !hasPriorRun ? "analyze" : "analyze-incremental";
      await api(`/projects/${id}/${path}`, { method: "POST" });
      refreshLive();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <>
      <PageTop title="资料" desc="选文件 → 上传 → 启动分析 · 补资料后可选增量或全量重跑" />

      {agent && !agent.ready && <div className="alert danger">Agent 未就绪 · {agent.message}</div>}
      {msg && (
        <div className={`alert${msg.includes("成功") ? " success" : " danger"}`}>{msg}</div>
      )}

      <div className="ingest-grid">
        <Block title="上传" hint="xlsx · csv · docx · pdf · jpg · png">
          <UploadDropzone
            disabled={busy}
            selectedCount={pending.length}
            onSelect={(list) => setPending(Array.from(list))}
          />
          {hasPending && (
            <ul className="file-chips">
              {pending.map((f) => (
                <li key={`${f.name}-${f.size}`} className="file-chip">
                  <span className="file-chip__name">{f.name}</span>
                  <span className="file-chip__size mono">{(f.size / 1024).toFixed(0)} KB</span>
                </li>
              ))}
            </ul>
          )}

          <div className="ingest-actions">
            {hasPending ? (
              <ActionButton loadingLabel="上传中…" onClick={upload} disabled={busy}>
                上传 {pending.length} 个文件
              </ActionButton>
            ) : canAnalyze ? (
              <>
                <ActionButton loadingLabel="启动中…" onClick={() => analyze(false)} disabled={busy}>
                  {hasPriorRun ? "增量分析" : "启动分析"}
                </ActionButton>
                {hasPriorRun && (
                  <ActionButton variant="outline" loadingLabel="启动中…" onClick={() => analyze(true)} disabled={busy}>
                    全量重跑
                  </ActionButton>
                )}
              </>
            ) : (
              <p className="ingest-hint muted">
                {uploaded === 0 ? "请先选择并上传文件" : "等待 Agent 就绪…"}
              </p>
            )}
          </div>
        </Block>

        <Block title={`已接入 · ${uploaded}`}>
          <div className="ingest-status">
            <div className={`ingest-status__item${uploaded > 0 ? " is-ok" : ""}`}>
              <span className="ingest-status__label">文件</span>
              <span className="ingest-status__val">{uploaded}</span>
            </div>
            <div className={`ingest-status__item${agent?.ready ? " is-ok" : ""}`}>
              <span className="ingest-status__label">Agent</span>
              <span className="ingest-status__val">{agent?.ready ? "ONLINE" : "OFF"}</span>
            </div>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>文件</th>
                <th>类别</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.id}>
                  <td className="strong">{f.file_name}</td>
                  <td>{f.document_category}</td>
                  <td>
                    <span className={`badge ${f.parse_status === "done" ? "low" : "neutral"}`}>{f.parse_status}</span>
                  </td>
                </tr>
              ))}
              {!files.length && (
                <tr>
                  <td colSpan={3} className="empty">
                    暂无文件
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {uploaded > 0 && (
            <p className="muted ingest-foot">
              分析进度见顶部 HUD ·{" "}
              <Link href={`/projects/${id}/risks`}>风险</Link>
              {" · "}
              <Link href={`/projects/${id}/outputs`}>交付物</Link>
            </p>
          )}
        </Block>
      </div>
    </>
  );
}
