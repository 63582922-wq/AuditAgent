/**
 * 将后端错误码映射为当前 locale 的 i18n 文案。
 * 后端 FXPGError 携带稳定 code 字段（如 PROJECT_NOT_FOUND），避免与文案耦合。
 */
const API_ERROR_KEYS: Record<string, string> = {
  PROJECT_NOT_FOUND: "errors.projectNotFound",
  MEETING_NOT_FOUND: "errors.meetingNotFound",
  RISK_NOT_FOUND: "errors.riskNotFound",
  RULE_NOT_FOUND: "errors.ruleNotFound",
  MEMORY_NOT_FOUND: "errors.memoryNotFound",
  OUTPUT_NOT_FOUND: "errors.outputNotFound",
  JOB_NOT_FOUND: "errors.jobNotFound",
  NOT_FOUND: "errors.notFound",
};

export function formatApiError(
  raw: string,
  t: (key: string) => string,
  code?: string | null,
): string {
  if (code && API_ERROR_KEYS[code]) {
    return t(API_ERROR_KEYS[code]);
  }
  // 回退：兼容历史纯文案响应（当后端尚未提供 code 字段时）
  const legacyKey = API_ERROR_KEYS[raw.trim()];
  return legacyKey ? t(legacyKey) : raw;
}
