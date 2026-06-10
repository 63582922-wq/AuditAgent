import { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  glow?: boolean;
};

/** 赛博面板：切角 + 动态边框 + 角标 */
export function FxPanel({ children, className = "", glow }: Props) {
  return (
    <div className={`fx-panel${glow ? " fx-panel--glow" : ""} ${className}`.trim()}>
      <span className="fx-panel__corner fx-panel__corner--tl" aria-hidden />
      <span className="fx-panel__corner fx-panel__corner--tr" aria-hidden />
      <span className="fx-panel__corner fx-panel__corner--bl" aria-hidden />
      <span className="fx-panel__corner fx-panel__corner--br" aria-hidden />
      <div className="fx-panel__inner">{children}</div>
    </div>
  );
}
