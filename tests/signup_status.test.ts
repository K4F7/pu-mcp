import { describe, expect, test } from "bun:test";
import {
  attemptStatusLabel,
  canCancelPlan,
  planResultHref,
  planStatusLabel,
} from "../src/pu_tool/web_static/signup_status";

describe("signup status presentation", () => {
  test("translates plan and attempt statuses", () => {
    expect(planStatusLabel("scheduled")).toBe("等待执行");
    expect(planStatusLabel("succeeded")).toBe("报名成功");
    expect(attemptStatusLabel("skipped")).toBe("已跳过");
    expect(planStatusLabel("future-status")).toBe("future-status");
  });

  test("only allows active waiting plans to be cancelled", () => {
    expect(canCancelPlan("scheduled", true)).toBeTrue();
    expect(canCancelPlan("retrying", true)).toBeTrue();
    expect(canCancelPlan("running", true)).toBeFalse();
    expect(canCancelPlan("succeeded", false)).toBeFalse();
  });

  test("routes terminal results to reminders or attempt records", () => {
    expect(planResultHref("succeeded")).toBe("/reminders");
    expect(planResultHref("failed")).toBe("/attempts");
    expect(planResultHref("cancelled")).toBeNull();
  });
});
