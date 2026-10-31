// Tests that pin the loader's stale-sweep safety rules (issue #245). Run with:
//   deno test --no-check --allow-env supabase/functions/load-events/sweep_guard_test.ts
//
// WHY: the sweep deletes rows. A partially loaded city must not look like
// churn: failed upsert batches must quiet the sweep, an empty manifest must
// issue no sweep call, and an absent manifest must fall back to payload
// sources —
// so the upcoming hardening of this code cannot drop a rule silently (#245).
//
// The stub mirrors the documented SQL contract of delete_stale_events
// (20261022120000_ran_source_sweep.sql): p_sources NULL is the legacy
// whole-city path, an empty array matches no rows, a non-empty array deletes
// whatever it names.
import { handler } from "./index.ts";

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

const SECRET = "test-secret";

function useLoaderEnv(): () => void {
  const saved = Deno.env.get("LOAD_EVENTS_SECRET");
  Deno.env.set("LOAD_EVENTS_SECRET", SECRET);
  const savedUrl = Deno.env.get("SUPABASE_URL");
  Deno.env.set("SUPABASE_URL", "https://stub.supabase.co");
  const savedKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  Deno.env.set("SUPABASE_SERVICE_ROLE_KEY", "service-role");
  return () => {
    if (saved === undefined) Deno.env.delete("LOAD_EVENTS_SECRET");
    else Deno.env.set("LOAD_EVENTS_SECRET", saved);
    if (savedUrl === undefined) Deno.env.delete("SUPABASE_URL");
    else Deno.env.set("SUPABASE_URL", savedUrl);
    if (savedKey === undefined) Deno.env.delete("SUPABASE_SERVICE_ROLE_KEY");
    else Deno.env.set("SUPABASE_SERVICE_ROLE_KEY", savedKey);
  };
}

interface Call {
  url: string;
  body: unknown;
}

/** A stub DB: sweep deletes something unless the scope excludes all sources. */
function stubSupabase(fails: (batch: unknown[]) => boolean): {
  upserts: Call[];
  rpcs: Call[];
  restore: () => void;
} {
  const upserts: Call[] = [];
  const rpcs: Call[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string"
      ? input
      : input instanceof URL
      ? input.href
      : input.url;
    const call: Call = { url, body: init?.body ? JSON.parse(String(init.body)) : null };
    if (url.includes("/rest/v1/rpc/delete_stale_events")) {
      rpcs.push(call);
      const scope = (call.body as Record<string, unknown>).p_sources;
      const deleted = scope === null ? 1
      : Array.isArray(scope) && scope.length === 0 ? 0
      : 1;
      return Promise.resolve(
        new Response(String(deleted), { status: 200, headers: { "Content-Type": "application/json" } }),
      );
    }
    if (url.includes("/rest/v1/events")) {
      upserts.push(call);
      const batch = Array.isArray(call.body) ? call.body : [];
      if (!fails(batch)) return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(
        new Response(JSON.stringify({ message: "stub upsert failure" }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    throw new Error(`unexpected fetch: ${url}`);
  }) as typeof fetch;
  return { upserts, rpcs, restore: () => (globalThis.fetch = originalFetch) };
}

function loadRequest(events: unknown[], ranSources?: string[]): Request {
  return new Request("http://localhost/functions/v1/load-events", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-load-events-secret": SECRET,
    },
    body: JSON.stringify(
      ranSources === undefined
        ? { city: "bloomington", events }
        : { city: "bloomington", events, ran_sources: ranSources },
    ),
  });
}

const eventOf = (source: string) => ({
  source_uid: `${source}-uid-1`,
  source_id: source,
  title: `Event from ${source}`,
  start_time: "2030-04-05T04:00:00+00:00",
});

Deno.test("an absent manifest scopes the sweep to the payload's sources", async () => {
  const restoreEnv = useLoaderEnv();
  const stub = stubSupabase(() => false);

  try {
    const resp = await handler(
      loadRequest([eventOf("src-a"), eventOf("src-b")]),
    );

    assert(resp.status === 200, `expected 200, got ${resp.status}`);
    assert(stub.rpcs.length > 0, "expected the sweep RPC to run");
    const sortedScope = (scope: unknown) =>
      Array.isArray(scope) ? [...scope].map(String).sort() : String(scope);
    const expected = ["src-a", "src-b"].sort();
    for (const rpc of stub.rpcs) {
      const body = rpc.body as Record<string, unknown>;
      assert(
        JSON.stringify(sortedScope(body.p_sources)) === JSON.stringify(expected),
        `expected p_sources ["src-a","src-b"], got ${JSON.stringify(body.p_sources)}`,
      );
    }
    // Non-empty scope: the stub DB deletes, and the response reports it.
    const body = await resp.json();
    assert(body.deleted === 1, `expected a sweep, got ${JSON.stringify(body)}`);
    assert(body.success === true, `expected success=true, got ${JSON.stringify(body)}`);
  } finally {
    stub.restore();
    restoreEnv();
  }
});

Deno.test("a non-empty manifest alone decides the sweep scope", async () => {
  const restoreEnv = useLoaderEnv();
  const stub = stubSupabase(() => false);

  try {
    // src-payload-only ran a failed build: sweeping it would delete its rows.
    // src-quiet ran and produced no events: its stale rows must go.
    const resp = await handler(
      loadRequest([eventOf("src-payload-only"), eventOf("src-ran")], [
        "src-ran",
        "src-quiet",
      ]),
    );

    assert(resp.status === 200, `expected 200, got ${resp.status}`);
    assert(stub.rpcs.length > 0, "expected the sweep RPC to run");
    const scope = (stub.rpcs[0].body as Record<string, unknown>).p_sources;
    assert(Array.isArray(scope), `expected an array, got ${JSON.stringify(scope)}`);
    const sorted = [...(scope as string[])].sort();
    assert(
      JSON.stringify(sorted) === JSON.stringify(["src-quiet", "src-ran"]),
      `expected manifest sources, got ${JSON.stringify(sorted)}`,
    );
    assert(
      !sorted.includes("src-payload-only"),
      "a payload source that did not run must not be swept",
    );
  } finally {
    stub.restore();
    restoreEnv();
  }
});

Deno.test("a present but empty manifest sweeps nothing", async () => {
  const restoreEnv = useLoaderEnv();
  const stub = stubSupabase(() => false);

  try {
    const resp = await handler(
      loadRequest([eventOf("src-a")], []),
    );

    assert(resp.status === 200, `expected 200, got ${resp.status}`);
    // Issue #245: a present-but-empty manifest means zero sweep calls —
    // not merely a call whose empty scope happens to delete nothing.
    assert(stub.rpcs.length === 0, `expected no sweep call, got ${stub.rpcs.length}`);
    const body = await resp.json();
    assert(body.success === true, `expected success=true, got ${JSON.stringify(body)}`);
    assert(body.deleted === 0, `expected nothing swept, got ${JSON.stringify(body)}`);
  } finally {
    stub.restore();
    restoreEnv();
  }
});

Deno.test("a partially failed load means the sweep never runs", async () => {
  const restoreEnv = useLoaderEnv();
  // The loader upserts 500 at a time; batch 0 lands, batch 1 fails (#245).
  const stub = stubSupabase((batch) =>
    (batch as { source_id?: string }[]).some((e) => e.source_id === "src-bad")
  );
  const savedSetTimeout = globalThis.setTimeout;
  // The retry backoff is real production behavior; skipping the waits keeps
  // this test fast without adding a seam to index.ts.
  globalThis.setTimeout = ((fn: () => void) => {
    fn();
    return 0;
  }) as typeof setTimeout;

  try {
    const events = [
      ...Array.from({ length: 500 }, (_, i) => ({
        ...eventOf("src-a"),
        source_uid: `src-a-uid-${i}`,
      })),
      eventOf("src-bad"),
    ];
    const resp = await handler(loadRequest(events));

    assert(resp.status === 200, `expected 200, got ${resp.status}`);
    assert(stub.upserts.length >= 2, "expected both batches attempted");
    assert(
      stub.rpcs.length === 0,
      `sweep ran despite a failed batch: ${stub.rpcs.map((c) => c.url).join(", ")}`,
    );
    const body = await resp.json();
    assert(body.inserted === 500, `expected 500 inserted, got ${JSON.stringify(body)}`);
    assert(body.errors === 1, `expected 1 error, got ${JSON.stringify(body)}`);
    assert(body.success === false, "expected success=false");
    assert(body.deleted === 0, `expected deleted=0, got ${JSON.stringify(body)}`);
  } finally {
    globalThis.setTimeout = savedSetTimeout;
    stub.restore();
    restoreEnv();
  }
});
