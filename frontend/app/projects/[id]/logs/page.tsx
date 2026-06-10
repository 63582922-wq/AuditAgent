"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ActivityTimeline } from "@/components/ActivityTimeline";
import { PageTop } from "@/components/PageChrome";
import { api } from "@/lib/api";

type Log = {
  id: string;
  step: string;
  status: string;
  detail_json?: Record<string, unknown>;
  duration_ms?: number;
  created_at: string;
};

export default function ProjectLogsPage() {
  const { id } = useParams<{ id: string }>();
  const [logs, setLogs] = useState<Log[]>([]);

  useEffect(() => {
    api<Log[]>(`/projects/${id}/logs`).then(setLogs).catch(console.error);
    const t = setInterval(() => api<Log[]>(`/projects/${id}/logs`).then(setLogs).catch(console.error), 3000);
    return () => clearInterval(t);
  }, [id]);

  return (
    <>
      <PageTop title="Agent 日志" desc="Orchestrator、子 Agent 工具调用、Critic 与交付步骤记录" />
      <ActivityTimeline logs={logs} />
    </>
  );
}
