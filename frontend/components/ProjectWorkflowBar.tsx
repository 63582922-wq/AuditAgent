"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CyberWorkflow } from "@/components/CyberWorkflow";
import { Job, Project, api } from "@/lib/api";

export function ProjectWorkflowBar() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    if (!id) return;
    const load = () => {
      api<Project>(`/projects/${id}`).then(setProject).catch(console.error);
      api<Job>(`/projects/${id}/jobs/latest`)
        .then(setJob)
        .catch(() => setJob(null));
    };
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [id]);

  if (!project) return null;

  return (
    <CyberWorkflow
      status={project.status}
      jobStep={job?.current_step}
      jobPct={job?.progress_pct}
      jobStatus={job?.status}
    />
  );
}
