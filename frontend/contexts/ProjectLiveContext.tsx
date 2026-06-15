"use client";

import { ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  AgentStatus,
  Job,
  ProjectLive,
  fetchLatestJob,
  fetchProjectLive,
  isNetworkError,
  api,
} from "@/lib/api";
import { ActivityLog } from "@/components/ActivityTimeline";
import { isPipelineRunning } from "@/lib/workflow";
import { useI18n } from "@/lib/i18n";

type Ctx = {
  live: ProjectLive | null;
  job: Job | null;
  agent: AgentStatus | null;
  traceLogs: ActivityLog[];
  offline: boolean;
  pendingRun: boolean;
  refresh: () => void;
  watchRun: () => void;
};

const ProjectLiveContext = createContext<Ctx | null>(null);

export function ProjectLiveProvider({
  projectId,
  meetingId,
  includeLogs = false,
  includeAgent = false,
  children,
}: {
  projectId: string;
  meetingId?: string;
  includeLogs?: boolean;
  includeAgent?: boolean;
  children: ReactNode;
}) {
  const [live, setLive] = useState<ProjectLive | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [traceLogs, setTraceLogs] = useState<ActivityLog[]>([]);
  const [offline, setOffline] = useState(false);
  const [boostUntil, setBoostUntil] = useState(0);
  const [pendingRun, setPendingRun] = useState(false);
  const { t } = useI18n();
  const busyRef = useRef(false);

  const watchRun = useCallback(() => {
    setBoostUntil(Date.now() + 45000);
    setPendingRun(true);
  }, []);

  const refresh = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    try {
      const [liveResult, jobResult] = await Promise.allSettled([
        fetchProjectLive(projectId, meetingId),
        fetchLatestJob(projectId, meetingId),
      ]);

      let nextLive: ProjectLive | null = null;
      let nextJob: Job | null = null;

      if (liveResult.status === "fulfilled") {
        nextLive = liveResult.value;
        if (nextLive) {
          setLive(nextLive);
          setOffline(false);
        }
      } else if (isNetworkError(liveResult.reason)) {
        setOffline(true);
      }

      if (jobResult.status === "fulfilled") {
        nextJob = jobResult.value;
        setJob(nextJob);
      }

      const running = isPipelineRunning(nextLive?.status ?? "", nextJob?.status);
      if (running) setPendingRun(false);
      const boosted = Date.now() < boostUntil;
      if (includeLogs && (running || boosted)) {
        try {
          const logPath = meetingId
            ? `/projects/${projectId}/meetings/${meetingId}/logs`
            : `/projects/${projectId}/logs`;
          const logs = await api<ActivityLog[]>(logPath, { cache: "no-store" });
          setTraceLogs(logs);
        } catch {
          /* logs optional */
        }
      } else if (!running && !boosted) {
        setTraceLogs([]);
      }
    } finally {
      busyRef.current = false;
    }
  }, [boostUntil, includeLogs, meetingId, projectId]);

  useEffect(() => {
    refresh();
    if (!includeAgent) {
      setAgent(null);
      return;
    }
    api<AgentStatus>("/agent/status", { cache: "no-store" })
      .then((a) => {
        setAgent(a);
        setOffline(false);
      })
      .catch((e) => {
        if (isNetworkError(e)) setOffline(true);
      });
  }, [includeAgent, refresh]);

  useEffect(() => {
    const running = isPipelineRunning(live?.status ?? "", job?.status);
    const boosted = Date.now() < boostUntil;
    const ms = offline ? 8000 : boosted ? 800 : running ? 1200 : 10000;
    const timer = setInterval(refresh, ms);
    return () => clearInterval(timer);
  }, [refresh, job?.status, job?.progress_pct, live?.status, offline, boostUntil]);

  useEffect(() => {
    if (Date.now() >= boostUntil) return;
    const burst = setInterval(refresh, 600);
    return () => clearInterval(burst);
  }, [boostUntil, refresh]);

  return (
    <ProjectLiveContext.Provider value={{ live, job, agent, traceLogs, offline, pendingRun, refresh, watchRun }}>
      {offline && (
        <div className="alert danger" style={{ marginBottom: "1rem" }}>
          {t("common.offline")}
        </div>
      )}
      {children}
    </ProjectLiveContext.Provider>
  );
}

export function useProjectLive() {
  const ctx = useContext(ProjectLiveContext);
  if (!ctx) throw new Error("useProjectLive must be used within ProjectLiveProvider");
  return ctx;
}

export function useProjectLiveOptional() {
  return useContext(ProjectLiveContext);
}
