"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Block } from "@/components/PageChrome";
import { FolderPicker } from "@/components/FolderPicker";
import {
  Meeting,
  batchDeleteMeetings,
  createMeeting,
  deleteMeeting,
  fetchMeetings,
  harnessImportToProject,
  updateMeeting,
} from "@/lib/api";
import { formatApiError } from "@/lib/formatApiError";
import { useI18n } from "@/lib/i18n";
import { formatDate } from "@/lib/format";

type Props = {
  projectId: string;
};

type EditState = {
  id: string;
  meeting_code: string;
  meeting_title: string;
  observation_type: string;
};

export function MeetingsManager({ projectId }: Props) {
  const router = useRouter();
  const { t, messages } = useI18n();
  const statusLabel = (s: string) => messages.workflow.status[s] || s;
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importFiles, setImportFiles] = useState<File[]>([]);
  const [importTitle, setImportTitle] = useState("");
  const [edit, setEdit] = useState<EditState | null>(null);
  const [form, setForm] = useState({
    meeting_code: "",
    meeting_title: "",
    observation_type: t("meetings.defaultType"),
    meeting_type: "",
    meeting_date: "",
  });

  const load = useCallback(() => {
    setLoading(true);
    fetchMeetings(projectId)
      .then(setMeetings)
      .catch((e) => {
        const err = e as Error & { code?: string | null };
        setMsg(formatApiError(err.message || String(e), t, err.code));
      })
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setForm((f) => ({ ...f, observation_type: t("meetings.defaultType") }));
  }, [t]);

  const allSelected = meetings.length > 0 && selected.size === meetings.length;

  function toggleAll() {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(meetings.map((m) => m.id)));
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onCreate() {
    if (!form.meeting_code.trim()) {
      setMsg(t("meetings.codeRequired"));
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      await createMeeting(projectId, form);
      setShowCreate(false);
      setForm({
        meeting_code: "",
        meeting_title: "",
        observation_type: t("meetings.defaultType"),
        meeting_type: "",
        meeting_date: "",
      });
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onImportFolder() {
    if (!importFiles.length) {
      setMsg(t("meetings.importPickFolder"));
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const result = await harnessImportToProject(projectId, importFiles, {
        meetingTitle: importTitle.trim() || undefined,
        runAnalysis: true,
      });
      setShowImport(false);
      setImportFiles([]);
      setImportTitle("");
      if (result.meeting_id) {
        router.push(`/projects/${projectId}/meetings/${result.meeting_id}/files?run=1`);
        return;
      }
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onSaveEdit() {
    if (!edit) return;
    setBusy(true);
    try {
      await updateMeeting(projectId, edit.id, {
        meeting_code: edit.meeting_code,
        meeting_title: edit.meeting_title || undefined,
        observation_type: edit.observation_type || undefined,
      });
      setEdit(null);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteOne(id: string, code: string) {
    if (!confirm(t("meetings.confirmDeleteOne", { code }))) return;
    setBusy(true);
    try {
      await deleteMeeting(projectId, id);
      setSelected((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onBatchDelete() {
    if (!selected.size) return;
    if (!confirm(t("meetings.confirmBatch", { count: selected.size }))) return;
    setBusy(true);
    try {
      await batchDeleteMeetings(projectId, Array.from(selected));
      setSelected(new Set());
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Block title={t("meetings.title")} hint={t("meetings.hint")}>
      {msg && <p className="alert danger">{msg}</p>}

      <div className="table-toolbar">
        <label className="check-row">
          <input type="checkbox" checked={allSelected} onChange={toggleAll} disabled={!meetings.length} />
          {t("rail.selectAll")}
        </label>
        <div className="table-toolbar__actions">
          {selected.size > 0 && (
            <button type="button" className="btn-text btn-text--danger" onClick={onBatchDelete} disabled={busy}>
              {t("projects.deleteSelected")} ({selected.size})
            </button>
          )}
          <ActionButton variant="outline" onClick={() => setShowImport((v) => !v)} disabled={busy}>
            {showImport ? t("common.cancel") : t("meetings.importFolder")}
          </ActionButton>
          <ActionButton variant="outline" onClick={() => setShowCreate((v) => !v)} disabled={busy}>
            {showCreate ? t("common.cancel") : t("meetings.new")}
          </ActionButton>
        </div>
      </div>

      {showImport && (
        <div className="inline-form" style={{ marginBottom: "1rem", display: "grid", gap: "0.75rem", maxWidth: 720 }}>
          <FolderPicker selectedFiles={importFiles} onSelect={setImportFiles} disabled={busy} />
          <input
            className="input"
            placeholder={t("meetings.importTitleOptional")}
            value={importTitle}
            onChange={(e) => setImportTitle(e.target.value)}
            disabled={busy}
          />
          <ActionButton
            loadingLabel={t("meetings.importBusy")}
            onClick={onImportFolder}
            disabled={busy || !importFiles.length}
          >
            {t("meetings.importRun")}
          </ActionButton>
        </div>
      )}

      {showCreate && (
        <div className="inline-form" style={{ marginBottom: "1rem" }}>
          <input
            className="input"
            placeholder={t("meetings.codePlaceholder")}
            value={form.meeting_code}
            onChange={(e) => setForm({ ...form, meeting_code: e.target.value })}
          />
          <input
            className="input"
            placeholder={t("meetings.titleField")}
            value={form.meeting_title}
            onChange={(e) => setForm({ ...form, meeting_title: e.target.value })}
          />
          <input
            className="input"
            placeholder={t("meetings.observationType")}
            value={form.observation_type}
            onChange={(e) => setForm({ ...form, observation_type: e.target.value })}
          />
          <ActionButton loadingLabel={t("meetings.creating")} onClick={onCreate} disabled={busy}>
            {t("common.create")}
          </ActionButton>
        </div>
      )}

      <table className="data-table">
        <thead>
          <tr>
            <th style={{ width: 36 }} />
            <th>{t("meetings.code")}</th>
            <th>{t("meetings.titleField")}</th>
            <th>{t("meetings.files")}</th>
            <th>{t("meetings.findings")}</th>
            <th>{t("meetings.status")}</th>
            <th>{t("meetings.updated")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={8} className="loading">
                {t("common.loading")}
              </td>
            </tr>
          )}
          {!loading &&
            meetings.map((m) => (
              <tr key={m.id}>
                <td>
                  <input type="checkbox" checked={selected.has(m.id)} onChange={() => toggleOne(m.id)} />
                </td>
                <td className="mono strong">
                  {edit?.id === m.id ? (
                    <input
                      className="input input-sm"
                      value={edit.meeting_code}
                      onChange={(e) => setEdit({ ...edit, meeting_code: e.target.value })}
                    />
                  ) : (
                    <Link href={`/projects/${projectId}/meetings/${m.id}`}>{m.meeting_code}</Link>
                  )}
                </td>
                <td>
                  {edit?.id === m.id ? (
                    <input
                      className="input input-sm"
                      value={edit.meeting_title}
                      onChange={(e) => setEdit({ ...edit, meeting_title: e.target.value })}
                    />
                  ) : (
                    <Link
                      href={`/projects/${projectId}/meetings/${m.id}`}
                      style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", color: "inherit", textDecoration: "none" }}
                    >
                      <span className="strong">{m.meeting_title || m.meeting_code}</span>
                      {m.observation_type && <span className="muted">· {m.observation_type}</span>}
                    </Link>
                  )}
                </td>
                <td>{m.file_count ?? 0}</td>
                <td>{m.risk_count ?? 0}</td>
                <td>{statusLabel(m.status)}</td>
                <td className="mono">{formatDate(m.updated_at)}</td>
                <td style={{ textAlign: "right" }}>
                  <div className="table-actions">
                  {edit?.id === m.id ? (
                    <>
                      <button type="button" className="btn-text" onClick={onSaveEdit} disabled={busy}>
                        {t("common.save")}
                      </button>
                      <button type="button" className="btn-text" onClick={() => setEdit(null)}>
                        {t("common.cancel")}
                      </button>
                    </>
                  ) : (
                    <>
                      <Link href={`/projects/${projectId}/meetings/${m.id}`} className="btn-text">
                        {t("common.enter")}
                      </Link>
                      <button
                        type="button"
                        className="btn-text"
                        onClick={() =>
                          setEdit({
                            id: m.id,
                            meeting_code: m.meeting_code,
                            meeting_title: m.meeting_title || "",
                            observation_type: m.observation_type || "",
                          })
                        }
                      >
                        {t("common.edit")}
                      </button>
                      <button type="button" className="btn-text btn-text--danger" onClick={() => onDeleteOne(m.id, m.meeting_code)}>
                        {t("common.delete")}
                      </button>
                    </>
                  )}
                  </div>
                </td>
              </tr>
            ))}
          {!loading && meetings.length === 0 && (
            <tr>
              <td colSpan={8} className="empty">
                {t("meetings.empty")}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Block>
  );
}
