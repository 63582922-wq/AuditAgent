"use client";

import { useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { Rule, api } from "@/lib/api";

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [form, setForm] = useState({
    rule_id: "",
    rule_name: "",
    risk_category: "税务风险",
    risk_level: "中",
    applicable_document_type: "expense_detail",
    suggestion_template: "",
  });
  const [msg, setMsg] = useState("");

  function load() {
    api<Rule[]>("/rules").then(setRules).catch(console.error);
  }

  useEffect(() => {
    load();
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");
    try {
      await api("/rules", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          condition: { all: [{ field: "amount", operator: ">=", value: 10000 }] },
          evidence_fields: ["amount"],
          manual_review_required: true,
          priority: 80,
        }),
      });
      setMsg("已添加");
      load();
    } catch (err) {
      setMsg(String(err));
    }
  }

  async function toggleRule(ruleDbId: string) {
    await api(`/rules/${ruleDbId}/toggle`, { method: "PATCH" });
    load();
  }

  const enabled = rules.filter((r) => r.enabled).length;

  return (
    <>
      <PageTop title="规则库" desc={`${rules.length} 条 · 启用 ${enabled} 条`} />

      <Block title="新增规则">
        <form onSubmit={onSubmit} style={{ maxWidth: 480, display: "grid", gap: "0.75rem" }}>
          <input className="input" placeholder="规则 ID" value={form.rule_id} onChange={(e) => setForm({ ...form, rule_id: e.target.value })} required />
          <input className="input" placeholder="名称" value={form.rule_name} onChange={(e) => setForm({ ...form, rule_name: e.target.value })} required />
          <select className="input" value={form.applicable_document_type} onChange={(e) => setForm({ ...form, applicable_document_type: e.target.value })}>
            <option value="expense_detail">费用明细</option>
            <option value="invoice_list">发票清单</option>
            <option value="bank_statement">银行流水</option>
            <option value="contract">合同</option>
          </select>
          <textarea className="textarea" placeholder="建议模板" value={form.suggestion_template} onChange={(e) => setForm({ ...form, suggestion_template: e.target.value })} required />
          <button className="btn" style={{ justifySelf: "start" }}>
            添加
          </button>
          {msg && <p className="muted">{msg}</p>}
        </form>
      </Block>

      <table className="data-table">
        <thead>
          <tr>
            <th />
            <th>ID</th>
            <th>名称</th>
            <th>类别</th>
            <th>等级</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id} style={{ opacity: r.enabled ? 1 : 0.45 }}>
              <td>
                <button type="button" className="btn-text" onClick={() => toggleRule(r.id)}>
                  {r.enabled ? "开" : "关"}
                </button>
              </td>
              <td className="mono">{r.rule_id}</td>
              <td className="strong">{r.rule_name}</td>
              <td>{r.risk_category}</td>
              <td>{r.risk_level}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
