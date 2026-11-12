// Tests for the my-picks conditional response. Run with:
//   deno test supabase/functions/my-picks/cache_test.ts
//
// WHY: calendar apps re-poll the same personal feed every 15 minutes to a day.
// The function has always emitted an ETag but never read the request's
// If-None-Match, so a subscriber re-downloaded an unchanged calendar every
// time. These tests pin both branches of the validator, plus the renderer's
// byte stability, which the validator hashes.
import { respondWithICS } from "./cache.ts";
import { compareEvents, generateICS, laterTimestamp } from "./ics.ts";

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

const ICS = "BEGIN:VCALENDAR\r\nEND:VCALENDAR";

function request(ifNoneMatch?: string): Request {
  return new Request("http://localhost/functions/v1/my-picks", {
    headers: ifNoneMatch ? { "If-None-Match": ifNoneMatch } : {},
  });
}

Deno.test("returns 304 with no body when the validator matches", async () => {
  const first = await respondWithICS(request(), ICS, {});
  const etag = first.headers.get("ETag")!;
  const second = await respondWithICS(request(etag), ICS, {});

  assert(second.status === 304, `expected 304, got ${second.status}`);
  assert((await second.text()) === "", "expected an empty 304 body");
});

Deno.test("returns 200 with a new validator when the feed changes", async () => {
  const first = await respondWithICS(request(), ICS, {});
  const etag = first.headers.get("ETag")!;
  const second = await respondWithICS(request(etag), ICS + "\r\n", {});

  assert(second.status === 200, `expected 200, got ${second.status}`);
  assert((await second.text()) === ICS + "\r\n", "expected the new body");
  assert(second.headers.get("ETag") !== etag, "expected a new ETag");
});

Deno.test("returns 200 when the request carries no validator", async () => {
  const res = await respondWithICS(request(), ICS, {});

  assert(res.status === 200, `expected 200, got ${res.status}`);
  assert((await res.text()) === ICS, "expected the body");
  assert(res.headers.get("ETag") !== null, "expected an ETag");
});

Deno.test("honours weak, listed and wildcard validators", async () => {
  const etag = (await respondWithICS(request(), ICS, {})).headers.get("ETag")!;
  for (const header of [`W/${etag}`, `"other", ${etag}`, "*"]) {
    const res = await respondWithICS(request(header), ICS, {});
    assert(res.status === 304, `expected 304 for ${header}, got ${res.status}`);
  }
});

const PICK = {
  id: 1,
  title: "Concert",
  start_time: "2030-04-05T18:00:00Z",
  end_time: null,
  location: null,
  description: null,
  url: null,
  image_url: null,
  city: "bloomington",
  rrule: null,
  notes: null,
  categories: null,
  created_at: "2026-01-02T03:04:05Z",
};

Deno.test("an unchanged pick list renders the same bytes and answers 304", async () => {
  // The ETag hashes the ICS, so a per-render timestamp (the old DTSTAMP) would
  // change the validator on every poll and 304 would never happen in production.
  const tz = { bloomington: "America/Indiana/Indianapolis" };
  const first = generateICS([PICK], "My Picks", tz);
  const second = generateICS([PICK], "My Picks", tz);

  assert(first === second, "expected two renders of the same picks to be identical");
  assert(
    first.includes("DTSTAMP:20260102T030405Z"),
    "expected DTSTAMP to come from the event, not the request clock",
  );
  assert(
    first.includes("LAST-MODIFIED:20260102T030405Z"),
    "expected an untouched event to carry its creation time as LAST-MODIFIED",
  );
  const etag = (await respondWithICS(request(), first, {})).headers.get("ETag")!;
  const res = await respondWithICS(request(etag), second, {});
  assert(res.status === 304, `expected 304, got ${res.status}`);
});

Deno.test("an edit keeps DTSTAMP and moves LAST-MODIFIED", () => {
  // RFC 5545: DTSTAMP is creation, LAST-MODIFIED is the last content change.
  // A client that ignores DTSTAMP must still see the reschedule.
  const tz = { bloomington: "America/Indiana/Indianapolis" };
  const edited = { ...PICK, updated_at: "2026-02-03T04:05:06Z" };
  const before = generateICS([PICK], "My Picks", tz);
  const after = generateICS([edited], "My Picks", tz);

  assert(
    after.includes("DTSTAMP:20260102T030405Z"),
    "expected the creation time to stay put",
  );
  assert(
    after.includes("LAST-MODIFIED:20260203T040506Z"),
    "expected the edit time on LAST-MODIFIED",
  );
  const withoutModified = (ics: string) =>
    ics.split("\r\n").filter((line) => !line.startsWith("LAST-MODIFIED:")).join("\r\n");
  assert(
    withoutModified(before) === withoutModified(after),
    "expected LAST-MODIFIED to be the only line an edit changes",
  );
});

Deno.test("the later of a curator edit and a source change wins", () => {
  // An older enrichment must not freeze LAST-MODIFIED over a newer feed edit,
  // and the merge must stay null-safe when a pick has neither.
  assert(
    laterTimestamp("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z") ===
      "2026-02-01T00:00:00Z",
    "expected the later source change to win",
  );
  assert(
    laterTimestamp("2026-03-01T00:00:00Z", "2026-02-01T00:00:00Z") ===
      "2026-03-01T00:00:00Z",
    "expected the later curator edit to win",
  );
  assert(
    laterTimestamp(null, "2026-02-01T00:00:00Z") === "2026-02-01T00:00:00Z",
    "expected a source-only timestamp to survive",
  );
  assert(laterTimestamp(undefined, null) === null, "expected null for neither");
});

Deno.test("equal start times keep one byte order", () => {
  // PostgREST returns tied rows in no guaranteed order, so an unstable sort
  // would flap the ETag for any curator with two events at the same time.
  const a = { ...PICK, id: 2, title: "Two" };
  const b = { ...PICK, id: 1, title: "One" };

  assert(
    generateICS([a, b].sort(compareEvents), "My Picks", {}) ===
      generateICS([b, a].sort(compareEvents), "My Picks", {}),
    "expected a total order over picks",
  );
});
