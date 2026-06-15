"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { api, AgentStatus, Stats } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function HomePage() {
  const { t, messages } = useI18n();
  const [stats, setStats] = useState<Stats | null>(null);
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [agentLoading, setAgentLoading] = useState(true);
  const [agentError, setAgentError] = useState("");

  useEffect(() => {
    api<Stats>("/stats").then(setStats).catch(console.error);
    setAgentLoading(true);
    api<AgentStatus>("/agent/status")
      .then(setAgent)
      .catch((e) => setAgentError(e instanceof Error ? e.message : String(e)))
      .finally(() => setAgentLoading(false));
  }, []);

  return (
    <>
      <PageTop title={t("product.name")} desc={`${t("product.subtitle")} · ${t("home.desc")}`} />

      {agentLoading && (
        <p className="status-line muted">{t("common.loading")}…</p>
      )}
      {agentError && (
        <div className="alert danger">
          {t("common.offline")} · {agentError}
        </div>
      )}
      {agent && !agent.ready && (
        <div className="alert danger">
          {t("home.agentNotReady")} · {agent.message}
        </div>
      )}
      {agent?.ready && (
        <p className="status-line">
          <span className="status-line__dot" />
          {t("home.agentReady")}
        </p>
      )}

      <div className="home-entry">
        <Link href="/projects/new" className="home-entry__card">
          <span className="home-entry__num">01</span>
          <strong>{t("home.newProject")}</strong>
          <p>{t("home.entryNewDesc")}</p>
        </Link>
        <Link href="/projects" className="home-entry__card home-entry__card--alt">
          <span className="home-entry__num">02</span>
          <strong>{t("home.projectList")}</strong>
          <p>{t("home.entryListDesc")}</p>
        </Link>
      </div>

      <Block title={t("home.flowTitle")}>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          {t("home.flowDesc")}
        </p>
        <div className="home-flow">
          {messages.home.flowSteps.map((step, i) => (
            <div key={step} className="home-flow__step">
              <span className="home-flow__num">{String(i + 1).padStart(2, "0")}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
      </Block>

      {stats && (
        <>
          <div className="metrics">
            <div className="metric">
              <div className="metric__val">{stats.project_count}</div>
              <div className="metric__label">{t("home.statsProjects")}</div>
            </div>
            <div className="metric">
              <div className="metric__val">{stats.rule_count}</div>
              <div className="metric__label">{t("home.statsRules")}</div>
            </div>
            <div className="metric">
              <div className="metric__val">{stats.risk_count}</div>
              <div className="metric__label">{messages.domain.finding}</div>
            </div>
            <div className="metric metric--high">
              <div className="metric__val">{stats.high_count}</div>
              <div className="metric__label">{t("home.statsHigh")}</div>
            </div>
            <div className="metric metric--mid">
              <div className="metric__val">{stats.medium_count}</div>
              <div className="metric__label">{t("home.statsMid")}</div>
            </div>
            <div className="metric metric--low">
              <div className="metric__val">{stats.low_count}</div>
              <div className="metric__label">{t("home.statsLow")}</div>
            </div>
          </div>

          <Block title={t("home.deliverableTypes")} hint={t("home.deliverableHint")}>
            <p className="tag-row">
              {messages.home.deliverableList.map((label) => (
                <span key={label} className="tag">
                  {label}
                </span>
              ))}
            </p>
          </Block>
        </>
      )}
    </>
  );
}
