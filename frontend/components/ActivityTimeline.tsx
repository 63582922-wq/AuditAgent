"use client";

import { STATUS_LABEL } from "@/lib/workflow";

export type ActivityLog = {
  id: string;
  step: string;
  status: string;
  detail_json?: Record<string, unknown>;
  duration_ms?: number;
  created_at: string;
};

export function ActivityTimeline({ logs }: { logs: ActivityLog[] }) {
  if (!logs.length) {
    return <p className="timeline-empty">执行分析后，步骤耗时与详情将在此记录</p>;
  }

  const sorted = [...logs].reverse();

  return (
    <div className="timeline">
      {sorted.map((log) => (
        <div className="timeline__item" key={log.id}>
          <time className="timeline__time">{new Date(log.created_at).toLocaleTimeString("zh-CN")}</time>
          <div>
            <div className="timeline__title">{STATUS_LABEL[log.step] || log.step}</div>
            <div className="timeline__meta">
              <span>{log.status}</span>
              {log.duration_ms != null && <span>{log.duration_ms} ms</span>}
            </div>
            {log.detail_json && Object.keys(log.detail_json).length > 0 && (
              <pre className="timeline__detail">{JSON.stringify(log.detail_json, null, 2)}</pre>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
