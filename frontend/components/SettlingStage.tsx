"use client";

import { LiveWorkflowGraph } from "@/components/LiveWorkflowGraph";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import { useI18n } from "@/lib/i18n";
import { localizeMissionGuide } from "@/lib/i18n/mission-i18n";
import { statusLabel } from "@/lib/i18n/workflow-steps";
import { isPipelineRunning } from "@/lib/workflow";

type Props = {
  basePath: string;
};

export function SettlingStage({ basePath }: Props) {
  const { live, job, pendingRun } = useProjectLive();
  const { t, messages } = useI18n();

  if (!live) {
    return (
      <section className="settling-stage settling-stage--loading" aria-busy="true">
        <p className="settling-stage__kicker">{t("common.loading")}</p>
        <div className="settling-stage__hero settling-stage__hero--ghost">
          <span aria-hidden>—</span>
          <em>%</em>
        </div>
      </section>
    );
  }

  const running = isPipelineRunning(live.status, job?.status);
  if (running || pendingRun) return null;

  const guide = localizeMissionGuide(live, job, basePath, messages, t);

  return (
    <section className="settling-stage">
      <p className="settling-stage__kicker">{statusLabel(live.status, messages)}</p>
      <h1 className="settling-stage__title">{guide.headline}</h1>
      <p className="settling-stage__desc">{guide.detail}</p>
      <div className="settling-stage__metrics">
        <div>
          <label>{t("meetingOverview.files")}</label>
          <b>{live.file_count ?? 0}</b>
        </div>
        <div>
          <label>{messages.domain.finding}</label>
          <b>{live.risk_count ?? 0}</b>
        </div>
        <div>
          <label>{t("meetingOverview.outputs")}</label>
          <b>{live.output_count ?? 0}</b>
        </div>
      </div>

      <LiveWorkflowGraph
        live={live}
        job={job}
        livePulse={isPipelineRunning(live.status, job?.status)}
        className="settling-stage__graph"
      />
    </section>
  );
}
