"use client";

type Props = {
  /** 子会议页启用轻量流线背景 */
  animated?: boolean;
};

export function TechBackdrop({ animated = false }: Props) {
  return (
    <div className={`tech-backdrop${animated ? " tech-backdrop--live" : ""}`} aria-hidden>
      <div className="tech-backdrop__grid" />
      {animated && (
        <div className="tech-backdrop__flow">
          <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="flow-line" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(77,184,217,0)" />
                <stop offset="50%" stopColor="rgba(77,184,217,0.35)" />
                <stop offset="100%" stopColor="rgba(77,184,217,0)" />
              </linearGradient>
            </defs>
            <path
              d="M-80 420 Q360 380 720 400 T1520 380"
              fill="none"
              stroke="url(#flow-line)"
              strokeWidth="1"
              opacity="0.6"
            >
              <animate attributeName="d" dur="18s" repeatCount="indefinite"
                values="M-80 420 Q360 380 720 400 T1520 380;M-80 400 Q360 440 720 420 T1520 400;M-80 420 Q360 380 720 400 T1520 380" />
            </path>
            <path
              d="M-60 520 Q400 480 800 510 T1540 490"
              fill="none"
              stroke="url(#flow-line)"
              strokeWidth="0.75"
              opacity="0.35"
            >
              <animate attributeName="d" dur="24s" repeatCount="indefinite"
                values="M-60 520 Q400 480 800 510 T1540 490;M-60 500 Q400 540 800 520 T1540 510;M-60 520 Q400 480 800 510 T1540 490" />
            </path>
          </svg>
        </div>
      )}
    </div>
  );
}
