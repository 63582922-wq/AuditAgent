"use client";

import { ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  AgentStatus,
  Job,
  ProjectLive,
  fetchLatestJob,
  fetchProjectLive,
  isNetworkError,
  isNotFoundError,
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
  notFound: boolean;
  error: string;
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
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState("");
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
          setNotFound(false);
          setError("");
        }
      } else if (isNotFoundError(liveResult.reason)) {
        setLive(null);
        setJob(null);
        setTraceLogs([]);
        setOffline(false);
        setNotFound(true);
        setError(liveResult.reason instanceof Error ? liveResult.reason.message : t("errors.notFound"));
      } else if (isNetworkError(liveResult.reason)) {
        setOffline(true);
      } else {
        setError(liveResult.reason instanceof Error ? liveResult.reason.message : String(liveResult.reason));
      }

      if (jobResult.status === "fulfilled") {
        nextJob = jobResult.value;
        setJob(nextJob);
      }

      const running = isPipelineRunning(nextLive?.status ?? "", nextJob?.status);
      if (running) setPendingRun(false);
      const boosted = Date.now() < boostUntil;
      if (includeLogs && nextLive) {
        try {
          const logPath = meetingId
            ? `/projects/${projectId}/meetings/${meetingId}/logs`
            : `/projects/${projectId}/logs`;
          const logs = await api<ActivityLog[]>(logPath, { cache: "no-store" });
          setTraceLogs(logs);
        } catch {
          /* logs optional */
        }
      } else if (!includeLogs || (!running && !boosted && !nextLive)) {
        setTraceLogs([]);
      }
    } finally {
      busyRef.current = false;
    }
  }, [boostUntil, includeLogs, meetingId, projectId, t]);

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
    <ProjectLiveContext.Provider value={{ live, job, agent, traceLogs, offline, notFound, error, pendingRun, refresh, watchRun }}>
      {offline && (
        <div className="alert danger" style={{ marginBottom: "1rem" }}>
          {t("common.offline")}
        </div>
      )}
      {notFound && (
        <div className="alert danger" style={{ marginBottom: "1rem" }}>
          {error ? `${t("errors.notFound")}：${error}` : t("errors.notFound")}
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
