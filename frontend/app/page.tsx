"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
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
        title="AuditAgent"
        desc="审计助手全流程作业 · 规则引擎与 Agent 协同"
        action={
          <Link href="/projects/new" className="btn">
            新建项目
          </Link>
        }
      />

      {agent && !agent.ready && <div className="alert danger">Agent 未就绪 · {agent.message}</div>}
      {agent?.ready && (
        <p className="status-line">
          <span className="status-line__dot" />
          {agent.text_model}
          {agent.vision_ready ? ` · ${agent.vision_model}` : ""}
        </p>
      )}

      <Block title="工作流程" hint="进入具体项目后，顶部 HUD 会显示真实进度">
        <p className="muted" style={{ marginBottom: "1rem" }}>
          创建项目 → 上传资料 → 点击「启动分析」→ 在风险 / 交付页查看结果
        </p>
        <Link href="/projects" className="btn btn--outline">
          查看全部项目
        </Link>
      </Block>

      {stats && (
        <>
          <div className="metrics">
            <div className="metric">
              <div className="metric__val">{stats.project_count}</div>
              <div className="metric__label">项目</div>
            </div>
            <div className="metric">
              <div className="metric__val">{stats.rule_count}</div>
              <div className="metric__label">规则</div>
            </div>
            <div className="metric">
              <div className="metric__val">{stats.risk_count}</div>
              <div className="metric__label">风险</div>
            </div>
            <div className="metric metric--high">
              <div className="metric__val">{stats.high_count}</div>
              <div className="metric__label">高</div>
            </div>
            <div className="metric metric--mid">
              <div className="metric__val">{stats.medium_count}</div>
              <div className="metric__label">中</div>
            </div>
            <div className="metric metric--low">
              <div className="metric__val">{stats.low_count}</div>
              <div className="metric__label">低</div>
            </div>
          </div>

          <Block title="交付物类型" hint="分析完成后自动生成">
            <p className="tag-row">
              {["PDF 报告", "风险清单", "批注 Excel", "影像标注", "缺件清单", "更正建议"].map((t) => (
                <span key={t} className="tag">
                  {t}
                </span>
              ))}
            </p>
          </Block>
        </>
      )}
    </>
  );
}
