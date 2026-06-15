"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Job, Project, ProjectLive } from "@/lib/api";
import { FxPanel } from "@/components/FxPanel";
import { useI18n } from "@/lib/i18n";
import { localizeMissionGuide, missionPhasesForUi } from "@/lib/i18n/mission-i18n";

type Props = {
  project: Project | ProjectLive;
  job?: Job | null;
};

function workBaseFrom(pathname: string, projectId: string): string {
  const m = pathname.match(new RegExp(`^/projects/${projectId}/meetings/([^/]+)`));
  return m ? `/projects/${projectId}/meetings/${m[1]}` : `/projects/${projectId}`;
}

export function MissionControl({ project, job }: Props) {
  const pathname = usePathname();
  const { t, messages } = useI18n();
  const basePath = workBaseFrom(pathname, project.id);
  const guide = localizeMissionGuide(project, job, basePath, messages, t);
  const phases = missionPhasesForUi(messages);
  const failed = guide.phase === "failed";
  const fileCount = "file_count" in project ? project.file_count : (project.files?.length ?? 0);
  const riskCount = "risk_count" in project ? project.risk_count : (project.risks?.length ?? 0);
  const onActionPage =
    guide.action &&
    (pathname === guide.action.href || pathname.startsWith(`${guide.action.href}/`));

  return (
    <FxPanel
      className={`mission${guide.live ? " mission--live" : ""}${failed ? " mission--failed" : ""}`}
      glow={guide.live}
    >
      <div className="mission__scanline" aria-hidden />
      <nav className="mission__phases" aria-label="Mission phases">
        {phases.map((p, i) => {
          const done = i < guide.phaseIndex;
          const active = i === guide.phaseIndex;
          const last = i === phases.length - 1;
          return (
            <div
              key={p.id}
              className={`mission-phase${done ? " mission-phase--done" : ""}${active ? " mission-phase--active" : ""}`}
            >
              <div className="mission-phase__node">
                {active && guide.live && <span className="mission-phase__burst" aria-hidden />}
                {active && guide.live && <span className="mission-phase__ring" aria-hidden />}
                <span className="mission-phase__icon">{p.icon}</span>
              </div>
              <span className="mission-phase__label">{p.short}</span>
              {!last && <span className="mission-phase__wire" aria-hidden />}
            </div>
          );
        })}
      </nav>

      <div className="mission__body">
        <div>
          <p className="mission__tag">
            {t("product.name")}
            {guide.live && <span className="mission__live-dot" aria-hidden />}
          </p>
          <h2 className="mission__headline">{guide.headline}</h2>
          <p className="mission__detail">{guide.detail}</p>
        </div>
        <div className="mission__actions">
          <div className="mission__stats">
            <span className="mission-stat">
              <em>{fileCount}</em>
              {t("hud.filesUnit")}
            </span>
            <span className="mission-stat">
              <em>{riskCount}</em>
              {messages.domain.finding}
            </span>
            <span className="mission-stat mission-stat--pct">
              <em>{guide.progress}</em>%
            </span>
          </div>
          {guide.action && !onActionPage && (
            <Link href={guide.action.href} className="btn btn-sm">
              {guide.action.label}
            </Link>
          )}
        </div>
      </div>
    </FxPanel>
  );
}
