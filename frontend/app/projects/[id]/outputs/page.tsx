"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { OutputRecord, downloadUrl, api } from "@/lib/api";

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

  useEffect(() => {
    api<OutputRecord[]>(`/projects/${id}/outputs`).then(setOutputs).catch(console.error);
    const t = setInterval(() => api<OutputRecord[]>(`/projects/${id}/outputs`).then(setOutputs).catch(console.error), 4000);
    return () => clearInterval(t);
  }, [id]);

  return (
    <>
      <PageTop title="交付物" desc="分析完成后自动生成，点击下载。" />

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
