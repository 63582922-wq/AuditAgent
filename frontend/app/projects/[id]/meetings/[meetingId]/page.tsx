"use client";

import { useParams } from "next/navigation";
import { SettlingStage } from "@/components/SettlingStage";

export default function MeetingOverviewPage() {
  const { id, meetingId } = useParams<{ id: string; meetingId: string }>();
  const base = `/projects/${id}/meetings/${meetingId}`;

  return (
    <>
      <SettlingStage basePath={base} />
    </>
  );
}
