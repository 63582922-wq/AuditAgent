"use client";

import { useI18n } from "@/lib/i18n";

type Props = {
  high: number;
  medium: number;
  low: number;
  total?: number;
};

export function RiskChart({ high, medium, low, total }: Props) {
  const { t } = useI18n();
  const sum = total ?? high + medium + low;
  if (sum === 0) return <p className="muted">{t("common.empty")}</p>;

  const hPct = (high / sum) * 100;
  const mPct = (medium / sum) * 100;
  const gradient = `conic-gradient(
    var(--risk-high) 0 ${hPct}%,
    var(--risk-mid) ${hPct}% ${hPct + mPct}%,
    var(--risk-low) ${hPct + mPct}% 100%
  )`;

  return (
    <div className="risk-chart">
      <div className="risk-chart__ring" style={{ background: gradient }}>
        <div className="risk-chart__center">
          <span className="risk-chart__total">{sum}</span>
          <span className="risk-chart__label">{t("components.riskChart.unit")}</span>
        </div>
      </div>
      <div className="risk-chart__legend">
        <div className="risk-chart__leg-item">
          <span className="risk-chart__swatch" style={{ background: "var(--risk-high)" }} />
          {t("components.riskChart.high")} {high}
          <em>{((high / sum) * 100).toFixed(0)}%</em>
        </div>
        <div className="risk-chart__leg-item">
          <span className="risk-chart__swatch" style={{ background: "var(--risk-mid)" }} />
          {t("components.riskChart.medium")} {medium}
          <em>{((medium / sum) * 100).toFixed(0)}%</em>
        </div>
        <div className="risk-chart__leg-item">
          <span className="risk-chart__swatch" style={{ background: "var(--risk-low)" }} />
          {t("components.riskChart.low")} {low}
          <em>{((low / sum) * 100).toFixed(0)}%</em>
        </div>
      </div>
    </div>
  );
}
