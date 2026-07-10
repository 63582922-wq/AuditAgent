"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { ActionButton } from "@/components/ActionButton";
import { Block, PageTop } from "@/components/PageChrome";
import { fetchMeetingEvidence, MeetingEvidenceSnapshot, Risk, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useDocumentVisible } from "@/lib/useDocumentVisible";
import { isPipelineRunning } from "@/lib/workflow";

export default function MeetingRisksPage() {
  const { id, meetingId } = useParams<{ id: string; meetingId: string }>();
  const { t } = useI18n();
  const liveCtx = useProjectLiveOptional();
  const documentVisible = useDocumentVisible();
  const [risks, setRisks] = useState<Risk[]>([]);
  const [level, setLevel] = useState("");
  const [evidence, setEvidence] = useState<MeetingEvidenceSnapshot | null>(null);
  const [comment, setComment] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"danger" | "success">("success");

  const running = isPipelineRunning(liveCtx?.live?.status ?? "", liveCtx?.job?.status);

  useEffect(() => {
    const base = `/projects/${id}/meetings/${meetingId}/risks`;
    const path = level ? `${base}?level=${encodeURIComponent(level)}` : base;
    const load = () => {
      void api<Risk[]>(path).then(setRisks).catch(console.error);
      void fetchMeetingEvidence(id, meetingId).then(setEvidence).catch(console.error);
    };
    load();
    if (!documentVisible || !running) return;
    const poll = setInterval(load, 5000);
    return () => clearInterval(poll);
  }, [documentVisible, id, level, meetingId, running]);

  const levelLabel = (l: string) => {
    if (l === "高") return t("findingsPage.levelHigh");
    if (l === "中") return t("findingsPage.levelMid");
    if (l === "低") return t("findingsPage.levelLow");
    return l;
  };

  const ruleOutcomes = liveCtx?.live?.state_json?.rule_outcomes ?? [];
  const outcomeCounts = ruleOutcomes.reduce<Record<string, number>>((counts, item) => {
    const status = item.status || "needs_review";
    counts[status] = (counts[status] || 0) + 1;
    return counts;
  }, {});
  const outcomeLabel = (status: string) => {
    if (status === "passed") return t("findingsPage.rulePassed");
    if (status === "finding") return t("findingsPage.ruleFinding");
    if (status === "not_applicable") return t("findingsPage.ruleNotApplicable");
    return t("findingsPage.ruleNeedsReview");
  };
  const evidenceStatus = (status: string) => {
    if (status === "accepted") return t("findingsPage.rulePassed");
    if (status === "conflict") return t("findingsPage.ruleNeedsReview");
    return t("findingsPage.ruleNeedsReview");
  };
  const reviewItems = risks.filter((risk) => risk.manual_review_required || risk.status === "pending");

  async function submitReview(riskId: string, status: "confirmed" | "dismissed" | "needs_more_info") {
    setBusy(`review:${riskId}`);
    setMessage("");
    try {
      await api(`/projects/${id}/risks/${riskId}/review`, {
        method: "POST",
        body: JSON.stringify({ review_status: status, review_comment: comment[riskId] || "" }),
      });
      setMessageKind("success");
      setMessage(t("reviewPage.saved"));
      liveCtx?.refresh();
      const next = await api<Risk[]>(`/projects/${id}/meetings/${meetingId}/risks`);
      setRisks(next);
    } catch (error) {
      setMessageKind("danger");
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy("");
    }
  }

  async function rerun(scope: "adjudicating" | "cross_checking") {
    if (!window.confirm(scope === "adjudicating" ? t("reviewPage.rerunAdjudicating") : t("reviewPage.rerunCross"))) return;
    setBusy(scope);
    setMessage("");
    try {
      await api(`/projects/${id}/meetings/${meetingId}/reanalyze`, {
        method: "POST",
        body: JSON.stringify({ scope }),
      });
      setMessageKind("success");
      setMessage(scope === "adjudicating" ? t("reviewPage.startedAdj") : t("reviewPage.startedCross"));
      liveCtx?.refresh();
    } catch (error) {
      setMessageKind("danger");
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy("");
    }
  }

  async function regenerateReports() {
    if (!window.confirm(t("reviewPage.regenReports"))) return;
    setBusy("regenerate");
    setMessage("");
    try {
      await api(`/projects/${id}/meetings/${meetingId}/regenerate-outputs`, { method: "POST" });
      setMessageKind("success");
      setMessage(t("reviewPage.regenOk"));
      liveCtx?.refresh();
    } catch (error) {
      setMessageKind("danger");
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageTop
        title={t("findingsPage.title")}
        desc={t("findingsPage.desc", { count: risks.length })}
        action={
          <select className="input" style={{ width: 120 }} value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">{t("findingsPage.filterAll")}</option>
            <option value="高">{t("findingsPage.levelHigh")}</option>
            <option value="中">{t("findingsPage.levelMid")}</option>
            <option value="低">{t("findingsPage.levelLow")}</option>
          </select>
        }
      />

      <Block title={t("findingsPage.auditSummary")} hint={t("findingsPage.auditSummaryHint")}>
        <div className="audit-status-grid">
          {(["passed", "finding", "needs_review", "not_applicable"] as const).map((status) => (
            <div key={status} className={`audit-status-grid__item audit-status-grid__item--${status}`}>
              <span>{outcomeLabel(status)}</span>
              <strong className="mono">{outcomeCounts[status] || 0}</strong>
            </div>
          ))}
        </div>
        {evidence?.run_id && (
          <p className={`audit-gate${evidence.gate.blocked ? " audit-gate--blocked" : ""}`}>
            {evidence.gate.blocked ? t("findingsPage.evidenceGateBlocked") : t("findingsPage.evidenceGateReady")}
          </p>
        )}
      </Block>

      {message && <div className={`alert ${messageKind}`}>{message}</div>}

      <table className="data-table">
        <thead>
          <tr>
            <th>{t("findingsPage.colLevel")}</th>
            <th>{t("findingsPage.colScore")}</th>
            <th>{t("findingsPage.colCategory")}</th>
            <th>{t("findingsPage.colCheck")}</th>
            <th>{t("findingsPage.colFinding")}</th>
            <th>{t("findingsPage.colReview")}</th>
          </tr>
        </thead>
        <tbody>
          {risks.map((r) => (
            <tr key={r.id}>
              <td>
                <span className={`badge ${r.risk_level === "高" ? "high" : r.risk_level === "中" ? "mid" : "low"}`}>
                  {levelLabel(r.risk_level)}
                </span>
              </td>
              <td className="mono">{r.risk_score}</td>
              <td>{r.risk_category}</td>
              <td className="strong">{r.problem}</td>
              <td>{r.analysis || r.suggestion}</td>
              <td>{r.manual_review_required ? t("findingsPage.yes") : "—"}</td>
            </tr>
          ))}
          {risks.length === 0 && (
            <tr>
              <td colSpan={6} className="empty">
                {t("findingsPage.empty")}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {!!evidence?.facts.length && (
        <Block title={t("findingsPage.factLedger")}>
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("findingsPage.fact")}</th>
                <th>{t("findingsPage.value")}</th>
                <th>{t("findingsPage.evidenceStatus")}</th>
                <th>{t("findingsPage.confidence")}</th>
              </tr>
            </thead>
            <tbody>
              {evidence.facts.map((fact) => (
                <tr key={fact.fact_key}>
                  <td className="strong">{fact.fact_key}</td>
                  <td>{fact.value === null || fact.value === undefined || fact.value === "" ? "—" : String(fact.value)}</td>
                  <td>
                    <span className={`badge ${fact.status === "accepted" ? "low" : fact.status === "conflict" ? "high" : "mid"}`}>
                      {evidenceStatus(fact.status)}
                    </span>
                  </td>
                  <td className="mono">{Math.round((fact.confidence || 0) * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Block>
      )}

      <Block title={t("reviewPage.title")} hint={t("reviewPage.desc")}>
        <div className="audit-review-actions">
          <ActionButton
            variant="outline"
            loading={busy === "adjudicating"}
            loadingLabel={t("reviewPage.starting")}
            disabled={!!busy}
            onClick={() => rerun("adjudicating")}
          >
            {t("reviewPage.rerunAdjudicating")}
          </ActionButton>
          <ActionButton
            variant="outline"
            loading={busy === "cross_checking"}
            loadingLabel={t("reviewPage.starting")}
            disabled={!!busy}
            onClick={() => rerun("cross_checking")}
          >
            {t("reviewPage.rerunCross")}
          </ActionButton>
          <ActionButton
            variant="outline"
            loading={busy === "regenerate"}
            loadingLabel={t("reviewPage.starting")}
            disabled={!!busy}
            onClick={regenerateReports}
          >
            {t("reviewPage.regenReports")}
          </ActionButton>
        </div>

        {reviewItems.map((risk) => (
          <section key={risk.id} className="audit-review-item">
            <div>
              <strong>{risk.problem}</strong>
              <p>{risk.analysis || risk.suggestion}</p>
            </div>
            <textarea
              className="textarea"
              placeholder={t("reviewPage.commentPlaceholder")}
              value={comment[risk.id] || ""}
              onChange={(event) => setComment((current) => ({ ...current, [risk.id]: event.target.value }))}
              disabled={!!busy}
            />
            <div className="audit-review-actions">
              <button type="button" className="btn-text" disabled={!!busy} onClick={() => void submitReview(risk.id, "confirmed")}>{t("reviewPage.confirm")}</button>
              <button type="button" className="btn-text" disabled={!!busy} onClick={() => void submitReview(risk.id, "dismissed")}>{t("reviewPage.dismiss")}</button>
              <button type="button" className="btn-text" disabled={!!busy} onClick={() => void submitReview(risk.id, "needs_more_info")}>{t("reviewPage.needMore")}</button>
            </div>
          </section>
        ))}
        {!reviewItems.length && <p className="empty">{t("reviewPage.empty")}</p>}
      </Block>
    </>
  );
}
