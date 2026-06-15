"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Block, PageTop } from "@/components/PageChrome";
import { UploadDropzone } from "@/components/UploadDropzone";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import {
  fetchMeetingFiles,
  FileRecord,
  harnessRunProject,
  isNetworkError,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { isPipelineRunning } from "@/lib/workflow";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export default function MeetingFilesPage() {
  const { id, meetingId } = useParams<{ id: string; meetingId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { t, messages } = useI18n();
  const { live, job, agent, refresh: refreshLive, watchRun, pendingRun } = useProjectLive();
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [pending, setPending] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const formatDoc = (cat: string) => messages.domain.docCategory[cat] || cat;
  const formatParse = (s: string) => messages.domain.parseStatus[s] || s;

  const loadFiles = useCallback(() => {
    fetchMeetingFiles(id, meetingId)
      .then(setFiles)
      .catch((e) => {
        if (!isNetworkError(e)) console.error(e);
      });
  }, [id, meetingId]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  useEffect(() => {
    if (searchParams.get("run") !== "1") return;
    watchRun();
    router.replace(`/projects/${id}/meetings/${meetingId}`, { scroll: false });
  }, [searchParams, watchRun, router, id, meetingId]);

  const running = isPipelineRunning(live?.status ?? "", job?.status) || pendingRun;

  const uploaded = files.length || live?.file_count || 0;
  const meetingCode = (live?.state_json as { meeting_case?: { meeting_code?: string } } | undefined)
    ?.meeting_case?.meeting_code;
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
      const res = await fetch(`${API_BASE}/projects/${id}/meetings/${meetingId}/files`, {
        method: "POST",
        body: fd,
        headers,
      });
      if (!res.ok) throw new Error(await res.text());
      setPending([]);
      setMsg(t("filesPage.uploadOk"));
      loadFiles();
      refreshLive();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runHarness() {
    setBusy(true);
    setMsg("");
    try {
      const result = await harnessRunProject(id, meetingId);
      watchRun();
      router.push(`/projects/${id}/meetings/${meetingId}`);
      if (result.status === "running") {
        setMsg(t("filesPage.harnessStarted"));
      } else {
        setMsg(
          t("filesPage.harnessDone", {
            count: result.finding_count ?? 0,
            finding: messages.domain.finding,
          })
        );
      }
      refreshLive();
      loadFiles();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const msgOk = msg.includes("成功") || msg.includes("complete") || msg.includes("启动") || msg.includes("started");

  return (
    <>
      <PageTop
        title={running ? t("filesPage.runningTitle") : t("filesPage.title")}
        desc={
          running
            ? t("filesPage.runningDesc")
            : meetingCode
              ? t("filesPage.descMeeting", { code: meetingCode })
              : t("filesPage.descDefault")
        }
      />

      {agent && !agent.ready && (
        <div className="alert danger">
          {t("filesPage.agentNotReady")} · {agent.message}
        </div>
      )}
      {msg && <div className={`alert${msgOk ? " success" : " danger"}`}>{msg}</div>}

      <div className={`ingest-grid${running ? " ingest-grid--readonly" : ""}`}>
        {!running && (
        <Block title={t("filesPage.uploadBlock")} hint={t("filesPage.uploadHint")}>
          <UploadDropzone disabled={busy} selectedCount={pending.length} onSelect={(list) => setPending(Array.from(list))} />
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
              <ActionButton loadingLabel={t("filesPage.uploading")} onClick={upload} disabled={busy}>
                {t("filesPage.uploadN", { count: pending.length })}
              </ActionButton>
            ) : uploaded > 0 && agent?.ready ? (
              <ActionButton loadingLabel={t("filesPage.starting")} onClick={runHarness} disabled={busy}>
                {t("filesPage.runHarness")}
              </ActionButton>
            ) : (
              <p className="ingest-hint muted">
                {uploaded === 0 ? t("filesPage.hintNoFiles") : t("filesPage.hintWaitAgent")}
              </p>
            )}
          </div>
        </Block>
        )}

        {running && (
          <p className="muted" style={{ margin: "0 0 1rem" }}>
            {t("filesPage.runningLocked")}
          </p>
        )}

        <Block title={t("filesPage.connected", { count: uploaded })}>
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("filesPage.colFile")}</th>
                <th>{t("filesPage.colCategory")}</th>
                <th>{t("filesPage.colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.id}>
                  <td className="strong">{f.file_name}</td>
                  <td>{formatDoc(f.document_category)}</td>
                  <td>
                    <span className={`badge ${f.parse_status === "done" ? "low" : "neutral"}`}>
                      {formatParse(f.parse_status)}
                    </span>
                  </td>
                </tr>
              ))}
              {!files.length && (
                <tr>
                  <td colSpan={3} className="empty">
                    {t("filesPage.emptyFiles")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {uploaded > 0 && (
            <p className="muted ingest-foot">
              <Link href={`/projects/${id}/meetings/${meetingId}/risks`}>{t("filesPage.footFindings")}</Link>
              {" · "}
              <Link href={`/projects/${id}/meetings/${meetingId}/outputs`}>{t("filesPage.footOutputs")}</Link>
            </p>
          )}
        </Block>
      </div>
    </>
  );
}
