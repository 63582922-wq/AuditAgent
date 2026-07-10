"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ActivityTimeline } from "@/components/ActivityTimeline";
import { Block, PageTop } from "@/components/PageChrome";
import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { fetchMeetingRunEvents } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useDocumentVisible } from "@/lib/useDocumentVisible";
import { isPipelineRunning } from "@/lib/workflow";

type Log = {
  id: string;
  step: string;
  status: string;
  detail_json?: Record<string, unknown>;
  duration_ms?: number;
  created_at: string;
};

export default function MeetingLogsPage() {
  const { id, meetingId } = useParams<{ id: string; meetingId: string }>();
  const { t } = useI18n();
  const liveCtx = useProjectLiveOptional();
  const documentVisible = useDocumentVisible();
  const [logs, setLogs] = useState<Log[]>([]);

  const running = isPipelineRunning(liveCtx?.live?.status ?? "", liveCtx?.job?.status);

  useEffect(() => {
    const load = () => {
      void fetchMeetingRunEvents(id, meetingId)
        .then((snapshot) => {
          setLogs(
            snapshot.events.map((event) => ({
              id: event.id,
              step: event.step,
              status: event.status,
              detail_json: event.detail,
              duration_ms: event.duration_ms ?? undefined,
              created_at: event.created_at || new Date().toISOString(),
            })),
          );
        })
        .catch(console.error);
    };
    load();
    if (!documentVisible || !running) return;
    const poll = setInterval(load, 4000);
    return () => clearInterval(poll);
  }, [documentVisible, id, meetingId, running]);

  return (
    <>
      <PageTop title={t("logsPage.title")} desc={t("logsPage.desc")} />
      <Block title={t("hud.traceLabel")}>
        <ActivityTimeline logs={logs} />
      </Block>
    </>
  );
}
