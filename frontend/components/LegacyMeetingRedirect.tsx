"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { fetchMeetings } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** 旧项目级路径重定向到首个子会议对应页面 */
export function LegacyMeetingRedirect({ suffix = "" }: { suffix?: string }) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useI18n();
  const [error, setError] = useState("");

  useEffect(() => {
    fetchMeetings(id)
      .then((meetings) => {
        if (meetings[0]) router.replace(`/projects/${id}/meetings/${meetings[0].id}${suffix}`);
        else router.replace(`/projects/${id}`);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        router.replace(`/projects/${id}`);
      });
  }, [id, router, suffix]);

  return (
    <p className="loading" style={{ padding: "2rem 0" }}>
      {error ? `${t("common.actionFailed")} · ${error}` : t("common.redirecting")}
    </p>
  );
}
