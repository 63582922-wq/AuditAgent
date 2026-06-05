"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CyberWorkflow } from "@/components/CyberWorkflow";
import { Block, PageTop } from "@/components/PageChrome";
import { AgentStatus, Stats, api } from "@/lib/api";

export default function HomePage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [agent, setAgent] = useState<AgentStatus | null>(null);

  useEffect(() => {
    api<Stats>("/stats").then(setStats).catch(console.error);
    api<AgentStatus>("/agent/status").then(setAgent).catch(console.error);
  }, []);

  return (
    <>
      <PageTop
        title="FXPG · AGENT"
        desc="会计风险评估神经链路 · 全流程可视化追踪"
        action={
          <Link href="/projects/new" className="btn">
            初始化项目
          </Link>
        }
      />

      <CyberWorkflow status="adjudicating" jobStep="adjudicating" jobPct={67} jobStatus="running" demo />

      {agent && !agent.ready && (
        <div className="alert danger">LINK DOWN · {agent.message}</div>
      )}

      {agent?.ready && (
        <p className="muted" style={{ margin: "-1rem 0 1.5rem", fontFamily: "var(--mono)", fontSize: "0.75rem" }}>
          UPLINK OK · {agent.text_model}
          {agent.vision_ready ? ` · ${agent.vision_model}` : ""}
        </p>
      )}

      {stats && (
        <>
          <div className="metrics">
            <div className="metric">
              <div className="metric__val">{stats.project_count}</div>
              <div className="metric__label">Projects</div>
            </div>
            <div className="metric">
              <div className="metric__val">{stats.rule_count}</div>
              <div className="metric__label">Rules</div>
            </div>
            <div className="metric">
              <div className="metric__val">{stats.risk_count}</div>
              <div className="metric__label">Risks</div>
            </div>
            <div className="metric metric--high">
              <div className="metric__val">{stats.high_count}</div>
              <div className="metric__label">Critical</div>
            </div>
            <div className="metric metric--mid">
              <div className="metric__val">{stats.medium_count}</div>
              <div className="metric__label">Warning</div>
            </div>
            <div className="metric metric--low">
              <div className="metric__val">{stats.low_count}</div>
              <div className="metric__label">Info</div>
            </div>
          </div>

          <Block title="Output Matrix" hint="分析完成后自动写入">
            <p className="muted" style={{ fontFamily: "var(--mono)", fontSize: "0.75rem", lineHeight: 1.9 }}>
              PDF_REPORT · XLS_RISK · XLS_ANNOT · IMG_MARK · DOC_MISSING · DOC_CORRECTION
            </p>
          </Block>
        </>
      )}
    </>
  );
}
