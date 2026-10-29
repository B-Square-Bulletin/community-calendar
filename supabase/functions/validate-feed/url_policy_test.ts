// Tests for the validate-feed URL policy (GHSA-758r-g4xx-2j8r). Run with:
//   deno test supabase/functions/validate-feed/url_policy_test.ts
//
// WHY: validate-feed fetched any caller-supplied URL from the Edge Runtime,
// so it was an open proxy into the project's network and the metadata address.
import { checkFeedUrl } from "./url_policy.ts";

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

function allowed(raw: string): void {
  const r = checkFeedUrl(raw);
  assert(r.ok, `expected ${raw} to be allowed, got: ${r.ok ? "" : r.error}`);
}

function blocked(raw: string): void {
  const r = checkFeedUrl(raw);
  assert(!r.ok, `expected ${raw} to be blocked`);
}

Deno.test("public https feed URLs are allowed", () => {
  allowed("https://www.meetup.com/events/ical/");
  allowed("https://feeds.example.com/calendar.ics?city=bloomington");
  allowed("https://example.com:443/feed.ics");
  // Near-misses of the private and special-use ranges must stay allowed.
  allowed("https://172.32.0.1/feed.ics");
  allowed("https://100.63.0.1/feed.ics");
  allowed("https://198.20.0.1/feed.ics");
  allowed("https://192.0.3.1/feed.ics");
  allowed("https://198.51.101.1/feed.ics");
  allowed("https://203.0.114.1/feed.ics");
  allowed("https://[2606:4700::1111]/feed.ics");
});

Deno.test("non-https and unparseable URLs are blocked", () => {
  blocked("http://example.com/feed.ics");
  blocked("ftp://example.com/feed.ics");
  blocked("file:///etc/passwd");
  blocked("not a url");
  blocked("");
});

Deno.test("non-default ports are blocked", () => {
  blocked("https://example.com:8443/feed.ics");
  blocked("https://example.com:22/feed.ics");
});

Deno.test("loopback, private and link-local hosts are blocked", () => {
  blocked("https://localhost/feed.ics");
  blocked("https://localhost./feed.ics");
  blocked("https://api.localhost/feed.ics");
  blocked("https://app.internal/feed.ics");
  blocked("https://app.internal./feed.ics");
  blocked("https://intranet/feed.ics");
  blocked("https://127.0.0.1/feed.ics");
  blocked("https://2130706433/feed.ics"); // decimal-encoded 127.0.0.1
  blocked("https://0x7f000001/feed.ics"); // hex-encoded 127.0.0.1
  blocked("https://10.1.2.3/feed.ics");
  blocked("https://172.20.0.1/feed.ics");
  blocked("https://192.168.1.1/feed.ics");
  blocked("https://100.64.0.1/feed.ics"); // CGNAT
  blocked("https://169.254.169.254/feed.ics"); // cloud metadata
  blocked("https://192.0.2.1/feed.ics"); // TEST-NET-1
  blocked("https://198.51.100.1/feed.ics"); // TEST-NET-2
  blocked("https://203.0.113.1/feed.ics"); // TEST-NET-3
  blocked("https://198.18.0.1/feed.ics"); // benchmarking 198.18/15
  blocked("https://0.0.0.0/feed.ics");
  blocked("https://224.0.0.1/feed.ics");
});

Deno.test("IPv6 loopback, ULA, link-local and v4-embedded forms are blocked", () => {
  blocked("https://[::1]/feed.ics");
  blocked("https://[::]/feed.ics");
  blocked("https://[fd00::1]/feed.ics");
  blocked("https://[fe80::1]/feed.ics");
  blocked("https://[ff02::1]/feed.ics");
  blocked("https://[::ffff:127.0.0.1]/feed.ics");
  blocked("https://[::ffff:169.254.169.254]/feed.ics");
  blocked("https://[::ffff:0:169.254.169.254]/feed.ics");
  blocked("https://[::7f00:1]/feed.ics"); // IPv4-compatible 127.0.0.1
  blocked("https://[64:ff9b::a9fe:a9fe]/feed.ics"); // NAT64 metadata
  blocked("https://[2002:a9fe:a9fe::1]/feed.ics"); // 6to4 metadata
});
