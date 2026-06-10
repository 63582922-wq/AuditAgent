"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { ActionButton } from "@/components/ActionButton";
import { AgentBriefsPanel } from "@/components/AgentBriefsPanel";
import {
  OutputRecord,
  ProjectLive,
  acceptDeliverables,
  downloadUrl,
  fetchProjectLive,
  rejectDeliverables,
  api,
} from "@/lib/api";

const LABEL: Record<string, string> = {
  risk_excel: "Excel 风险清单",
  risk_pdf: "PDF 风险报告",
  annotated_excel: "批注 Excel",
  annotated_image: "标注图片",
  correction_list: "更正建议清单",
  missing_docs: "补充资料清单",
};

export default function ProjectOutputsPage() {
  const { id } = useParams<{ id: string }>();
  const [outputs, setOutputs] = useState<OutputRecord[]>([]);
  const [project, setProject] = useState<ProjectLive | null>(null);
  const [rejectComment, setRejectComment] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [outs, live] = await Promise.all([
      api<OutputRecord[]>(`/projects/${id}/outputs`),
      fetchProjectLive(id),
    ]);
    setOutputs(outs);
    setProject(live);
  }, [id]);

  useEffect(() => {
    refresh().catch(console.error);
    const t = setInterval(() => refresh().catch(console.error), 4000);
    return () => clearInterval(t);
  }, [refresh]);

  const deliverable = project?.state_json?.deliverable;
  const canReview =
    outputs.length > 0 &&
    (project?.status === "completed" || project?.status === "needs_review") &&
    deliverable?.status !== "accepted";

  async function onAccept() {
    setBusy(true);
    try {
      await acceptDeliverables(id);
      await refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
    }
  }

  async function onReject(reanalyze = false) {
    setBusy(true);
    try {
      await rejectDeliverables(id, rejectComment, reanalyze);
      await refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTop
        title="交付验收"
        desc="Orchestrator 分析完成后自动生成 PDF/Excel。请下载查阅后在下方验收；专员简报见概览页。"
      />

      <AgentBriefsPanel state={project?.state_json} />

      {deliverable?.status === "accepted" && (
        <Block className="fx-banner fx-banner--ok">验收已通过</Block>
      )}
      {deliverable?.status === "rejected" && (
        <Block className="fx-banner fx-banner--warn">
          已退回{deliverable.comment ? `：${deliverable.comment}` : ""}
        </Block>
      )}

      {canReview && (
        <Block>
          <p className="muted" style={{ marginBottom: "1rem" }}>
            请下载并查阅交付物。确认无误后点击验收；如需调整请退回并说明原因。
          </p>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
            <ActionButton onClick={onAccept} disabled={busy}>
              验收通过
            </ActionButton>
            <input
              type="text"
              placeholder="退回原因（可选）"
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              className="fx-input"
              style={{ minWidth: "16rem", flex: 1 }}
            />
            <ActionButton variant="ghost" onClick={() => onReject(false)} disabled={busy}>
              退回
            </ActionButton>
            <ActionButton variant="outline" onClick={() => onReject(true)} disabled={busy}>
              退回并重新分析
            </ActionButton>
          </div>
        </Block>
      )}

      <table className="data-table">
        <thead>
          <tr>
            <th>类型</th>
            <th>文件</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {outputs.map((o) => (
            <tr key={o.id}>
              <td>{LABEL[o.output_type] || o.output_type}</td>
              <td className="strong">{o.file_name}</td>
              <td style={{ textAlign: "right" }}>
                <a href={downloadUrl(id, o.id)} target="_blank" rel="noreferrer" className="btn-text">
                  下载
                </a>
              </td>
            </tr>
          ))}
          {outputs.length === 0 && (
            <tr>
              <td colSpan={3} className="empty">
                尚未生成
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
