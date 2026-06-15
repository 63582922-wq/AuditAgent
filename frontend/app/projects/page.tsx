"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageTop } from "@/components/PageChrome";
import { Project, api, batchDeleteProjects, updateProject } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { formatDate } from "@/lib/format";

export default function ProjectsPage() {
  const { t, messages } = useI18n();
  const statusLabel = (s: string) => messages.workflow.status[s] || s;
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const [pageMsg, setPageMsg] = useState("");

  function load() {
    setLoading(true);
    api<Project[]>("/projects")
      .then(setProjects)
      .catch((e) => setPageMsg(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  const allSelected = projects.length > 0 && selected.size === projects.length;

  function toggleAll() {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(projects.map((p) => p.id)));
  }

  async function saveEdit(id: string) {
    try {
      await updateProject(id, { name: editName.trim() });
      setEditId(null);
      load();
    } catch (e) {
      setPageMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function removeOne(id: string, name: string) {
    if (!confirm(t("projects.confirmDelete", { name }))) return;
    try {
      await api(`/projects/${id}`, { method: "DELETE" });
      load();
    } catch (e) {
      setPageMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function removeSelected() {
    if (!selected.size || !confirm(t("projects.confirmBatch", { count: selected.size }))) return;
    try {
      await batchDeleteProjects(Array.from(selected));
      setSelected(new Set());
      load();
    } catch (e) {
      setPageMsg(e instanceof Error ? e.message : String(e));
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

      {pageMsg && <p className="alert danger">{pageMsg}</p>}

      <div className="table-toolbar">
        <label className="check-row">
          <input type="checkbox" checked={allSelected} onChange={toggleAll} disabled={!projects.length} />
          {t("rail.selectAll")}
        </label>
        {selected.size > 0 && (
          <button type="button" className="btn-text btn-text--danger" onClick={removeSelected}>
            {t("projects.deleteSelected")} ({selected.size})
          </button>
        )}
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
            projects.map((p) => (
              <tr key={p.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(p.id)}
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
                      <button type="button" className="btn-text" onClick={() => saveEdit(p.id)}>
                        {t("common.save")}
                      </button>
                      <button type="button" className="btn-text" onClick={() => setEditId(null)}>
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
                      >
                        {t("common.edit")}
                      </button>
                      <button type="button" className="btn-text btn-text--danger" onClick={() => removeOne(p.id, p.name)}>
                        {t("common.delete")}
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
        </tbody>
      </table>
    </>
  );
}
