"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Block } from "@/components/PageChrome";
import { SettlingStage } from "@/components/SettlingStage";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import { useI18n } from "@/lib/i18n";
import { isPipelineRunning } from "@/lib/workflow";

export default function MeetingOverviewPage() {
  const { id, meetingId } = useParams<{ id: string; meetingId: string }>();
  const { t } = useI18n();
  const { live, job, pendingRun } = useProjectLive();
  const base = `/projects/${id}/meetings/${meetingId}`;
  const running = isPipelineRunning(live?.status ?? "", job?.status) || pendingRun;

  const links = [
    { href: "files", label: t("meetingOverview.linkFiles"), hideWhenRunning: true },
    { href: "risks", label: t("meetingOverview.linkFindings") },
    { href: "outputs", label: t("meetingOverview.linkOutputs") },
    { href: "logs", label: t("meetingOverview.linkLogs") },
    { href: "review", label: t("meetingOverview.linkReview") },
  ].filter((l) => !running || !l.hideWhenRunning);

  return (
    <>
      <SettlingStage basePath={base} />

      <Block title={t("meetingOverview.quickLinks")}>
        {running && (
          <p className="muted" style={{ margin: "0 0 1rem" }}>
            {t("meetingOverview.runningLinksHint")}
          </p>
        )}
        <nav className="quick-link-grid">
          {links.map((l) => (
            <Link key={l.href} href={`${base}/${l.href}`} className="quick-link-tile">
              <span className="quick-link-tile__label">{l.label}</span>
              <span className="quick-link-tile__arrow" aria-hidden>
                →
              </span>
            </Link>
          ))}
        </nav>
      </Block>
    </>
  );
}
