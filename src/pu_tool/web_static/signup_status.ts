const PLAN_STATUS_LABELS: Record<string, string> = {
  scheduled: "等待执行",
  retrying: "等待重试",
  running: "正在报名",
  succeeded: "报名成功",
  failed: "报名失败",
  cancelled: "已取消",
};

const ATTEMPT_STATUS_LABELS: Record<string, string> = {
  pending: "等待执行",
  retrying: "准备重试",
  succeeded: "成功",
  failed: "失败",
  skipped: "已跳过",
};

export const planStatusLabel = (status: unknown) =>
  PLAN_STATUS_LABELS[String(status ?? "")] ?? String(status ?? "未知");

export const attemptStatusLabel = (status: unknown) =>
  ATTEMPT_STATUS_LABELS[String(status ?? "")] ?? String(status ?? "未知");

export const canCancelPlan = (status: unknown, enabled: unknown) =>
  Boolean(enabled) && (status === "scheduled" || status === "retrying");

export const planResultHref = (status: unknown) => {
  if (status === "succeeded") return "/reminders";
  if (status === "failed") return "/attempts";
  return null;
};
