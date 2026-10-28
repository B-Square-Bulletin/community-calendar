// Tests for the capture-event auth gate (GHSA-qq24-wmxg-hrgv). Run with:
//   deno test --no-check --allow-env supabase/functions/capture-event/auth_test.ts
//
// WHY: extract forwards uploads to paid Anthropic/OpenAI APIs. A request with
// no user token must be refused before any outbound call.
import { handler, MAX_UPLOAD_BYTES } from "./index.ts";

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

function extractRequest(auth?: string, body = new FormData()): Request {
  const headers: Record<string, string> = {};
  if (auth) headers.Authorization = auth;
  return new Request("http://localhost/functions/v1/capture-event", {
    method: "POST",
    headers,
    body,
  });
}

Deno.test("extract without a token returns 401 with no outbound fetch", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCalls = 0;
  globalThis.fetch = (() => {
    fetchCalls++;
    throw new Error("unexpected outbound fetch");
  }) as typeof fetch;

  try {
    const form = new FormData();
    form.append("mode", "extract");
    form.append("file", new File(["poster"], "poster.jpg", { type: "image/jpeg" }));

    const resp = await handler(extractRequest(undefined, form));

    assert(resp.status === 401, `expected 401, got ${resp.status}`);
    assert(fetchCalls === 0, `expected no outbound fetch, got ${fetchCalls}`);
    const body = await resp.json();
    assert(body.error === "Missing authorization", `unexpected error: ${body.error}`);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

Deno.test("an invalid token returns 401 before a paid API call", async () => {
  const restoreEnv = useAuthEnv();
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = ((input: RequestInfo | URL) => {
    calls.push(requestUrl(input));
    return Promise.resolve(
      new Response(JSON.stringify({ message: "invalid JWT" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
  }) as typeof fetch;

  try {
    const form = new FormData();
    form.append("mode", "extract");
    form.append("file", new File(["poster"], "poster.jpg", { type: "image/jpeg" }));

    const resp = await handler(extractRequest("Bearer garbage", form));

    assert(resp.status === 401, `expected 401, got ${resp.status}`);
    const body = await resp.json();
    assert(body.error === "Invalid authorization", `unexpected error: ${body.error}`);
    assert(calls.length > 0, "expected a Supabase Auth check");
    assert(
      calls.every((url) => !url.includes("anthropic.com") && !url.includes("openai.com")),
      `paid API called: ${calls.join(", ")}`,
    );
  } finally {
    globalThis.fetch = originalFetch;
    restoreEnv();
  }
});

Deno.test("an upload over 10 MiB returns 413 before a paid API call", async () => {
  const restoreEnv = useAuthEnv();
  const originalFetch = globalThis.fetch;
  let paidCalls = 0;
  globalThis.fetch = ((input: RequestInfo | URL) => {
    const url = requestUrl(input);
    if (url.includes("anthropic.com") || url.includes("openai.com")) paidCalls++;
    return Promise.resolve(
      new Response(
        JSON.stringify({
          id: "11111111-1111-1111-1111-111111111111",
          aud: "authenticated",
          role: "authenticated",
          email: "test@example.com",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
  }) as typeof fetch;

  try {
    const form = new FormData();
    form.append("mode", "extract");
    form.append(
      "file",
      new File([new Uint8Array(MAX_UPLOAD_BYTES + 1)], "big.mp3", { type: "audio/mpeg" }),
    );

    const resp = await handler(extractRequest("Bearer token", form));

    assert(resp.status === 413, `expected 413, got ${resp.status}`);
    assert(paidCalls === 0, `paid API called ${paidCalls} times`);
  } finally {
    globalThis.fetch = originalFetch;
    restoreEnv();
  }
});
