"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { Risk, api } from "@/lib/api";

export default function ProjectReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [risks, setRisks] = useState<Risk[]>([]);
  const [comment, setComment] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");

  function load() {
    api<Risk[]>(`/projects/${id}/risks`).then(setRisks).catch(console.error);
  }

  useEffect(() => {
    load();
  }, [id]);

  async function submitReview(riskId: string, status: string) {
    await api(`/projects/${id}/risks/${riskId}/review`, {
      method: "POST",
      body: JSON.stringify({ review_status: status, review_comment: comment[riskId] || "" }),
    });
    load();
  }

  async function regenerateReports() {
    try {
      await api(`/projects/${id}/regenerate-outputs`, { method: "POST" });
      setMsg("已重新生成，请到交付物页下载");
    } catch (e) {
      setMsg(String(e));
    }
  }

  const items = risks.filter((r) => r.manual_review_required || r.status === "pending");

  return (
    <>
      <PageTop
        title="复核"
        desc={`${items.length} 项待处理`}
        action={
          <button type="button" className="btn-outline" onClick={regenerateReports}>
            重新生成报告
          </button>
        }
      />

      {msg && <div className="alert success">{msg}</div>}

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
            placeholder="复核意见"
            value={comment[r.id] || ""}
            onChange={(e) => setComment({ ...comment, [r.id]: e.target.value })}
          />
          <div style={{ marginTop: "0.75rem", display: "flex", gap: "1rem" }}>
            <button type="button" className="btn-text" onClick={() => submitReview(r.id, "confirmed")}>
              确认
            </button>
            <button type="button" className="btn-text" onClick={() => submitReview(r.id, "dismissed")}>
              排除
            </button>
            <button type="button" className="btn-text" onClick={() => submitReview(r.id, "needs_more_info")}>
              需补充
            </button>
          </div>
        </Block>
      ))}

      {items.length === 0 && <p className="empty">无待复核项</p>}
    </>
  );
}
