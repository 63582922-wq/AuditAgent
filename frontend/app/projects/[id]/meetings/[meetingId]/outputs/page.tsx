"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { ActionButton } from "@/components/ActionButton";
import { AgentBriefsPanel } from "@/components/AgentBriefsPanel";
import { useProjectLive } from "@/contexts/ProjectLiveContext";
import {
  OutputRecord,
  acceptMeetingDeliverables,
  downloadUrl,
  rejectMeetingDeliverables,
  api,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useDocumentVisible } from "@/lib/useDocumentVisible";
import { isPipelineRunning } from "@/lib/workflow";

const PRIMARY_OUTPUT_TYPES = new Set([
  "fixed_template_excel",
  "deliverable_package",
]);

const INTERNAL_OUTPUT_TYPES = new Set([
  "finding_pdf",
  "fixed_template_field_evidence",
  "fixed_template_quality",
  "fixed_template_quality_json",
  "finding_excel",
  "observation_summary",
  "evidence_index",
  "material_parse_index",
  "missing_docs",
  "correction_list",
  "risk_pdf",
  "risk_excel",
  "deliverable_readme",
  "annotated_excel",
  "annotated_image",
]);

function dedupeOutputs(items: OutputRecord[]): OutputRecord[] {
  const byFile = new Map<string, OutputRecord>();
  for (const o of items.filter((item) => !INTERNAL_OUTPUT_TYPES.has(item.output_type))) {
    if (!PRIMARY_OUTPUT_TYPES.has(o.output_type)) continue;
    const prev = byFile.get(o.file_name);
    if (!prev) {
      byFile.set(o.file_name, o);
      continue;
    }
    const preferFinding = (a: OutputRecord, b: OutputRecord) =>
      a.output_type.startsWith("finding_") ? a : b.output_type.startsWith("finding_") ? b : a;
    byFile.set(o.file_name, preferFinding(o, prev));
  }
  return Array.from(byFile.values());
}

function ownerLabel(owner?: string) {
  const labels: Record<string, string> = {
    system: "系统",
    observer: "观察员",
    pmo: "PMO",
    customer: "客户",
  };
  return labels[owner || ""] || owner || "未定";
}

function evidenceTypeLabel(type?: string) {
  const labels: Record<string, string> = {
    direct_material: "直接资料",
    derived_fact: "推导事实",
    rule_derived: "规则推导",
    indirect_or_low_confidence: "间接/低置信",
    missing_evidence: "缺证据",
    external_handoff: "外部补齐",
    template_structure: "模板结构",
  };
  return labels[type || ""] || type || "未定";
}

function evalValueLabel(value: unknown) {
  if (value === null || value === undefined || value === "") return "空";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

type EvaluationDiagnosisFile = {
  file_name?: string;
  output_type?: string;
};

type EvaluationDiagnosis = {
  root_cause?: string;
  remediation?: string;
  candidate_files?: EvaluationDiagnosisFile[];
  related_files?: EvaluationDiagnosisFile[];
  loose_outputs?: EvaluationDiagnosisFile[];
};

function diagnosisEvidenceLabel(diagnosis?: EvaluationDiagnosis) {
  if (!diagnosis) return "";
  const fileNames = [
    ...(diagnosis.candidate_files ?? []).map((item) => item.file_name),
    ...(diagnosis.related_files ?? []).map((item) => item.file_name),
    ...(diagnosis.loose_outputs ?? []).map((item) => item.file_name || item.output_type),
  ].filter(Boolean);
  return Array.from(new Set(fileNames)).slice(0, 4).join(" · ");
}

export default function MeetingOutputsPage() {
  const { id, meetingId } = useParams<{ id: string; meetingId: string }>();
  const { t, messages } = useI18n();
  const { live: project, job, refresh: refreshLive } = useProjectLive();
  const documentVisible = useDocumentVisible();
  const [outputs, setOutputs] = useState<OutputRecord[]>([]);
  const [rejectComment, setRejectComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const [actionMsgKind, setActionMsgKind] = useState<"danger" | "success">("danger");

  const outputLabel = (type: string) => messages.domain.outputType[type] || type;
  const running = isPipelineRunning(project?.status ?? "", job?.status);

  const refresh = useCallback(async () => {
    const outs = await api<OutputRecord[]>(`/projects/${id}/meetings/${meetingId}/outputs`);
    setOutputs(outs);
  }, [id, meetingId]);

  useEffect(() => {
    refresh().catch(console.error);
    if (!documentVisible || !running) return;
    const poll = setInterval(() => refresh().catch(console.error), 5000);
    return () => clearInterval(poll);
  }, [documentVisible, refresh, running]);

  const deliverable = project?.state_json?.deliverable;
  const templateQuality = deliverable?.template_quality;
  const complianceEvaluation = deliverable?.evaluation;
  const qualityCounts = templateQuality?.counts ?? {};
  const owner_counts = templateQuality?.owner_counts ?? {};
  const qualityComplete = (qualityCounts.complete ?? 0) + (qualityCounts.not_applicable ?? 0);
  const qualityMissing = (qualityCounts.missing ?? 0) + (qualityCounts.needs_review ?? 0);
  const qualityManual = (qualityCounts.manual_required ?? 0) + (qualityCounts.customer_required ?? 0);
  const qualityStatus = templateQuality?.status ?? "needs_review";
  const qualityStatusLabel =
    qualityStatus === "pass"
      ? t("outputsPage.qualityPass")
      : qualityStatus === "fail"
        ? t("outputsPage.qualityFail")
        : t("outputsPage.qualityNeedsReview");
  const qualityGenerated = templateQuality?.generated_at
    ? new Date(templateQuality.generated_at).toLocaleString()
    : "";
  const evaluationStatusLabel =
    complianceEvaluation?.status === "skipped"
      ? t("outputsPage.evaluationSkipped")
      : complianceEvaluation?.passed
        ? t("outputsPage.evaluationPass")
        : t("outputsPage.evaluationFail");
  const evaluationGenerated = complianceEvaluation?.generated_at
    ? new Date(complianceEvaluation.generated_at).toLocaleString()
    : "";
  const critic = project?.state_json?.runtime?.critic;
  const outputRank = (type: string) => {
    const order = [
      "fixed_template_excel",
      "deliverable_package",
    ];
    const idx = order.indexOf(type);
    return idx === -1 ? order.length : idx;
  };
  const visibleOutputs = dedupeOutputs(outputs).sort((a, b) => outputRank(a.output_type) - outputRank(b.output_type));
  const primaryDeliverable = visibleOutputs.find((o) => o.output_type === "fixed_template_excel");
  const archiveOutput = visibleOutputs.find((o) => o.output_type === "deliverable_package");
  const evidenceGate = deliverable?.evidence_gate ?? project?.state_json?.evidence_gate;
  const formalDeliveryBlocks = [
    evidenceGate?.blocked ? t("outputsPage.deliveryBlockEvidence") : "",
    deliverable?.evaluation_gate?.blocked ? t("outputsPage.deliveryBlockEvaluation") : "",
    deliverable?.template_gate?.blocked || qualityStatus !== "pass" ? t("outputsPage.deliveryBlockTemplate") : "",
    !primaryDeliverable || !archiveOutput ? t("outputsPage.deliveryBlockOutputs") : "",
  ].filter(Boolean);
  const formalAcceptanceGate = deliverable?.formal_acceptance_gate;
  const formalDeliveryBlocked = formalAcceptanceGate?.blocked ?? formalDeliveryBlocks.length > 0;
  const canReview =
    outputs.length > 0 &&
    ["completed", "needs_review", "deliverable_rejected"].includes(project?.status ?? "") &&
    deliverable?.status !== "accepted";

  async function onAccept() {
    setBusy(true);
    setActionMsg("");
    try {
      await acceptMeetingDeliverables(id, meetingId);
      await Promise.all([refresh(), refreshLive()]);
      setActionMsgKind("success");
      setActionMsg(t("outputsPage.accepted"));
    } catch (e) {
      setActionMsgKind("danger");
      setActionMsg(e instanceof Error ? e.message : t("outputsPage.acceptFail"));
    } finally {
      setBusy(false);
    }
  }

  async function onReject(reanalyze = false) {
    setBusy(true);
    setActionMsg("");
    try {
      await rejectMeetingDeliverables(id, meetingId, rejectComment, reanalyze);
      await Promise.all([refresh(), refreshLive()]);
      setActionMsgKind("success");
      setActionMsg(reanalyze ? t("outputsPage.rejectedReanalyze") : t("outputsPage.rejected"));
    } catch (e) {
      setActionMsgKind("danger");
      setActionMsg(e instanceof Error ? e.message : t("outputsPage.rejectFail"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTop title={t("outputsPage.title")} desc={t("outputsPage.desc")} />

      {actionMsg && <div className={`alert ${actionMsgKind}`}>{actionMsg}</div>}

      <AgentBriefsPanel state={project?.state_json} />

      {critic && (
        <Block title={messages.domain.criticAgent} hint={t("outputsPage.criticHint")}>
          <p className="muted" style={{ margin: 0, fontSize: "0.875rem", lineHeight: 1.6 }}>
            {t("outputsPage.criticValidated", { count: critic.validated ?? 0 })}
            {(critic.flagged ?? 0) > 0
              ? `${t("outputsPage.criticFlagged", { count: critic.flagged ?? 0 })}${
                  critic.readjudicate_rounds
                    ? t("outputsPage.criticRounds", { rounds: critic.readjudicate_rounds })
                    : ""
                }`
              : t("outputsPage.criticPassed")}
            {critic.outputs_regenerated ? t("outputsPage.criticRegen") : ""}
          </p>
        </Block>
      )}

      {deliverable?.status === "accepted" && (
        <Block className="settling-banner settling-banner--ok">{t("outputsPage.accepted")}</Block>
      )}
      {deliverable?.status === "rejected" && (
        <Block className="settling-banner settling-banner--warn">
          {deliverable.comment
            ? t("outputsPage.rejectedWith", { comment: deliverable.comment })
            : t("outputsPage.rejected")}
        </Block>
      )}
      {formalDeliveryBlocked && deliverable?.status !== "accepted" && (
        <Block className="settling-banner settling-banner--warn" title={t("outputsPage.deliveryBlockedTitle")} hint={t("outputsPage.deliveryBlockedHint")}>
          <p style={{ margin: 0 }}>{formalAcceptanceGate?.message || deliverable?.comment || formalDeliveryBlocks.join("；")}</p>
          <p className="muted" style={{ margin: "0.55rem 0 0" }}>{t("outputsPage.deliveryBlockedAction")}</p>
        </Block>
      )}

      {complianceEvaluation && (
        <Block
          className={`outputs-evaluation outputs-evaluation--${
            complianceEvaluation.status === "skipped"
              ? "skipped"
              : complianceEvaluation.passed
                ? "pass"
                : "fail"
          }`}
          title={t("outputsPage.evaluationTitle")}
          hint={t("outputsPage.evaluationHint")}
        >
          <div className="outputs-evaluation__summary">
            <strong>{evaluationStatusLabel}</strong>
            <span>
              {complianceEvaluation.case_id || complianceEvaluation.meeting_code || t("outputsPage.evaluationNoCase")}
            </span>
            {evaluationGenerated && <em>{t("outputsPage.evaluationGenerated", { time: evaluationGenerated })}</em>}
          </div>
          <div className="outputs-evaluation__metrics">
            <div>
              <label>{t("outputsPage.evaluationCase")}</label>
              <b>{complianceEvaluation.case_id || complianceEvaluation.reason || t("outputsPage.evaluationNoCase")}</b>
            </div>
            <div>
              <label>{t("outputsPage.evaluationChecks")}</label>
              <b>
                {complianceEvaluation.passed_checks ?? 0}/{complianceEvaluation.total_checks ?? 0}
              </b>
            </div>
            <div>
              <label>{t("outputsPage.evaluationCritical")}</label>
              <b>{complianceEvaluation.critical_failures ?? 0}</b>
            </div>
            <div>
              <label>{t("outputsPage.evaluationWarning")}</label>
              <b>{complianceEvaluation.warning_failures ?? 0}</b>
            </div>
          </div>
          {(complianceEvaluation.failed_checks ?? []).length > 0 ? (
            <div className="outputs-evaluation__issues">
              <span>{t("outputsPage.evaluationFailedChecks")}</span>
              <ol>
                {(complianceEvaluation.failed_checks ?? []).slice(0, 6).map((check) => {
                  const evidenceFiles = diagnosisEvidenceLabel(check.diagnosis);
                  return (
                    <li key={`${check.check_id}-${check.severity}`}>
                      <b>{check.check_id}</b>
                      <small>{check.message}</small>
                      <small>
                        {t("outputsPage.evaluationExpected")}: {evalValueLabel(check.expected)} ·{" "}
                        {t("outputsPage.evaluationActual")}: {evalValueLabel(check.actual)}
                      </small>
                      {check.diagnosis?.root_cause && (
                        <small>
                          {t("outputsPage.evaluationRootCause")}: {check.diagnosis.root_cause}
                        </small>
                      )}
                      {evidenceFiles && (
                        <small>
                          {t("outputsPage.evaluationEvidenceFiles")}: {evidenceFiles}
                        </small>
                      )}
                      {check.diagnosis?.remediation && (
                        <small>
                          {t("outputsPage.evaluationRemediation")}: {check.diagnosis.remediation}
                        </small>
                      )}
                    </li>
                  );
                })}
              </ol>
            </div>
          ) : (
            <p className="muted" style={{ margin: 0 }}>{t("outputsPage.evaluationNoIssues")}</p>
          )}
        </Block>
      )}

      {templateQuality && (
        <Block className={`outputs-quality outputs-quality--${qualityStatus}`} title={t("outputsPage.qualityTitle")} hint={t("outputsPage.qualityHint")}>
          <div className="outputs-quality__summary">
            <strong>{qualityStatusLabel}</strong>
            <span>
              {templateQuality.assessed_fields ?? 0}/{templateQuality.total_fields ?? 0}
            </span>
            {qualityGenerated && <em>{t("outputsPage.qualityGenerated", { time: qualityGenerated })}</em>}
          </div>
          <div className="outputs-quality__metrics">
            <div>
              <label>{t("outputsPage.qualityFields")}</label>
              <b>
                {templateQuality.assessed_fields ?? 0}/{templateQuality.total_fields ?? 0}
              </b>
            </div>
            <div>
              <label>{t("outputsPage.qualityComplete")}</label>
              <b>{qualityComplete}</b>
            </div>
            <div>
              <label>{t("outputsPage.qualityMissing")}</label>
              <b>{qualityMissing}</b>
            </div>
            <div>
              <label>{t("outputsPage.qualityManual")}</label>
              <b>{qualityManual}</b>
            </div>
            <div>
              <label>责任方</label>
              <b>
                系统 {owner_counts.system ?? 0} · 观察员 {owner_counts.observer ?? 0} · PMO {owner_counts.pmo ?? 0}
              </b>
            </div>
          </div>
          {(templateQuality.issue_fields ?? []).length > 0 ? (
            <div className="outputs-quality__issues">
              <span>{t("outputsPage.qualityIssues")}</span>
              <ol>
                {(templateQuality.issue_fields ?? []).slice(0, 6).map((issue) => (
                  <li key={`${issue.column}-${issue.header}`}>
                    <b>
                      {issue.column}. {issue.header}
                    </b>
                    <small>
                      责任方：{ownerLabel(issue.owner)} · 证据：{evidenceTypeLabel(issue.evidence_type)}
                      {issue.handoff_required ? " · 交付前处理" : ""}
                    </small>
                    <small>{issue.action || issue.issue || issue.quality}</small>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <p className="muted" style={{ margin: 0 }}>{t("outputsPage.qualityNoIssues")}</p>
          )}
        </Block>
      )}

      {canReview && (
        <Block>
          <p className="muted" style={{ marginBottom: "1rem" }}>
            {t("outputsPage.reviewHint")}
          </p>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
            <ActionButton onClick={onAccept} disabled={busy || formalDeliveryBlocked}>
              {t("outputsPage.accept")}
            </ActionButton>
            <input
              type="text"
              placeholder={t("outputsPage.rejectPlaceholder")}
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              className="input"
              style={{ minWidth: "16rem", flex: 1 }}
              disabled={busy}
            />
            <ActionButton variant="ghost" onClick={() => onReject(false)} disabled={busy}>
              {t("outputsPage.reject")}
            </ActionButton>
            <ActionButton variant="outline" onClick={() => onReject(true)} disabled={busy}>
              {t("outputsPage.rejectReanalyze")}
            </ActionButton>
          </div>
        </Block>
      )}

      {visibleOutputs.length > 0 ? (
        <div className="outputs-deliverable-grid" aria-label={t("outputsPage.title")}>
          {primaryDeliverable && (
            <section className="outputs-deliverable-card outputs-deliverable-card--primary">
              <span className="outputs-deliverable-card__eyebrow">{outputLabel(primaryDeliverable.output_type)}</span>
              <h2>{t("outputsPage.primaryTitle")}</h2>
              <p>{t("outputsPage.primaryDesc")}</p>
              <strong className="outputs-deliverable-card__file">{primaryDeliverable.file_name}</strong>
              <a href={downloadUrl(id, primaryDeliverable.id)} target="_blank" rel="noreferrer" className="btn">
                {t("outputsPage.download")}
              </a>
            </section>
          )}

          {archiveOutput && (
            <section className="outputs-deliverable-card">
              <span className="outputs-deliverable-card__eyebrow">{outputLabel(archiveOutput.output_type)}</span>
              <h2>{t("outputsPage.archiveTitle")}</h2>
              <p>{t("outputsPage.archiveDesc")}</p>
              <strong className="outputs-deliverable-card__file">{archiveOutput.file_name}</strong>
              <a href={downloadUrl(id, archiveOutput.id)} target="_blank" rel="noreferrer" className="btn-text">
                {t("outputsPage.downloadZip")}
              </a>
            </section>
          )}
        </div>
      ) : (
        <p className="empty">{t("outputsPage.empty")}</p>
      )}
    </>
  );
}
