"use client";

import { useI18n } from "@/lib/i18n";

export function PageSkeleton({ lines = 3 }: { lines?: number }) {
  const { t } = useI18n();
  return (
    <div className="page-skeleton" aria-busy="true" aria-label={t("common.loading")}>
      <div className="page-skeleton__bar" />
      <div className="page-skeleton__bar page-skeleton__bar--short" />
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="page-skeleton__block" />
      ))}
    </div>
  );
}

export function HudSkeleton() {
  const { t } = useI18n();
  return (
    <div className="hud-skeleton" aria-busy="true" aria-label={t("common.loading")}>
      <div className="hud-skeleton__phases">
        {Array.from({ length: 5 }, (_, i) => (
          <span key={i} className="hud-skeleton__phase" />
        ))}
      </div>
      <div className="hud-skeleton__body" />
    </div>
  );
}
