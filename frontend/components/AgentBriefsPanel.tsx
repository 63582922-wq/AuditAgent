"use client";

import { Block } from "@/components/PageChrome";
import { ProjectStateJson } from "@/lib/api";

type Props = {
  state?: ProjectStateJson | null;
};

const AGENT_LABEL: Record<string, string> = {
  tax: "税务专员",
  invoice: "票据专员",
  contract: "合同专员",
  treasury: "资金专员",
  ledger: "账务专员",
};

export function AgentBriefsPanel({ state }: Props) {
  const briefs = state?.sub_agent_briefs;
  const synthesis = state?.synthesis_brief;
  const keys = briefs ? Object.keys(briefs) : [];

  if (!keys.length && !synthesis?.summary) return null;

  return (
    <Block title="Agent 专员简报" hint={`${keys.length} 路子 Agent`}>
      {synthesis?.summary && (
        <div style={{ marginBottom: "1rem", paddingBottom: "1rem", borderBottom: "1px solid var(--line)" }}>
          <div className="muted" style={{ fontSize: "0.75rem", marginBottom: "0.35rem" }}>
            主 Agent 汇总
          </div>
          <p style={{ margin: 0, fontSize: "0.875rem", lineHeight: 1.6 }}>{synthesis.summary}</p>
        </div>
      )}

      <div style={{ display: "grid", gap: "0.75rem", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
        {keys.map((id) => {
          const b = briefs![id];
          return (
            <div
              key={id}
              style={{
                padding: "0.75rem",
                border: "1px solid var(--line)",
                borderRadius: "var(--radius-sm)",
                background: "var(--surface-2)",
              }}
            >
              <div className="muted" style={{ fontSize: "0.75rem", marginBottom: "0.35rem" }}>
                {AGENT_LABEL[id] || b?.title || id}
              </div>
              <p style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.55 }}>{b?.summary || "—"}</p>
              {b?.tools_used && b.tools_used.length > 0 && (
                <div className="muted" style={{ fontSize: "0.7rem", marginTop: "0.5rem" }}>
                  工具: {b.tools_used.join(", ")}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Block>
  );
}
