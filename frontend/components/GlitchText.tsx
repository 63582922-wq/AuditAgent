import { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  as?: "span" | "h1" | "h2" | "h3";
};

export function GlitchText({ children, className = "", as: Tag = "span" }: Props) {
  const text = String(children);
  return (
    <Tag className={`glitch ${className}`} data-text={text}>
      {text}
    </Tag>
  );
}
