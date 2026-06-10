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

type Ctx = {
  live: ProjectLive | null;
  job: Job | null;
  agent: AgentStatus | null;
  offline: boolean;
  refresh: () => void;
};

const ProjectLiveContext = createContext<Ctx | null>(null);

export function ProjectLiveProvider({ projectId, children }: { projectId: string; children: ReactNode }) {
  const [live, setLive] = useState<ProjectLive | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [offline, setOffline] = useState(false);
  const busyRef = useRef(false);

  const refresh = useCallback(() => {
    if (busyRef.current) return;
    busyRef.current = true;
    Promise.all([
      fetchProjectLive(projectId)
        .then((data) => {
          if (data) {
            setLive(data);
            setOffline(false);
          }
        })
        .catch((e) => {
          if (isNetworkError(e)) setOffline(true);
        }),
      fetchLatestJob(projectId).then(setJob),
    ]).finally(() => {
      busyRef.current = false;
    });
  }, [projectId]);

  useEffect(() => {
    refresh();
    api<AgentStatus>("/agent/status")
      .then((a) => {
        setAgent(a);
        setOffline(false);
      })
      .catch((e) => {
        if (isNetworkError(e)) setOffline(true);
      });
  }, [refresh]);

  useEffect(() => {
    const ms = offline ? 8000 : job?.status === "running" ? 2000 : 5000;
    const t = setInterval(refresh, ms);
    return () => clearInterval(t);
  }, [refresh, job?.status, offline]);

  return (
    <ProjectLiveContext.Provider value={{ live, job, agent, offline, refresh }}>
      {offline && (
        <div className="alert danger" style={{ marginBottom: "1rem" }}>
          无法连接后端（8000 端口）· 请在终端运行：cd backend && source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000
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
