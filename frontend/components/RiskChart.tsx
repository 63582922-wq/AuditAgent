"use client";

type Props = {
  high: number;
  medium: number;
  low: number;
  total?: number;
};

export function RiskChart({ high, medium, low, total }: Props) {
  const sum = total ?? high + medium + low;
  if (sum === 0) return <p className="muted">暂无数据</p>;

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
          <span className="risk-chart__label">项</span>
        </div>
      </div>
      <div className="risk-chart__legend">
        <div className="risk-chart__leg-item">
          <span className="risk-chart__swatch" style={{ background: "var(--risk-high)" }} />
          高 {high}
          <em>{((high / sum) * 100).toFixed(0)}%</em>
        </div>
        <div className="risk-chart__leg-item">
          <span className="risk-chart__swatch" style={{ background: "var(--risk-mid)" }} />
          中 {medium}
          <em>{((medium / sum) * 100).toFixed(0)}%</em>
        </div>
        <div className="risk-chart__leg-item">
          <span className="risk-chart__swatch" style={{ background: "var(--risk-low)" }} />
          低 {low}
          <em>{((low / sum) * 100).toFixed(0)}%</em>
        </div>
      </div>
    </div>
  );
}
