import { ReactNode } from "react";

type PageTopProps = {
  title: string;
  desc?: string;
  action?: ReactNode;
  children?: ReactNode;
};

export function PageTop({ title, desc, action, children }: PageTopProps) {
  return (
    <header className="page-top">
      <div className="page-top__main">
        <h1>{title}</h1>
        {desc && <p>{desc}</p>}
      </div>
      {(action || children) && <div className="page-top__actions">{action || children}</div>}
    </header>
  );
}

type BlockProps = {
  title?: string;
  hint?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
};

export function Block({ title, hint, action, children }: BlockProps) {
  return (
    <section className="block">
      {(title || action) && (
        <div className="block-head">
          <div>
            {title && <h2>{title}</h2>}
            {hint && <p>{hint}</p>}
          </div>
          {action}
        </div>
      )}
      <div className="block-body">{children}</div>
    </section>
  );
}
