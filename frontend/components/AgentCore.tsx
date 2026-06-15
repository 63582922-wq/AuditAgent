"use client";

type Mode = "rest" | "idle" | "working" | "done" | "failed";

type Props = {
  mode: Mode;
  pct?: number;
};

export function AgentCore({ mode, pct = 0 }: Props) {
  const ringOffset = 113 * (1 - Math.min(100, Math.max(0, pct)) / 100);

  return (
    <div className={`agent-core agent-core--${mode}`} aria-hidden>
      <svg viewBox="0 0 88 88" className="agent-core__ring">
        <defs>
          <linearGradient id="streamline-ring-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--accent)" />
            <stop offset="100%" stopColor="var(--purple)" />
          </linearGradient>
        </defs>
        <circle cx="44" cy="44" r="36" className="agent-core__ring-bg" />
        <circle
          cx="44"
          cy="44"
          r="36"
          className="agent-core__ring-fill"
          style={{ strokeDasharray: 226, strokeDashoffset: ringOffset }}
        />
      </svg>
      <div className="agent-core__hex">
        <span className="agent-core__core" />
      </div>
      {mode === "working" && <span className="agent-core__sweep" />}
    </div>
  );
}
