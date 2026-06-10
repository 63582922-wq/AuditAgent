"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Block, PageTop } from "@/components/PageChrome";
import { Project, Risk, api } from "@/lib/api";

export default function ProjectReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [risks, setRisks] = useState<Risk[]>([]);
  const [comment, setComment] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");

  function load() {
    api<Project>(`/projects/${id}`).then(setProject).catch(console.error);
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
    setMsg("复核已保存，结论已写入 Agent 记忆");
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

  async function reanalyze(scope: "adjudicating" | "cross_checking") {
    setBusy(scope);
    try {
      await api(`/projects/${id}/reanalyze`, {
        method: "POST",
        body: JSON.stringify({ scope }),
      });
      setMsg(scope === "adjudicating" ? "已启动研判重跑" : "已启动交叉比对 + 研判重跑");
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy("");
    }
  }

  const items = risks.filter((r) => r.manual_review_required || r.status === "pending");
  const gateReason = (
    project?.state_json?.runtime as { human_gate?: { reason?: string } } | undefined
  )?.human_gate?.reason;

  return (
    <>
      <PageTop
        title="逐条复核（可选）"
        desc="默认流程在「交付验收」页确认 PDF/Excel 即可。此处仅在你需要逐条确认/排除风险时使用。"
        action={
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <ActionButton
              variant="outline"
              loadingLabel="启动中…"
              loading={busy === "adjudicating"}
              disabled={!!busy}
              onClick={() => reanalyze("adjudicating")}
            >
              重跑研判
            </ActionButton>
            <ActionButton
              variant="outline"
              loadingLabel="启动中…"
              loading={busy === "cross_checking"}
              disabled={!!busy}
              onClick={() => reanalyze("cross_checking")}
            >
              重跑交叉比对
            </ActionButton>
            <ActionButton variant="outline" onClick={regenerateReports}>
              重新生成报告
            </ActionButton>
          </div>
        }
      />

      {project?.status === "needs_review" && gateReason && (
        <div className="alert" style={{ marginBottom: "1rem" }}>
          Agent 已暂停自动完成：{gateReason}
        </div>
      )}

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
