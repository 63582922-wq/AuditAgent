"use client";

import { useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { Rule, api } from "@/lib/api";
import { COMPLIANCE_RULE_CATEGORIES } from "@/lib/domain";
import { useI18n } from "@/lib/i18n";

const DOC_TYPES = [
  "meeting_metadata",
  "a1_meeting_export",
  "observation_confirmation",
  "sign_in_record",
  "meeting_agenda",
  "coordination_sms",
  "meeting_screenshot",
  "presentation_material",
] as const;

export default function RulesPage() {
  const { t, messages } = useI18n();
  const docLabel = (v: string) => messages.domain.docCategory[v] || v;
  const [rules, setRules] = useState<Rule[]>([]);
  const [form, setForm] = useState({
    rule_id: "",
    rule_name: "",
    risk_category: COMPLIANCE_RULE_CATEGORIES[0],
    risk_level: "中",
    applicable_document_type: "observation_confirmation",
    suggestion_template: "",
  });
  const [msg, setMsg] = useState("");
  const [formError, setFormError] = useState("");

  function load() {
    api<Rule[]>("/rules").then(setRules).catch(console.error);
  }

  useEffect(() => {
    load();
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");
    setFormError("");
    if (!form.rule_id.trim() || !form.rule_name.trim() || !form.suggestion_template.trim()) {
      setFormError(t("common.fillRequired"));
      return;
    }
    try {
      await api("/rules", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          condition: { all: [{ field: "speaker_service_minutes", operator: "<", value: 15 }] },
          evidence_fields: ["speaker_service_minutes"],
          manual_review_required: false,
          priority: 80,
        }),
      });
      setMsg(t("settings.added"));
      load();
    } catch (err) {
      setMsg(String(err));
    }
  }

  async function toggleRule(ruleDbId: string) {
    await api(`/rules/${ruleDbId}/toggle`, { method: "PATCH" });
    load();
  }

  const cmpRules = rules.filter((r) => r.rule_id.startsWith("CMP-"));
  const enabled = rules.filter((r) => r.enabled).length;

  return (
    <>
      <PageTop
        title={t("settings.rulesPageTitle")}
        desc={t("settings.rulesPageDesc", { total: rules.length, enabled, cmp: cmpRules.length })}
      />

      <Block title={t("settings.addRule")}>
        <form noValidate onSubmit={onSubmit} style={{ maxWidth: 480, display: "grid", gap: "0.75rem" }}>
          <input
            className="input"
            placeholder={t("settings.ruleIdPlaceholder")}
            value={form.rule_id}
            onChange={(e) => setForm({ ...form, rule_id: e.target.value })}
          />
          <input
            className="input"
            placeholder={t("settings.ruleNamePlaceholder")}
            value={form.rule_name}
            onChange={(e) => setForm({ ...form, rule_name: e.target.value })}
          />
          <select className="input" value={form.risk_category} onChange={(e) => setForm({ ...form, risk_category: e.target.value })}>
            {COMPLIANCE_RULE_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            className="input"
            value={form.applicable_document_type}
            onChange={(e) => setForm({ ...form, applicable_document_type: e.target.value })}
          >
            {DOC_TYPES.map((d) => (
              <option key={d} value={d}>
                {docLabel(d)}
              </option>
            ))}
          </select>
          <textarea
            className="textarea"
            placeholder={t("settings.suggestionPlaceholder")}
            value={form.suggestion_template}
            onChange={(e) => setForm({ ...form, suggestion_template: e.target.value })}
          />
          <button type="submit" className="btn" style={{ justifySelf: "start" }}>
            {t("settings.add")}
          </button>
          {formError && <p className="form-hint">{formError}</p>}
          {msg && <p className="muted">{msg}</p>}
        </form>
      </Block>

      <table className="data-table">
        <thead>
          <tr>
            <th />
            <th>{t("settings.colId")}</th>
            <th>{t("settings.colRule")}</th>
            <th>{t("settings.colCategory")}</th>
            <th>{t("settings.colLevel")}</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id} style={{ opacity: r.enabled ? 1 : 0.45 }}>
              <td>
                <button type="button" className="btn-text" onClick={() => toggleRule(r.id)}>
                  {r.enabled ? t("settings.toggleOn") : t("settings.toggleOff")}
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
