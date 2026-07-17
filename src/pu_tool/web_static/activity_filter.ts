export type ActivityFilterItem = {
  activity_id?: unknown;
  title?: unknown;
  activity_type?: unknown;
  status?: unknown;
  location?: unknown;
  organizer?: unknown;
  score_items?: Array<{ kind?: unknown }>;
};

export type ActivityFilters = {
  query?: string;
  activityType?: string;
  status?: string;
  rewardKind?: string;
};

const normalized = (value: unknown) => String(value ?? '').trim().toLocaleLowerCase();

export function filterActivities<T extends ActivityFilterItem>(
  items: T[],
  filters: ActivityFilters,
): T[] {
  const query = normalized(filters.query);
  return items.filter((item) => {
    const searchable = [
      item.activity_id,
      item.title,
      item.activity_type,
      item.location,
      item.organizer,
    ].map(normalized);
    return (
      (!query || searchable.some((value) => value.includes(query)))
      && (!filters.activityType || String(item.activity_type ?? '') === filters.activityType)
      && (!filters.status || String(item.status ?? '') === filters.status)
      && (!filters.rewardKind || (item.score_items ?? []).some(
        (score) => score.kind === filters.rewardKind,
      ))
    );
  });
}
