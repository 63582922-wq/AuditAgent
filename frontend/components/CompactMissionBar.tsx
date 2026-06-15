"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import { useI18n } from "@/lib/i18n";
import { localizeMissionGuide } from "@/lib/i18n/mission-i18n";
import { buildWorkflowSteps } from "@/lib/i18n/workflow-steps";
import { getStepStates, isPipelineRunning, resolveLiveProgress } from "@/lib/workflow";

function workBase(pathname: string, projectId: string): string {
  const m = pathname.match(new RegExp(`^/projects/${projectId}/meetings/([^/]+)`));
  return m ? `/projects/${projectId}/meetings/${m[1]}` : `/projects/${projectId}`;
}

export function CompactMissionBar() {
  const pathname = usePathname();
  const { live, job } = useProjectLive();
  const { t, messages } = useI18n();

  if (!live) return null;

  const meetingMatch = pathname.match(/^\/projects\/[^/]+\/meetings\/([^/]+)/);
  const projectId = live.id;
  const basePath = workBase(pathname, projectId);
  const workflowSteps = buildWorkflowSteps(messages);
  const guide = localizeMissionGuide(live, job, basePath, messages, t);
  const pct = resolveLiveProgress(live, job, workflowSteps);
  const steps = getStepStates(live.status, job?.current_step, job?.status, workflowSteps);
  const activeStep = steps.find((s) => s.state === "active");
  const running = isPipelineRunning(live.status, job?.status);

  return (
    <div className={`mission-strip${running ? " mission-strip--live" : ""}`}>
      <div className="mission-strip__main">
        <p className="mission-strip__headline">{guide.headline}</p>
        <p className="mission-strip__detail">{guide.detail}</p>
      </div>
      <div className="mission-strip__meta">
        {running && (
          <span className="mission-strip__live">
            <span className="mission-strip__dot" aria-hidden />
            {activeStep?.step.short ?? "—"} · {pct}%
          </span>
        )}
        {guide.action && (
          <Link href={guide.action.href} className="btn btn-sm btn-outline">
            {guide.action.label}
          </Link>
        )}
      </div>
      {running && (
        <div className="mission-strip__bar" aria-hidden>
          <span style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}
