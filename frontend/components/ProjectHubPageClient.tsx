"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { MeetingsManager } from "@/components/MeetingsManager";
import { Block, PageTop } from "@/components/PageChrome";
import { ActionButton } from "@/components/ActionButton";
import { api, Project, updateProject } from "@/lib/api";
import { formatApiError } from "@/lib/formatApiError";
import { useI18n } from "@/lib/i18n";

export function ProjectHubPageClient() {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const [project, setProject] = useState<Project | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadErrorRaw, setLoadErrorRaw] = useState("");
  const [formMsg, setFormMsg] = useState("");
  const [formMsgKind, setFormMsgKind] = useState<"danger" | "success">("danger");
  const loadError = loadErrorRaw ? formatApiError(loadErrorRaw, t) : "";

  useEffect(() => {
    setLoadErrorRaw("");
    api<Project>(`/projects/${id}`)
      .then((p) => {
        setProject(p);
        setName(p.name);
      })
      .catch((e) => setLoadErrorRaw(e instanceof Error ? e.message : String(e)));
  }, [id]);

  async function saveName() {
    if (!name.trim()) {
      setFormMsgKind("danger");
      setFormMsg(t("projects.nameRequired"));
      return;
    }
    setBusy(true);
    setLoadErrorRaw("");
    setFormMsg("");
    try {
      const p = await updateProject(id, { name: name.trim() });
      setProject(p);
      setEditing(false);
      setFormMsgKind("success");
      setFormMsg(t("projects.saved"));
    } catch (e) {
      setFormMsgKind("danger");
      setFormMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function cancelEdit() {
    setName(project?.name || "");
    setEditing(false);
    setFormMsg("");
  }

  const notFound = !!loadError && !project;

  return (
    <>
      <PageTop
        title={notFound ? t("errors.projectNotFound") : project?.name || t("projects.title")}
        desc={t("projectHub.desc")}
        action={
          <Link href="/projects" className="btn btn-outline">
            {t("nav.backProjects")}
          </Link>
        }
      />

      {loadError && <p className="alert danger">{loadError}</p>}
      {formMsg && <p className={`alert ${formMsgKind}`}>{formMsg}</p>}

      {notFound ? null : (
      <Block title={t("projectHub.info")}>
        {editing ? (
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} style={{ maxWidth: 420 }} />
            <ActionButton onClick={saveName} disabled={busy}>
              {t("common.save")}
            </ActionButton>
            <button type="button" className="btn-outline" onClick={cancelEdit} disabled={busy}>
              {t("common.cancel")}
            </button>
          </div>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            {project?.summary || t("projectHub.infoHint")}
            <button type="button" className="btn-text" style={{ marginLeft: "0.75rem" }} onClick={() => setEditing(true)}>
              {t("projectHub.editName")}
            </button>
          </p>
        )}
      </Block>
      )}

      {!notFound && <MeetingsManager projectId={id} />}
    </>
  );
}
