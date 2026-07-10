"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageTop } from "@/components/PageChrome";
import { Project, api, batchDeleteProjects, updateProject } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { formatDate } from "@/lib/format";

const PROJECTS_PAGE_SIZE = 50;

async function deleteProjectsWithFallback(projectIds: string[]) {
  const ids = Array.from(new Set(projectIds));
  let batchDeleted = 0;
  let batchError = "";

  try {
    const result = await batchDeleteProjects(ids);
    batchDeleted = result.deleted;
  } catch (e) {
    batchError = e instanceof Error ? e.message : String(e);
  }

  const afterBatch = await api<Project[]>("/projects", { cache: "no-store" });
  const afterBatchIds = new Set(afterBatch.map((p) => p.id));
  const remainingIds = ids.filter((id) => afterBatchIds.has(id));

  let fallbackDeleted = 0;
  for (const id of remainingIds) {
    try {
      await api(`/projects/${id}`, { method: "DELETE" });
      fallbackDeleted += 1;
    } catch {
      /* final refresh below calculates the actual remaining IDs */
    }
  }

  const afterFallback = remainingIds.length
    ? await api<Project[]>("/projects", { cache: "no-store" })
    : afterBatch;
  const finalIds = new Set(afterFallback.map((p) => p.id));
  const stillRemainingIds = ids.filter((id) => finalIds.has(id));
  const deleted = ids.length - stillRemainingIds.length;

  if (deleted === 0 && batchError) {
    throw new Error(batchError);
  }

  return {
    requested: ids.length,
    batchDeleted,
    fallbackDeleted,
    deleted,
    failed: stillRemainingIds.length,
    remainingIds: stillRemainingIds,
  };
}

export default function ProjectsPage() {
  const { t, messages } = useI18n();
  const statusLabel = (s: string) => messages.workflow.status[s] || s;
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [deleteBusyId, setDeleteBusyId] = useState<string | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [pageMsg, setPageMsg] = useState("");
  const [pageMsgKind, setPageMsgKind] = useState<"danger" | "success">("danger");

  async function load() {
    setLoading(true);
    try {
      const nextProjects = await api<Project[]>("/projects", { cache: "no-store" });
      setProjects(nextProjects);
      const validIds = new Set(nextProjects.map((p) => p.id));
      setSelected((prev) => new Set(Array.from(prev).filter((id) => validIds.has(id))));
      return nextProjects;
    } catch (e) {
      setPageMsgKind("danger");
      setPageMsg(e instanceof Error ? e.message : String(e));
      return [];
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filteredProjects = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter((p) =>
      [p.name, p.status, p.summary || ""].some((value) => value.toLowerCase().includes(q))
    );
  }, [projects, query]);

  const totalPages = Math.max(1, Math.ceil(filteredProjects.length / PROJECTS_PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visibleProjects = useMemo(() => {
    const start = (currentPage - 1) * PROJECTS_PAGE_SIZE;
    return filteredProjects.slice(start, start + PROJECTS_PAGE_SIZE);
  }, [currentPage, filteredProjects]);
  const visibleProjectIds = useMemo(() => visibleProjects.map((p) => p.id), [visibleProjects]);
  const selectedVisibleCount = visibleProjectIds.filter((id) => selected.has(id)).length;
  const allSelected = visibleProjectIds.length > 0 && selectedVisibleCount === visibleProjectIds.length;
  const actionBusy = batchBusy || savingId !== null || deleteBusyId !== null;

  useEffect(() => {
    setPage(1);
  }, [query]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allSelected) visibleProjectIds.forEach((id) => next.delete(id));
      else visibleProjectIds.forEach((id) => next.add(id));
      return next;
    });
  }

  async function saveEdit(id: string) {
    const name = editName.trim();
    if (!name) {
      setPageMsgKind("danger");
      setPageMsg(t("projects.nameRequired"));
      return;
    }
    setSavingId(id);
    setPageMsg("");
    try {
      await updateProject(id, { name });
      setEditId(null);
      setEditName("");
      setPageMsgKind("success");
      setPageMsg(t("projects.saved"));
      void load();
    } catch (e) {
      setPageMsgKind("danger");
      setPageMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingId(null);
    }
  }

  async function removeOne(id: string, name: string) {
    if (!confirm(t("projects.confirmDelete", { name }))) return;
    setDeleteBusyId(id);
    setPageMsg("");
    try {
      await api(`/projects/${id}`, { method: "DELETE" });
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      setPageMsgKind("success");
      setPageMsg(t("projects.deletedOne", { name }));
      void load();
    } catch (e) {
      setPageMsgKind("danger");
      setPageMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleteBusyId(null);
    }
  }

  async function removeSelected() {
    if (!selected.size || !confirm(t("projects.confirmBatch", { count: selected.size }))) return;
    const ids = Array.from(selected);
    setBatchBusy(true);
    setPageMsg("");
    try {
      const result = await deleteProjectsWithFallback(ids);
      setSelected(new Set(result.remainingIds));
      await load();
      if (result.deleted <= 0) {
        setPageMsgKind("danger");
        setPageMsg(t("projects.deleteNone"));
      } else if (result.deleted < result.requested) {
        setPageMsgKind("danger");
        setPageMsg(t("projects.deletedPartial", { deleted: result.deleted, count: result.requested, failed: result.failed }));
      } else {
        setPageMsgKind("success");
        setPageMsg(t("projects.deletedSelected", { count: result.deleted }));
      }
    } catch (e) {
      setPageMsgKind("danger");
      setPageMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBatchBusy(false);
    }
  }

  return (
    <>
      <PageTop
        title={t("projects.title")}
        desc={t("projects.desc")}
        action={
          <Link href="/projects/new" className="btn">
            {t("projects.new")}
          </Link>
        }
      />

      {pageMsg && <p className={`alert ${pageMsgKind}`}>{pageMsg}</p>}

      <div className="table-toolbar">
        <div className="table-toolbar__controls">
          <label className="check-row">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleAll}
              disabled={!visibleProjects.length || loading || batchBusy}
            />
            {t("projects.selectVisible")}
          </label>
          <input
            className="input input-sm table-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("projects.searchPlaceholder")}
            disabled={loading || batchBusy}
          />
          <span className="muted table-count">
            {t("projects.pageStatus", { page: currentPage, total: totalPages, count: filteredProjects.length })}
          </span>
        </div>
        {selected.size > 0 && (
          <div className="table-toolbar__actions">
            <button
              type="button"
              className="btn-text btn-text--danger"
              onClick={removeSelected}
              disabled={batchBusy || loading}
            >
              {batchBusy ? t("projects.deleteSelectedBusy") : t("projects.deleteSelected")} ({selected.size})
            </button>
          </div>
        )}
        <div className="table-pager">
          <button
            type="button"
            className="btn-text"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={loading || currentPage <= 1}
          >
            {t("projects.prevPage")}
          </button>
          <button
            type="button"
            className="btn-text"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={loading || currentPage >= totalPages}
          >
            {t("projects.nextPage")}
          </button>
        </div>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th style={{ width: 36 }} />
            <th>{t("projects.name")}</th>
            <th>{t("projects.status")}</th>
            <th>{t("projects.created")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={5} className="loading">
                {t("common.loading")}
              </td>
            </tr>
          )}
          {!loading &&
            visibleProjects.map((p) => (
              <tr key={p.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(p.id)}
                    disabled={batchBusy || deleteBusyId === p.id}
                    onChange={() =>
                      setSelected((prev) => {
                        const n = new Set(prev);
                        if (n.has(p.id)) n.delete(p.id);
                        else n.add(p.id);
                        return n;
                      })
                    }
                  />
                </td>
                <td>
                  {editId === p.id ? (
                    <input
                      className="input input-sm"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && saveEdit(p.id)}
                      disabled={savingId === p.id}
                    />
                  ) : (
                    <Link href={`/projects/${p.id}`} className="strong">
                      {p.name}
                    </Link>
                  )}
                  {p.summary && (
                    <div className="muted" style={{ fontSize: "0.75rem", marginTop: "0.2rem" }}>
                      {p.summary}
                    </div>
                  )}
                </td>
                <td>{statusLabel(p.status)}</td>
                <td className="mono">{formatDate(p.created_at)}</td>
                <td style={{ textAlign: "right" }}>
                  <div className="table-actions">
                  {editId === p.id ? (
                    <>
                      <button type="button" className="btn-text" onClick={() => saveEdit(p.id)} disabled={savingId === p.id}>
                        {savingId === p.id ? t("common.processing") : t("common.save")}
                      </button>
                      <button type="button" className="btn-text" onClick={() => setEditId(null)} disabled={savingId === p.id}>
                        {t("common.cancel")}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="btn-text"
                        onClick={() => {
                          setEditId(p.id);
                          setEditName(p.name);
                        }}
                        disabled={actionBusy}
                      >
                        {t("common.edit")}
                      </button>
                      <button
                        type="button"
                        className="btn-text btn-text--danger"
                        onClick={() => removeOne(p.id, p.name)}
                        disabled={actionBusy}
                      >
                        {deleteBusyId === p.id ? t("common.processing") : t("common.delete")}
                      </button>
                    </>
                  )}
                  </div>
                </td>
              </tr>
            ))}
          {!loading && projects.length === 0 && (
            <tr>
              <td colSpan={5} className="empty">
                {t("projects.empty")} · <Link href="/projects/new">{t("common.create")}</Link>
              </td>
            </tr>
          )}
          {!loading && projects.length > 0 && filteredProjects.length === 0 && (
            <tr>
              <td colSpan={5} className="empty">
                {t("projects.noMatches")}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
