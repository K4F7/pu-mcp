export type LoginSchoolPayload = { sid: string } | { encoded_sid: string };

export function loginSchoolPayload(value: string): LoginSchoolPayload {
  const normalized = value.trim();
  if (!normalized) {
    throw new Error('请输入学校 SID、编码 SID 或 class 登录链接');
  }
  return /^\d+$/.test(normalized)
    ? { sid: normalized }
    : { encoded_sid: normalized };
}
