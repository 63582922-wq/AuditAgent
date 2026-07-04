"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Block, PageTop } from "@/components/PageChrome";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import { Risk, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function MeetingReviewPage() {
  const { id, meetingId } = useParams<{ id: string; meetingId: string }>();
  const { t } = useI18n();
  const { live, refresh: refreshLive } = useProjectLive();
  const [risks, setRisks] = useState<Risk[]>([]);
  const [comment, setComment] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [msgKind, setMsgKind] = useState<"danger" | "success">("success");
  const [busy, setBusy] = useState("");

  function load() {
    api<Risk[]>(`/projects/${id}/meetings/${meetingId}/risks`).then(setRisks).catch(console.error);
  }

  useEffect(() => {
    load();
  }, [id, meetingId]);

  async function submitReview(riskId: string, status: string) {
    const key = `review:${riskId}`;
    setBusy(key);
    setMsg("");
    try {
      await api(`/projects/${id}/risks/${riskId}/review`, {
        method: "POST",
        body: JSON.stringify({ review_status: status, review_comment: comment[riskId] || "" }),
      });
      setMsgKind("success");
      setMsg(t("reviewPage.saved"));
      await Promise.all([refreshLive(), api<Risk[]>(`/projects/${id}/meetings/${meetingId}/risks`).then(setRisks)]);
    } catch (e) {
      setMsgKind("danger");
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function regenerateReports() {
    setBusy("regenerate");
    setMsg("");
    try {
      await api(`/projects/${id}/meetings/${meetingId}/regenerate-outputs`, { method: "POST" });
      setMsgKind("success");
      setMsg(t("reviewPage.regenOk"));
      await refreshLive();
    } catch (e) {
      setMsgKind("danger");
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function reanalyze(scope: "adjudicating" | "cross_checking") {
    setBusy(scope);
    setMsg("");
    try {
      await api(`/projects/${id}/meetings/${meetingId}/reanalyze`, {
        method: "POST",
        body: JSON.stringify({ scope }),
      });
      setMsgKind("success");
      setMsg(scope === "adjudicating" ? t("reviewPage.startedAdj") : t("reviewPage.startedCross"));
      await refreshLive();
    } catch (e) {
      setMsgKind("danger");
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  const items = risks.filter((r) => r.manual_review_required || r.status === "pending");
  const gateReason = (
    live?.state_json?.runtime as { human_gate?: { reason?: string } } | undefined
  )?.human_gate?.reason;

  return (
    <>
      <PageTop
        title={t("reviewPage.title")}
        desc={t("reviewPage.desc")}
        action={
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <ActionButton
              variant="outline"
              loadingLabel={t("reviewPage.starting")}
              loading={busy === "adjudicating"}
              disabled={!!busy}
              onClick={() => reanalyze("adjudicating")}
            >
              {t("reviewPage.rerunAdjudicating")}
            </ActionButton>
            <ActionButton
              variant="outline"
              loadingLabel={t("reviewPage.starting")}
              loading={busy === "cross_checking"}
              disabled={!!busy}
              onClick={() => reanalyze("cross_checking")}
            >
              {t("reviewPage.rerunCross")}
            </ActionButton>
            <ActionButton
              variant="outline"
              loadingLabel={t("reviewPage.starting")}
              loading={busy === "regenerate"}
              disabled={!!busy}
              onClick={regenerateReports}
            >
              {t("reviewPage.regenReports")}
            </ActionButton>
          </div>
        }
      />

      {live?.status === "needs_review" && gateReason && (
        <div className="alert" style={{ marginBottom: "1rem" }}>
          {t("reviewPage.gatePaused", { reason: gateReason })}
        </div>
      )}

      {msg && <div className={`alert ${msgKind}`}>{msg}</div>}

      {items.map((r) => (
        <Block
          key={r.id}
          title={r.problem}
          hint={
            <>
              <span className={`badge ${r.risk_level === "高" ? "high" : r.risk_level === "中" ? "mid" : "low"}`}>
                {r.risk_level}
              </span>
              {" · "}
              {r.suggestion}
            </>
          }
        >
          {r.analysis && (
            <p style={{ fontSize: "0.8125rem", color: "var(--text-2)", margin: "0 0 1rem" }}>
              {r.analysis}
            </p>
          )}
          <textarea
            className="textarea"
            placeholder={t("reviewPage.commentPlaceholder")}
            value={comment[r.id] || ""}
            onChange={(e) => setComment({ ...comment, [r.id]: e.target.value })}
            disabled={!!busy}
          />
          <div style={{ marginTop: "0.75rem", display: "flex", gap: "1rem" }}>
            <button type="button" className="btn-text" onClick={() => submitReview(r.id, "confirmed")} disabled={!!busy}>
              {t("reviewPage.confirm")}
            </button>
            <button type="button" className="btn-text" onClick={() => submitReview(r.id, "dismissed")} disabled={!!busy}>
              {t("reviewPage.dismiss")}
            </button>
            <button type="button" className="btn-text" onClick={() => submitReview(r.id, "needs_more_info")} disabled={!!busy}>
              {t("reviewPage.needMore")}
            </button>
          </div>
        </Block>
      ))}

      {items.length === 0 && <p className="empty">{t("reviewPage.empty")}</p>}
    </>
  );
}
