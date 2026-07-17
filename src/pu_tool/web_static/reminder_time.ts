export type ReminderTimeState = {
  status: '即将开始' | '进行中' | '已结束' | '时间未知';
  countdown: string;
};

const remainingMinutes = (target: number, now: number) =>
  Math.max(1, Math.ceil((target - now) / 60_000));

export function describeReminderTime(
  start: number | null,
  end: number | null,
  now = Date.now(),
): ReminderTimeState {
  if (start === null) {
    return { status: '时间未知', countdown: '无法计算开始时间' };
  }
  if (now < start) {
    return { status: '即将开始', countdown: `还有 ${remainingMinutes(start, now)} 分钟开始` };
  }
  if (end === null) {
    return { status: '进行中', countdown: '结束时间未知' };
  }
  if (now < end) {
    return { status: '进行中', countdown: `还有 ${remainingMinutes(end, now)} 分钟结束` };
  }
  return { status: '已结束', countdown: '活动已结束' };
}
