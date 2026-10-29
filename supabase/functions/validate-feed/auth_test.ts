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

const ADMIN_ID = "11111111-1111-1111-1111-111111111111";

function headerOf(input: RequestInfo | URL, init?: RequestInit): string {
  const headers = (input instanceof Request ? input.headers : undefined) ??
    new Headers(init?.headers);
  return headers.get("Authorization") ?? "";
}

/**
 * Stub Supabase's /user and /admin_users plus the feed itself.
 *
 * The admin answer is conditional on the request, not just the URL: the real
 * gate works only because the caller's JWT rides along on the admin_users
 * query (RLS reads auth.uid()) and because the query filters on that user's
 * id. A stub that answered by URL alone would keep passing if either were
 * dropped, and every real admin would then get a 403 (PR 264 review).
 */
function stubFetch(
  isAdmin: boolean,
  feed: () => Response = () => new Response(FEED_ICS),
  token = "admin-token",
): { calls: string[]; restore: () => void } {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    calls.push(url);
    const authorized = headerOf(input, init) === `Bearer ${token}`;
    if (url.includes("/auth/v1/user")) {
      if (!authorized) {
        return Promise.resolve(
          new Response(JSON.stringify({ message: "invalid JWT" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ id: ADMIN_ID, aud: "authenticated" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    if (url.includes("/rest/v1/admin_users")) {
      const targeted = url.includes(`user_id=eq.${ADMIN_ID}`);
      const rows = isAdmin && authorized && targeted ? [{ user_id: ADMIN_ID }] : [];
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
  const stub = stubFetch(false, undefined, "user-token");

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

Deno.test("an invalid token returns 401 before the feed fetch", async () => {
  const restoreEnv = useAuthEnv();
  // The stub is the token "admin-token", so a different bearer fails /user.
  const stub = stubFetch(true, undefined, "someone-else");

  try {
    const resp = await handler(validateRequest("Bearer expired-token"));

    assert(resp.status === 401, `expected 401, got ${resp.status}`);
    const body = await resp.json();
    assert(body.error === "Invalid authorization", `unexpected error: ${body.error}`);
    assert(
      !stub.calls.some((url) => url.includes("feeds.example.com")),
      `feed was fetched: ${stub.calls.join(", ")}`,
    );
  } finally {
    stub.restore();
    restoreEnv();
  }
});

Deno.test("a feed that times out mid-read is reported, not thrown", async () => {
  const restoreEnv = useAuthEnv();
  const stub = stubFetch(
    true,
    () =>
      new Response(
        new ReadableStream({
          start(controller) {
            controller.error(new DOMException("timed out", "TimeoutError"));
          },
        }),
      ),
  );

  try {
    const resp = await handler(validateRequest("Bearer admin-token"));

    assert(resp.status === 200, `expected 200, got ${resp.status}`);
    const body = await resp.json();
    assert(body.valid === false, `expected valid:false, got ${JSON.stringify(body)}`);
    assert(body.error === "Feed timed out", `unexpected error: ${body.error}`);
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

    // A blocked URL is a validation result (200 + valid:false), not an error
    // status, so the dialog shows the reason instead of "Failed to validate".
    assert(resp.status === 200, `expected 200, got ${resp.status}`);
    const body = await resp.json();
    assert(body.valid === false, `expected valid:false, got ${JSON.stringify(body)}`);
    assert(body.error === "That host is not allowed", `unexpected error: ${body.error}`);
    assert(
      !stub.calls.some((url) => url.includes("169.254.169.254")),
      `metadata address was fetched: ${stub.calls.join(", ")}`,
    );
  } finally {
    stub.restore();
    restoreEnv();
  }
});

Deno.test("a blocked feed URL is reported without fetching it", async () => {
  const restoreEnv = useAuthEnv();
  const stub = stubFetch(true);

  try {
    const req = new Request("http://localhost/functions/v1/validate-feed", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer admin-token" },
      body: JSON.stringify({ url: "https://192.168.1.10/feed.ics" }),
    });
    const resp = await handler(req);

    assert(resp.status === 200, `expected 200, got ${resp.status}`);
    const body = await resp.json();
    assert(body.valid === false, `expected valid:false, got ${JSON.stringify(body)}`);
    assert(body.error === "That host is not allowed", `unexpected error: ${body.error}`);
    assert(
      !stub.calls.some((url) => url.includes("192.168.1.10")),
      `blocked host was fetched: ${stub.calls.join(", ")}`,
    );
  } finally {
    stub.restore();
    restoreEnv();
  }
});

Deno.test("a feed over the size cap is reported, not thrown", async () => {
  const restoreEnv = useAuthEnv();
  const stub = stubFetch(
    true,
    () => new Response(new Uint8Array(5 * 1024 * 1024 + 1)),
  );

  try {
    const resp = await handler(validateRequest("Bearer admin-token"));

    assert(resp.status === 200, `expected 200, got ${resp.status}`);
    const body = await resp.json();
    assert(body.valid === false, `expected valid:false, got ${JSON.stringify(body)}`);
    assert(body.error === "Feed is larger than 5 MiB", `unexpected error: ${body.error}`);
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
