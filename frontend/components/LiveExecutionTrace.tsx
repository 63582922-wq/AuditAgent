"use client";

import { useEffect, useRef } from "react";
import {
  ActivityLog,
  pickRecentTraceLogs,
  traceLogTitle,
} from "@/components/ActivityTimeline";
import { useI18n } from "@/lib/i18n";
import { statusLabel } from "@/lib/i18n/workflow-steps";
import { formatTime } from "@/lib/format";

type Props = {
  logs: ActivityLog[];
  live?: boolean;
};

export function LiveExecutionTrace({ logs, live }: Props) {
  const { t, messages } = useI18n();
  const recent = pickRecentTraceLogs(logs, 12);
  const endRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    if (!live || !recent.length) return;
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [live, recent.length, recent[recent.length - 1]?.id]);

  if (!recent.length) {
    return (
      <p className="live-trace__empty">
        {live ? t("components.liveTrace.waitingLive") : t("components.liveTrace.waitingIdle")}
      </p>
    );
  }

  return (
    <ol className="live-trace" aria-label={t("components.liveTrace.aria")}>
      {recent.map((log, i) => {
        const active = live && i === recent.length - 1 && log.status === "running";
        const done = log.status === "completed";
        return (
          <li
            key={log.id}
            ref={i === recent.length - 1 ? endRef : undefined}
            className={`live-trace__item${active ? " live-trace__item--active" : ""}${done ? " live-trace__item--done" : ""}`}
          >
            <span className="live-trace__dot" aria-hidden />
            <div className="live-trace__body">
              <span className="live-trace__title">{traceLogTitle(log, t, messages)}</span>
              <span className="live-trace__status">{statusLabel(log.status, messages) || log.status}</span>
              <time className="live-trace__time">{formatTime(log.created_at)}</time>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
