"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { PageTop } from "@/components/PageChrome";
import { Risk, api } from "@/lib/api";
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

  const running = isPipelineRunning(liveCtx?.live?.status ?? "", liveCtx?.job?.status);

  useEffect(() => {
    const base = `/projects/${id}/meetings/${meetingId}/risks`;
    const path = level ? `${base}?level=${encodeURIComponent(level)}` : base;
    api<Risk[]>(path).then(setRisks).catch(console.error);
    if (!documentVisible || !running) return;
    const poll = setInterval(() => api<Risk[]>(path).then(setRisks).catch(console.error), 5000);
    return () => clearInterval(poll);
  }, [documentVisible, id, level, meetingId, running]);

  const levelLabel = (l: string) => {
    if (l === "高") return t("findingsPage.levelHigh");
    if (l === "中") return t("findingsPage.levelMid");
    if (l === "低") return t("findingsPage.levelLow");
    return l;
  };

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
    </>
  );
}
