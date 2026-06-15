/** 会议合规远程观察 — 前端展示常量（与后端 agent_domain=compliance 对齐） */

export const PRODUCT_NAME = "AuditAgent";
export const PRODUCT_SUBTITLE = "会议合规远程观察";
export const CRITIC_AGENT_NAME = "审核校验 Agent";
export const FINDING = "Finding";

export const DOCUMENT_CATEGORY_LABELS: Record<string, string> = {
  meeting_metadata: "观察元数据",
  finding_template: "Finding 模板",
  a1_meeting_export: "A1 会议导出",
  meeting_agenda: "会议议程",
  sign_in_record: "签到记录",
  observation_confirmation: "现场确认单",
  coordination_sms: "沟通短信",
  meeting_screenshot: "线上截图",
  presentation_material: "演讲材料",
  speaker_profile: "讲者资料",
  unknown: "未识别",
};

export const COMPLIANCE_AGENT_LABELS: Record<string, string> = {
  meeting_plan: "会议计划专员",
  attendance: "签到与会专员",
  speaker: "讲者核验专员",
  evidence: "证据链专员",
  policy: "合规政策专员",
  vision_agent: "视觉 Agent",
  main: "主 Agent",
};

export const COMPLIANCE_RULE_CATEGORIES = [
  "违反公司制度",
  "计划不一致",
  "未成功观察",
  "参会人身份不符",
];

export const COMPLIANCE_DOC_TYPES = [
  { value: "meeting_metadata", label: "观察元数据" },
  { value: "a1_meeting_export", label: "A1 会议导出" },
  { value: "observation_confirmation", label: "现场确认单" },
  { value: "sign_in_record", label: "签到记录" },
  { value: "meeting_agenda", label: "会议议程" },
  { value: "coordination_sms", label: "沟通短信" },
  { value: "meeting_screenshot", label: "线上截图" },
  { value: "presentation_material", label: "演讲材料" },
];

export const OUTPUT_TYPE_LABELS: Record<string, string> = {
  risk_excel: "Excel Finding 清单",
  risk_pdf: "PDF Finding 报告",
  annotated_excel: "批注 Excel",
  annotated_image: "标注图片",
  correction_list: "整改跟踪表",
  missing_docs: "缺件清单",
  finding_excel: "Excel Finding 清单",
  finding_pdf: "PDF Finding 报告",
  observation_summary: "观察摘要（PDF）",
  evidence_index: "证据索引（Excel）",
  material_parse_index: "资料解析索引（Excel）",
  deliverable_readme: "交付说明（PDF）",
  deliverable_package: "交付物归档包（ZIP）",
};

export const DEFAULT_CASE_PATH =
  process.env.NEXT_PUBLIC_DEFAULT_CASE_PATH || "";

export const PARSE_STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传",
  done: "已解析",
  pending: "待解析",
  failed: "解析失败",
};

export const COMPLIANCE_DELIVERABLE_LABELS = [
  "PDF Finding 报告",
  "Excel Finding 清单",
  "观察摘要 PDF",
  "证据索引 Excel",
  "资料解析索引 Excel",
  "OCR Markdown / 版面 JSON",
  "缺件清单 Excel",
  "整改跟踪表 Excel",
  "交付物 ZIP 包",
] as const;

export function formatParseStatus(status: string): string {
  return PARSE_STATUS_LABELS[status] || status;
}

export function formatDocumentCategory(category: string): string {
  return DOCUMENT_CATEGORY_LABELS[category] || category;
}

export function agentLabel(id: string, fallback?: string): string {
  return COMPLIANCE_AGENT_LABELS[id] || fallback || id;
}
