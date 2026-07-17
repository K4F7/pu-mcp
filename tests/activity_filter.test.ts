import { describe, expect, test } from 'bun:test';
import { filterActivities } from '../src/pu_tool/web_static/activity_filter';

const activities = [
  {
    activity_id: 'A-1',
    title: '志愿服务活动',
    activity_type: '志愿公益',
    status: 'open',
    location: '北区报告厅',
    organizer: '青年志愿者协会',
    score_items: [{ kind: 'academic_credit' }],
  },
  {
    activity_id: 'A-2',
    title: '创新讲座',
    activity_type: '学术讲座',
    status: 'scheduled',
    location: '南区教室',
    organizer: '创新学院',
    score_items: [{ kind: 'point' }],
  },
];

describe('filterActivities', () => {
  test('searches title, id, location, organizer and type case-insensitively', () => {
    expect(filterActivities(activities, { query: 'a-2' })).toHaveLength(1);
    expect(filterActivities(activities, { query: '报告厅' })[0]?.activity_id).toBe('A-1');
    expect(filterActivities(activities, { query: '创新学院' })[0]?.activity_id).toBe('A-2');
    expect(filterActivities(activities, { query: '志愿公益' })[0]?.activity_id).toBe('A-1');
  });

  test('combines type, status and reward filters', () => {
    expect(filterActivities(activities, {
      activityType: '志愿公益',
      status: 'open',
      rewardKind: 'academic_credit',
    })).toEqual([activities[0]]);
    expect(filterActivities(activities, {
      activityType: '志愿公益',
      rewardKind: 'point',
    })).toEqual([]);
  });

  test('does not mutate the source list', () => {
    const result = filterActivities(activities, { query: '' });
    expect(result).not.toBe(activities);
    expect(result).toEqual(activities);
  });
});
