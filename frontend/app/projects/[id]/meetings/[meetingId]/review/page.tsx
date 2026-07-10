"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/** Legacy URL only. Review controls live in the consolidated audit conclusions workspace. */
export default function LegacyReviewRedirect() {
  const { id, meetingId } = useParams<{ id: string; meetingId: string }>();
  const router = useRouter();

  useEffect(() => {
    router.replace(`/projects/${id}/meetings/${meetingId}/risks`);
  }, [id, meetingId, router]);

  return null;
}
