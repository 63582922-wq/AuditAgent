"use client";

import { ReactNode } from "react";
import { MeetingRunStage } from "@/components/MeetingRunStage";
import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { isPipelineRunning } from "@/lib/workflow";

/** 子会议路由壳：运行中展示沉降风格实时进度 */
export function MeetingWorkShell({ children }: { children: ReactNode }) {
  const ctx = useProjectLiveOptional();
  const running =
    Boolean(ctx?.pendingRun) ||
    isPipelineRunning(ctx?.live?.status ?? "", ctx?.job?.status);

  return (
    <div className={running ? "meeting-work-shell is-running" : "meeting-work-shell"}>
      <MeetingRunStage />
      {children}
    </div>
  );
}
