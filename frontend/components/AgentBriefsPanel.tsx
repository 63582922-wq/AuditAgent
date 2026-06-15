"use client";

import { Block } from "@/components/PageChrome";
import { ProjectStateJson } from "@/lib/api";
import { agentLabel } from "@/lib/domain";
import { useI18n } from "@/lib/i18n";

type Props = {
  state?: ProjectStateJson | null;
};

export function AgentBriefsPanel({ state }: Props) {
  const { t } = useI18n();
  const briefs = state?.sub_agent_briefs;
  const synthesis = state?.synthesis_brief;
  const registered = state?.mission?.registered_agents;
  const keys = briefs ? Object.keys(briefs) : [];

  if (!keys.length && !synthesis?.summary) return null;

  function labelFor(id: string, title?: string) {
    const reg = registered?.find((a) => a.id === id);
    return reg?.name || agentLabel(id, title);
  }

  return (
    <Block title={t("components.briefs.title")} hint={t("components.briefs.hint", { count: keys.length })}>
      {synthesis?.summary && (
        <div className="settling-briefs__synthesis">
          <div className="muted settling-briefs__label">{t("components.briefs.synthesis")}</div>
          <p className="settling-briefs__text">{synthesis.summary}</p>
        </div>
      )}

      <div className="settling-briefs__grid">
        {keys.map((id) => {
          const b = briefs![id];
          return (
            <div key={id} className="settling-brief-card">
              <div className="muted settling-briefs__label">{labelFor(id, b?.title)}</div>
              <p className="settling-briefs__text">{b?.summary || "—"}</p>
              {b?.tools_used && b.tools_used.length > 0 && (
                <div className="muted settling-briefs__tools">
                  {t("components.briefs.tools", { list: b.tools_used.join(", ") })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Block>
  );
}
