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

function codeLocationText(log: ActivityLog): string | null {
  const loc = log.detail_json?.code_location;
  if (!loc || typeof loc !== "object") return null;
  const detail = loc as { file?: unknown; line?: unknown; function?: unknown };
  const file = typeof detail.file === "string" ? detail.file : "";
  const line =
    typeof detail.line === "number" || typeof detail.line === "string"
      ? String(detail.line)
      : "";
  const fn = typeof detail.function === "string" ? detail.function : "";
  if (!file || !line) return null;
  return `${file}:${line}${fn ? ` · ${fn}()` : ""}`;
}

function logMessage(log: ActivityLog): string | null {
  const detail = log.detail_json || {};
  if (typeof detail.message === "string" && detail.message.trim()) return detail.message;
  if (typeof detail.error === "string" && detail.error.trim()) return detail.error;
  return null;
}

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
        const message = logMessage(log);
        const codeLocation = codeLocationText(log);
        return (
          <li
            key={log.id}
            ref={i === recent.length - 1 ? endRef : undefined}
            className={`live-trace__item${active ? " live-trace__item--active" : ""}${done ? " live-trace__item--done" : ""}`}
          >
            <span className="live-trace__dot" aria-hidden />
            <div className="live-trace__body">
              <span className="live-trace__title">{traceLogTitle(log, t, messages)}</span>
              {message && <span className="live-trace__message">{message}</span>}
              <span className="live-trace__status">{statusLabel(log.status, messages) || log.status}</span>
              <time className="live-trace__time">{formatTime(log.created_at)}</time>
              {codeLocation && <span className="live-trace__code">{codeLocation}</span>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
