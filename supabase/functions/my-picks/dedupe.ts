// Collapse picked events to one entry per stored duplicate group.
//
// The confidence route's `duplicate_group` is authoritative: a NULL value means
// the route left the row alone, so the row is its own group. When several
// members of one group are picked, the route's canonical representative wins so
// the ICS feed matches the app's collapsed card. Ordering is left to the caller.
export interface PickedEvent {
  id: number | string;
  duplicate_group?: string | null;
  duplicate_group_representative?: string | null;
  merged_ids?: Array<number | string>;
  source_uid?: string | null;
  [key: string]: unknown;
}

export function withGroupMembership<T extends PickedEvent>(
  events: T[],
  memberships: ReadonlyMap<string, Array<number | string>>,
): T[] {
  return events.map((event) => {
    const group = event.duplicate_group;
    const mergedIds = group ? memberships.get(group) : undefined;
    return {
      ...event,
      merged_ids: mergedIds?.length ? [...mergedIds] : [event.id],
    };
  });
}

export function dedupePickedEvents<T extends PickedEvent>(events: T[]): T[] {
  const best = new Map<string, { event: T; rank: [number, number] }>();
  for (const event of events) {
    const group = event.duplicate_group;
    const key = group != null && group !== "" ? `g:${group}` : `r:${event.id}`;
    const rank: [number, number] = [
      event.duplicate_group_representative != null &&
      event.source_uid === event.duplicate_group_representative
        ? 0
        : 1,
      Number(event.id) || 0,
    ];
    const current = best.get(key);
    if (
      !current ||
      rank[0] < current.rank[0] ||
      (rank[0] === current.rank[0] && rank[1] < current.rank[1])
    ) {
      best.set(key, { event, rank });
    }
  }
  return [...best.values()].map((entry) => entry.event);
}
