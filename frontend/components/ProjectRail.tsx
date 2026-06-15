"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { useI18n } from "@/lib/i18n";
import { buildWorkflowSteps } from "@/lib/i18n/workflow-steps";
import { resolveMissionPhase } from "@/lib/mission";
import { isPipelineRunning, resolveLiveProgress } from "@/lib/workflow";

export function ProjectRail({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const { t, messages } = useI18n();
  const base = `/projects/${projectId}`;
  const meetingMatch = pathname.match(/^\/projects\/[^/]+\/meetings\/([^/]+)/);
  const meetingId = meetingMatch?.[1];
  const workBase = meetingId ? `${base}/meetings/${meetingId}` : base;
  const { live, job } = useProjectLiveOptional() ?? { live: null, job: null };

  const workflowSteps = buildWorkflowSteps(messages);
  const running = isPipelineRunning(live?.status ?? "", job?.status);
  const pct = live ? resolveLiveProgress(live, job, workflowSteps) : 0;
  const missionPhase = live ? resolveMissionPhase(live, job) : "init";
  const missionSteps = [
    { id: "init", num: "01", label: messages.mission.phases.init.short, href: "" },
    { id: "ingest", num: "02", label: messages.mission.phases.ingest.short, href: "/files" },
    { id: "processing", num: "03", label: messages.mission.phases.processing.short, href: "/risks" },
    { id: "deliver", num: "04", label: messages.mission.phases.deliver.short, href: "/outputs" },
  ] as const;
  const phaseIdx =
    missionPhase === "init"
      ? 0
      : missionPhase === "ingest"
        ? 1
        : missionPhase === "processing"
          ? 2
          : 3;

  const meetingCode =
    (live?.state_json as { meeting_case?: { meeting_code?: string } } | undefined)?.meeting_case?.meeting_code ||
    live?.name;

  const pages = [
    { suffix: "", label: t("rail.overview") },
    { suffix: "/files", label: t("rail.files") },
    { suffix: "/risks", label: t("rail.findings") },
    { suffix: "/outputs", label: t("rail.outputs") },
    { suffix: "/logs", label: t("rail.logs") },
    { suffix: "/review", label: t("rail.review") },
  ];

  return (
    <div className="rail">
      <nav className="rail-crumb" aria-label={t("rail.contextLabel")}>
        <Link href="/projects">{t("nav.projects")}</Link>
        <span className="rail-crumb__sep">/</span>
        {meetingId ? (
          <>
            <Link href={base} title={live?.name}>
              {live?.name || t("rail.projectScope")}
            </Link>
            <span className="rail-crumb__sep">/</span>
            <span className="rail-crumb__current" title={meetingCode}>
              {meetingCode || t("rail.meetingScope")}
            </span>
          </>
        ) : (
          <span className="rail-crumb__current">{live?.name || t("rail.projectScope")}</span>
        )}
      </nav>

      {!meetingId && <p className="rail-scope">{t("rail.projectScope")}</p>}

      {meetingId && (
        <>
          <ol className="rail-steps" aria-label={t("rail.workflow")}>
            {missionSteps.map((step, i) => {
              const state =
                missionPhase === "failed"
                  ? i <= phaseIdx
                    ? i === phaseIdx
                      ? "is-live"
                      : "is-done"
                    : ""
                  : i < phaseIdx
                    ? "is-done"
                    : i === phaseIdx
                      ? "is-live"
                      : "";
              const suffix =
                step.id === "ingest" && (live?.file_count ?? 0) > 0
                  ? ` · ${live?.file_count} ${t("meetingOverview.filesUnit")}`
                  : step.id === "processing" && running
                    ? ` · ${pct}%`
                    : "";
              return (
                <li key={step.id} className={state || undefined}>
                  <Link href={`${workBase}${step.href}`} className="rail-steps__link">
                    <span>{step.num}</span>
                    <span className="rail-steps__text">
                      {step.label}
                      {suffix}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ol>
        </>
      )}

      {meetingId ? (
        <nav className="rail-pages" aria-label={t("rail.meetingNav")}>
          {pages.map((p) => {
            const href = `${workBase}${p.suffix}`;
            const active =
              p.suffix === ""
                ? pathname === workBase
                : pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link key={p.suffix} href={href} className={`rail-pages__link${active ? " is-active" : ""}`}>
                {p.label}
              </Link>
            );
          })}
        </nav>
      ) : (
        <div className="rail-project-actions">
          <Link href={base} className={`rail-pages__link${pathname === base ? " is-active" : ""}`}>
            {t("nav.meetingList")}
          </Link>
        </div>
      )}
    </div>
  );
}
