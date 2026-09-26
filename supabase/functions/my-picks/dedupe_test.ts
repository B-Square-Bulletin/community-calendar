// Tests for the my-picks group collapse. Run with:
//   deno test supabase/functions/my-picks/dedupe_test.ts
//
// WHY: the saved-picks ICS feed must not list a grouped event once per picked
// member. These tests pin the public collapse behavior (one entry per stored
// group, NULL rows separate, canonical representative preferred) without
// booting Deno.serve or touching the network.
import { dedupePickedEvents, withGroupMembership, type PickedEvent } from "./dedupe.ts";

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

Deno.test("collapses members of one stored group to a single entry", () => {
  const out = dedupePickedEvents([
    { id: 1, duplicate_group: "cr1:g", merged_ids: [1, 2] },
    { id: 2, duplicate_group: "cr1:g", merged_ids: [1, 2] },
  ]);
  assert(out.length === 1, `expected 1 entry, got ${out.length}`);
});

Deno.test("keeps NULL groups separate", () => {
  const out = dedupePickedEvents([
    { id: 1, duplicate_group: null },
    { id: 2, duplicate_group: null },
  ]);
  assert(out.length === 2, `expected 2 entries, got ${out.length}`);
});

Deno.test("prefers the canonical representative of a group", () => {
  const out = dedupePickedEvents([
    {
      id: 1,
      source_uid: "member",
      duplicate_group_representative: "rep",
      duplicate_group: "cr1:g",
    },
    {
      id: 2,
      source_uid: "rep",
      duplicate_group_representative: "rep",
      duplicate_group: "cr1:g",
    },
  ]);
  assert(out.length === 1, `expected 1 entry, got ${out.length}`);
  assert(out[0].id === 2, `expected representative id 2, got ${out[0].id}`);
});

Deno.test("falls back to the smallest member event id when the representative is not picked", () => {
  // A pick stored before the route existed, or a representative that changed
  // between builds, can leave the route's representative out of the picked
  // set. The collapse stays deterministic: one entry per group, smallest member
  // event id wins. The normal UI always picks the card's representative id, so
  // this is the defensive path (documented in ADR 0013). The client twin in
  // xmlui/helpers.js ranks on the same key, so the feed and list agree.
  const out = dedupePickedEvents([
    { id: 7, source_uid: "member-b", duplicate_group_representative: "rep", duplicate_group: "cr1:g" },
    { id: 3, source_uid: "member-a", duplicate_group_representative: "rep", duplicate_group: "cr1:g" },
  ]);
  assert(out.length === 1, `expected 1 entry, got ${out.length}`);
  assert(out[0].id === 3, `expected smallest event id 3, got ${out[0].id}`);
});

Deno.test("carries the complete stored membership into each picked group", () => {
  const picked: PickedEvent[] = [{ id: 2, duplicate_group: "cr1:g" }];
  const out = withGroupMembership(
    picked,
    new Map([["cr1:g", [1, 2, 3]]]),
  );
  assert(
    JSON.stringify(out[0].merged_ids) === JSON.stringify([1, 2, 3]),
    "expected the view membership to be carried into the picked event",
  );
});
