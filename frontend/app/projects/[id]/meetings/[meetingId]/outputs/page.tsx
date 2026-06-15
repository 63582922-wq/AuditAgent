"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { ActionButton } from "@/components/ActionButton";
import { AgentBriefsPanel } from "@/components/AgentBriefsPanel";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import {
  OutputRecord,
  acceptMeetingDeliverables,
  downloadUrl,
  rejectMeetingDeliverables,
  api,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useDocumentVisible } from "@/lib/useDocumentVisible";
import { isPipelineRunning } from "@/lib/workflow";

function dedupeOutputs(items: OutputRecord[]): OutputRecord[] {
  const byFile = new Map<string, OutputRecord>();
  for (const o of items) {
    const prev = byFile.get(o.file_name);
    if (!prev) {
      byFile.set(o.file_name, o);
      continue;
    }
    const preferFinding = (a: OutputRecord, b: OutputRecord) =>
      a.output_type.startsWith("finding_") ? a : b.output_type.startsWith("finding_") ? b : a;
    byFile.set(o.file_name, preferFinding(o, prev));
  }
  return Array.from(byFile.values());
}

export default function MeetingOutputsPage() {
  const { id, meetingId } = useParams<{ id: string; meetingId: string }>();
  const { t, messages } = useI18n();
  const { live: project, job, refresh: refreshLive } = useProjectLive();
  const documentVisible = useDocumentVisible();
  const [outputs, setOutputs] = useState<OutputRecord[]>([]);
  const [rejectComment, setRejectComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState("");

  const outputLabel = (type: string) => messages.domain.outputType[type] || type;
  const running = isPipelineRunning(project?.status ?? "", job?.status);

  const refresh = useCallback(async () => {
    const outs = await api<OutputRecord[]>(`/projects/${id}/meetings/${meetingId}/outputs`);
    setOutputs(outs);
  }, [id, meetingId]);

  useEffect(() => {
    refresh().catch(console.error);
    if (!documentVisible || !running) return;
    const poll = setInterval(() => refresh().catch(console.error), 5000);
    return () => clearInterval(poll);
  }, [documentVisible, refresh, running]);

  const deliverable = project?.state_json?.deliverable;
  const critic = project?.state_json?.runtime?.critic;
  const sortedOutputs = dedupeOutputs(outputs).sort((a, b) => {
    if (a.output_type === "deliverable_package") return -1;
    if (b.output_type === "deliverable_package") return 1;
    return 0;
  });
  const canReview =
    outputs.length > 0 &&
    ["completed", "needs_review", "deliverable_rejected"].includes(project?.status ?? "") &&
    deliverable?.status !== "accepted";

  async function onAccept() {
    setBusy(true);
    setActionMsg("");
    try {
      await acceptMeetingDeliverables(id, meetingId);
      await Promise.all([refresh(), refreshLive()]);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : t("outputsPage.acceptFail"));
    } finally {
      setBusy(false);
    }
  }

  async function onReject(reanalyze = false) {
    setBusy(true);
    setActionMsg("");
    try {
      await rejectMeetingDeliverables(id, meetingId, rejectComment, reanalyze);
      await Promise.all([refresh(), refreshLive()]);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : t("outputsPage.rejectFail"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTop title={t("outputsPage.title")} desc={t("outputsPage.desc")} />

      {actionMsg && <div className="alert danger">{actionMsg}</div>}

      <AgentBriefsPanel state={project?.state_json} />

      {critic && (
        <Block title={messages.domain.criticAgent} hint={t("outputsPage.criticHint")}>
          <p className="muted" style={{ margin: 0, fontSize: "0.875rem", lineHeight: 1.6 }}>
            {t("outputsPage.criticValidated", { count: critic.validated ?? 0 })}
            {(critic.flagged ?? 0) > 0
              ? `${t("outputsPage.criticFlagged", { count: critic.flagged ?? 0 })}${
                  critic.readjudicate_rounds
                    ? t("outputsPage.criticRounds", { rounds: critic.readjudicate_rounds })
                    : ""
                }`
              : t("outputsPage.criticPassed")}
            {critic.outputs_regenerated ? t("outputsPage.criticRegen") : ""}
          </p>
        </Block>
      )}

      {deliverable?.status === "accepted" && (
        <Block className="settling-banner settling-banner--ok">{t("outputsPage.accepted")}</Block>
      )}
      {deliverable?.status === "rejected" && (
        <Block className="settling-banner settling-banner--warn">
          {deliverable.comment
            ? t("outputsPage.rejectedWith", { comment: deliverable.comment })
            : t("outputsPage.rejected")}
        </Block>
      )}

      {canReview && (
        <Block>
          <p className="muted" style={{ marginBottom: "1rem" }}>
            {t("outputsPage.reviewHint")}
          </p>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
            <ActionButton onClick={onAccept} disabled={busy}>
              {t("outputsPage.accept")}
            </ActionButton>
            <input
              type="text"
              placeholder={t("outputsPage.rejectPlaceholder")}
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              className="input"
              style={{ minWidth: "16rem", flex: 1 }}
            />
            <ActionButton variant="ghost" onClick={() => onReject(false)} disabled={busy}>
              {t("outputsPage.reject")}
            </ActionButton>
            <ActionButton variant="outline" onClick={() => onReject(true)} disabled={busy}>
              {t("outputsPage.rejectReanalyze")}
            </ActionButton>
          </div>
        </Block>
      )}

      <table className="data-table">
        <thead>
          <tr>
            <th>{t("outputsPage.colType")}</th>
            <th>{t("outputsPage.colFile")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {sortedOutputs.map((o) => (
            <tr key={o.id} className={o.output_type === "deliverable_package" ? "strong" : undefined}>
              <td>{outputLabel(o.output_type)}</td>
              <td className="strong">{o.file_name}</td>
              <td style={{ textAlign: "right" }}>
                <a href={downloadUrl(id, o.id)} target="_blank" rel="noreferrer" className="btn-text">
                  {o.output_type === "deliverable_package" ? t("outputsPage.downloadZip") : t("outputsPage.download")}
                </a>
              </td>
            </tr>
          ))}
          {sortedOutputs.length === 0 && (
            <tr>
              <td colSpan={3} className="empty">
                {t("outputsPage.empty")}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
