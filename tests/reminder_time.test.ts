import { describe, expect, test } from 'bun:test';
import { describeReminderTime } from '../src/pu_tool/web_static/reminder_time';

const minute = 60_000;
const now = Date.UTC(2026, 6, 17, 4, 0, 0);

describe('describeReminderTime', () => {
  test('shows rounded-up minutes until the activity starts', () => {
    expect(describeReminderTime(now + 90_001, now + 10 * minute, now)).toEqual({
      status: '即将开始',
      countdown: '还有 2 分钟开始',
    });
  });

  test('shows minutes until the activity ends while in progress', () => {
    expect(describeReminderTime(now - minute, now + 61_000, now)).toEqual({
      status: '进行中',
      countdown: '还有 2 分钟结束',
    });
  });

  test('handles exact boundaries and missing times', () => {
    expect(describeReminderTime(now, now + minute, now).status).toBe('进行中');
    expect(describeReminderTime(now - minute, now, now)).toEqual({
      status: '已结束',
      countdown: '活动已结束',
    });
    expect(describeReminderTime(null, null, now).status).toBe('时间未知');
    expect(describeReminderTime(now - minute, null, now).countdown).toBe('结束时间未知');
  });
});
