"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Job, Project, api } from "@/lib/api";
import { WORKFLOW_STEPS, getStepStates, overallProgress } from "@/lib/workflow";

const PAGES = [
  { suffix: "", label: "概览" },
  { suffix: "/files", label: "资料" },
  { suffix: "/risks", label: "风险" },
  { suffix: "/review", label: "复核" },
  { suffix: "/outputs", label: "交付" },
  { suffix: "/logs", label: "日志" },
];

export function ProjectRail({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  const [project, setProject] = useState<Project | null>(null);
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    api<Project>(`/projects/${projectId}`).then(setProject).catch(console.error);
    api<Job>(`/projects/${projectId}/jobs/latest`)
      .then(setJob)
      .catch(() => setJob(null));
    const t = setInterval(() => {
      api<Project>(`/projects/${projectId}`).then(setProject).catch(console.error);
      api<Job>(`/projects/${projectId}/jobs/latest`)
        .then(setJob)
        .catch(() => setJob(null));
    }, 2500);
    return () => clearInterval(t);
  }, [projectId]);

  const status = project?.status ?? "created";
  const steps = getStepStates(status, job?.current_step, job?.status);
  const pct = overallProgress(status, job?.current_step, job?.progress_pct, job?.status);
  const activeStep = steps.find((s) => s.state === "active");

  return (
    <div className="rail">
      <Link href="/projects" className="rail-back">
        所有项目
      </Link>

      {project && (
        <p className="rail-project" title={project.name}>
          {project.name}
        </p>
      )}

      <div className="rail-progress">
        <div className="rail-progress__bar">
          <span style={{ width: `${pct}%` }} />
        </div>
        <span className="rail-progress__label">
          {pct}% · {activeStep?.step.short ?? "待启动"}
        </span>
      </div>

      <ol className="rail-flow">
        {WORKFLOW_STEPS.map((step, i) => {
          const { state } = steps[i];
          return (
            <li key={step.id} className={`rail-flow__item rail-flow__item--${state}`}>
              <span className="rail-flow__dot" />
              <span className="rail-flow__name">{step.short}</span>
            </li>
          );
        })}
      </ol>

      <div className="rail-divider" />

      <nav className="rail-pages">
        {PAGES.map((p) => {
          const href = `${base}${p.suffix}`;
          const active =
            p.suffix === "" ? pathname === base : pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link key={p.suffix} href={href} className={`rail-pages__link${active ? " is-active" : ""}`}>
              {p.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
