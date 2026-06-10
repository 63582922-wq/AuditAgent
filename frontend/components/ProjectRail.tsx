"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import { WORKFLOW_STEPS, getStepStates, overallProgress } from "@/lib/workflow";
import { getMissionGuide } from "@/lib/mission";

const PAGES = [
  { suffix: "", label: "概览" },
  { suffix: "/files", label: "资料" },
  { suffix: "/risks", label: "风险" },
  { suffix: "/outputs", label: "验收" },
  { suffix: "/logs", label: "日志" },
  { suffix: "/review", label: "复核" },
];

export function ProjectRail({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  const { live, job } = useProjectLive();

  const status = live?.status ?? "created";
  const steps = getStepStates(status, job?.current_step, job?.status);
  const pct = overallProgress(status, job?.current_step, job?.progress_pct, job?.status);
  const activeStep = steps.find((s) => s.state === "active");
  const guide = live ? getMissionGuide(live, job, projectId) : null;

  return (
    <div className="rail">
      <Link href="/projects" className="rail-back">
        ← 所有项目
      </Link>

      {live && (
        <p className="rail-project" title={live.name}>
          {live.name}
        </p>
      )}

      {guide && (
        <div className={`rail-mission rail-mission--${guide.phase}`}>
          <span className="rail-mission__phase">{guide.phase.toUpperCase()}</span>
          <span className="rail-mission__pct">{guide.progress}%</span>
        </div>
      )}

      <div className="rail-progress">
        <div className="rail-progress__bar">
          <span style={{ width: `${pct}%` }} />
        </div>
        <span className="rail-progress__label">
          {pct}% · {activeStep ? activeStep.step.station : "待启动"}
        </span>
      </div>

      <ol className="rail-flow">
        {WORKFLOW_STEPS.map((step, i) => {
          const { state } = steps[i];
          return (
            <li key={step.id} className={`rail-flow__item rail-flow__item--${state}`} title={step.agentSay}>
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
