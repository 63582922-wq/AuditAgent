"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Job, Project, ProjectLive } from "@/lib/api";
import { MISSION_PHASES, MissionPhase, getMissionGuide } from "@/lib/mission";

const PHASE_TITLE: Record<MissionPhase, string> = {
  init: "等待上传资料",
  ingest: "资料已接入",
  processing: "Orchestrator 分析中",
  review: "待人工复核（可选）",
  deliver: "待验收交付物",
  failed: "分析中断",
};

type Props = {
  project: Project | ProjectLive;
  job?: Job | null;
};

export function MissionControl({ project, job }: Props) {
  const pathname = usePathname();
  const guide = getMissionGuide(project, job, project.id);
  const failed = guide.phase === "failed";
  const fileCount = "file_count" in project ? project.file_count : (project.files?.length ?? 0);
  const riskCount = "risk_count" in project ? project.risk_count : (project.risks?.length ?? 0);
  const onActionPage =
    guide.action &&
    (pathname === guide.action.href || pathname.startsWith(`${guide.action.href}/`));

  return (
    <section className={`mission-bar${guide.live ? " mission-bar--live" : ""}${failed ? " mission-bar--failed" : ""}`}>
      <nav className="mission-bar__phases" aria-label="项目阶段">
        {MISSION_PHASES.map((p, i) => {
          const done = i < guide.phaseIndex;
          const active = i === guide.phaseIndex;
          return (
            <div
              key={p.id}
              className={`mission-bar__phase${done ? " is-done" : ""}${active ? " is-active" : ""}`}
            >
              <span className="mission-bar__num">{p.icon}</span>
              <span className="mission-bar__name">{p.label}</span>
            </div>
          );
        })}
      </nav>

      <div className="mission-bar__body">
        <div className="mission-bar__info">
          <p className="mission-bar__agent-hint">
            <span className="mission-bar__agent-dot" aria-hidden />
            审计助手 · {PHASE_TITLE[guide.phase]}
          </p>
          <p className="mission-bar__desc">{guide.detail}</p>
        </div>
        <div className="mission-bar__right">
          <div className="mission-bar__stats">
            <span><em>{fileCount}</em> 文件</span>
            <span><em>{riskCount}</em> 风险</span>
            <span className="mission-bar__progress"><em>{guide.progress}</em>%</span>
          </div>
          {guide.action && !onActionPage && (
            <Link href={guide.action.href} className="btn btn-sm">
              {guide.action.label}
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}
