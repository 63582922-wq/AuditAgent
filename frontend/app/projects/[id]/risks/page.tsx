"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { Risk, api } from "@/lib/api";

export default function ProjectRisksPage() {
  const { id } = useParams<{ id: string }>();
  const [risks, setRisks] = useState<Risk[]>([]);
  const [level, setLevel] = useState("");

  useEffect(() => {
    const path = level ? `/projects/${id}/risks?level=${encodeURIComponent(level)}` : `/projects/${id}/risks`;
    api<Risk[]>(path).then(setRisks).catch(console.error);
    const t = setInterval(() => api<Risk[]>(path).then(setRisks).catch(console.error), 4000);
    return () => clearInterval(t);
  }, [id, level]);

  return (
    <>
      <PageTop
        title="风险"
        desc={`${risks.length} 条记录`}
        action={
          <select className="input" style={{ width: 120 }} value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">全部</option>
            <option value="高">高</option>
            <option value="中">中</option>
            <option value="低">低</option>
          </select>
        }
      />

      <table className="data-table">
        <thead>
          <tr>
            <th>等级</th>
            <th>分</th>
            <th>类别</th>
            <th>问题</th>
            <th>建议</th>
            <th>复核</th>
          </tr>
        </thead>
        <tbody>
          {risks.map((r) => (
            <tr key={r.id}>
              <td>
                <span className={`badge ${r.risk_level === "高" ? "high" : r.risk_level === "中" ? "mid" : "low"}`}>
                  {r.risk_level}
                </span>
              </td>
              <td className="mono">{r.risk_score}</td>
              <td>{r.risk_category}</td>
              <td className="strong">{r.problem}</td>
              <td>{r.suggestion}</td>
              <td>{r.manual_review_required ? "是" : "—"}</td>
            </tr>
          ))}
          {risks.length === 0 && (
            <tr>
              <td colSpan={6} className="empty">
                暂无风险
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
