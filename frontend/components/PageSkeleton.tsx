export function PageSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="page-skeleton" aria-busy="true" aria-label="加载中">
      <div className="page-skeleton__bar" />
      <div className="page-skeleton__bar page-skeleton__bar--short" />
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="page-skeleton__block" />
      ))}
    </div>
  );
}

export function HudSkeleton() {
  return (
    <div className="hud-skeleton" aria-busy="true" aria-label="加载进度">
      <div className="hud-skeleton__phases">
        {Array.from({ length: 5 }, (_, i) => (
          <span key={i} className="hud-skeleton__phase" />
        ))}
      </div>
      <div className="hud-skeleton__body" />
    </div>
  );
}
