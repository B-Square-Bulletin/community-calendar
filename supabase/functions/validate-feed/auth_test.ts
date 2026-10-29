// Tests for the validate-feed admin gate (GHSA-758r-g4xx-2j8r). Run with:
//   deno test --no-check --allow-env supabase/functions/validate-feed/auth_test.ts
//
// WHY: the function fetched any URL the caller supplied, and it is deployed
// without JWT verification, so it was an open proxy for anyone holding the
// public publishable key. A request that is not from an admin must be refused
// before any outbound feed fetch.
import { handler } from "./index.ts";

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

function useAuthEnv(): () => void {
  const url = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_ANON_KEY");
  Deno.env.set("SUPABASE_URL", "https://example.supabase.co");
  Deno.env.set("SUPABASE_ANON_KEY", "anon");
  return () => {
    if (url === undefined) Deno.env.delete("SUPABASE_URL");
    else Deno.env.set("SUPABASE_URL", url);
    if (key === undefined) Deno.env.delete("SUPABASE_ANON_KEY");
    else Deno.env.set("SUPABASE_ANON_KEY", key);
  };
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function validateRequest(auth?: string): Request {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) headers.Authorization = auth;
  return new Request("http://localhost/functions/v1/validate-feed", {
    method: "POST",
    headers,
    body: JSON.stringify({ url: "https://feeds.example.com/calendar.ics" }),
  });
}

const FEED_ICS = [
  "BEGIN:VCALENDAR",
  "BEGIN:VEVENT",
  "SUMMARY:Test Event",
  "DTSTART:20300405T040000Z",
  "DTEND:20300405T050000Z",
  "LOCATION:Test Hall",
  "END:VEVENT",
  "END:VCALENDAR",
].join("\r\n");

/** Stub Supabase's /user and /admin_users plus the feed itself. */
function stubFetch(
  isAdmin: boolean,
  feed: () => Response = () => new Response(FEED_ICS),
): { calls: string[]; restore: () => void } {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = ((input: RequestInfo | URL) => {
    const url = requestUrl(input);
    calls.push(url);
    if (url.includes("/auth/v1/user")) {
      return Promise.resolve(
        new Response(JSON.stringify({ id: "11111111-1111-1111-1111-111111111111", aud: "authenticated" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    if (url.includes("/rest/v1/admin_users")) {
      const rows = isAdmin ? [{ user_id: "11111111-1111-1111-1111-111111111111" }] : [];
      return Promise.resolve(
        new Response(JSON.stringify(rows), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    return Promise.resolve(feed());
  }) as typeof fetch;
  return { calls, restore: () => (globalThis.fetch = originalFetch) };
}

Deno.test("a request without a token returns 401 with no outbound fetch", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCalls = 0;
  globalThis.fetch = (() => {
    fetchCalls++;
    throw new Error("unexpected outbound fetch");
  }) as typeof fetch;

  try {
    const resp = await handler(validateRequest());

    assert(resp.status === 401, `expected 401, got ${resp.status}`);
    assert(fetchCalls === 0, `expected no outbound fetch, got ${fetchCalls}`);
    const body = await resp.json();
    assert(body.error === "Missing authorization", `unexpected error: ${body.error}`);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

Deno.test("a signed-in user who is not an admin gets 403 before the feed fetch", async () => {
  const restoreEnv = useAuthEnv();
  const stub = stubFetch(false);

  try {
    const resp = await handler(validateRequest("Bearer user-token"));

    assert(resp.status === 403, `expected 403, got ${resp.status}`);
    const body = await resp.json();
    assert(body.error === "Admin authorization required", `unexpected error: ${body.error}`);
    assert(
      !stub.calls.some((url) => url.includes("feeds.example.com")),
      `feed was fetched: ${stub.calls.join(", ")}`,
    );
  } finally {
    stub.restore();
    restoreEnv();
  }
});

Deno.test("a redirect to a private address is refused", async () => {
  const restoreEnv = useAuthEnv();
  const stub = stubFetch(
    true,
    () =>
      new Response(null, {
        status: 302,
        headers: { location: "https://169.254.169.254/latest/meta-data/" },
      }),
  );

  try {
    const resp = await handler(validateRequest("Bearer admin-token"));

    assert(resp.status === 400, `expected 400, got ${resp.status}`);
    assert(
      !stub.calls.some((url) => url.includes("169.254.169.254")),
      `metadata address was fetched: ${stub.calls.join(", ")}`,
    );
  } finally {
    stub.restore();
    restoreEnv();
  }
});

Deno.test("a feed over the size cap returns 413", async () => {
  const restoreEnv = useAuthEnv();
  const stub = stubFetch(
    true,
    () => new Response(new Uint8Array(5 * 1024 * 1024 + 1)),
  );

  try {
    const resp = await handler(validateRequest("Bearer admin-token"));

    assert(resp.status === 413, `expected 413, got ${resp.status}`);
  } finally {
    stub.restore();
    restoreEnv();
  }
});

Deno.test("an admin token still previews the feed", async () => {
  const restoreEnv = useAuthEnv();
  const stub = stubFetch(true);

  try {
    const resp = await handler(validateRequest("Bearer admin-token"));

    assert(resp.status === 200, `expected 200, got ${resp.status}`);
    const body = await resp.json();
    assert(body.valid === true, `unexpected body: ${JSON.stringify(body)}`);
    assert(body.totalEvents === 1, `expected 1 event, got ${body.totalEvents}`);
    assert(body.events[0].title === "Test Event", `unexpected title: ${body.events[0]?.title}`);
    assert(
      stub.calls.some((url) => url.includes("feeds.example.com")),
      "expected the feed to be fetched",
    );
  } finally {
    stub.restore();
    restoreEnv();
  }
});
