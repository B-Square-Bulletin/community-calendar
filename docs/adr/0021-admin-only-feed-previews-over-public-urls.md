# 0021. Feed Previews Are Admin-Only and Fetch Only Public URLs

Date: 2026-10-28

## Status

Accepted

## Context

`validate-feed` took a `url` from the JSON body and fetched it from the Edge
Runtime. It checked no scheme, blocked no address range, capped no response
size, set no timeout, echoed upstream HTTP statuses back, and ran with
`verify_jwt` off while checking nothing itself
(GHSA-758r-g4xx-2j8r).

Turning on the gateway's JWT check would not have helped: the publishable key
in `xmlui/config.json` satisfies it (ADR 0019). So anyone could use the
function as an open fetch proxy, spend a 256 MB worker on an uncapped body, and
read the status oracle. The only caller is the Manage Feeds dialog, which is
`isAdmin`-gated in the UI, and the write it previews (`feeds` INSERT) is
admin-only per RLS.

## Decision

**Require an admin JWT.** The function verifies the bearer token with
`auth.getUser()`, then looks for that user id in `admin_users`, and returns
401/403 before any outbound fetch. It fails closed with a 500 when
`SUPABASE_URL`/`SUPABASE_ANON_KEY` are missing or the auth check errors, the
same rule `load-events` follows (ADR 0019). The explicit `user_id` filter is
deliberate: reading "whatever `admin_users` SELECT returns" would silently
grant everyone access if that RLS policy were ever widened.

**Fetch only public https URLs.** `url_policy.ts` requires `https:`, the
default port, and a host that is not loopback, private, CGNAT, link-local
(including the cloud metadata address), multicast or a LAN-style single-label
name. The spellings a URL parser normalises (`0x7f000001`, `2130706433`,
`localhost.` with a trailing dot) and the IPv6 forms (`::1`, `fd00::/8`,
`fe80::/10`, and the v4-embedded `::ffff:`, `::`, NAT64 and 6to4 variants) are
covered by the same check.

**Re-check every redirect hop.** `fetch` follows up to 20 redirects by default,
which would let a public URL bounce to a private one. Redirects are fetched
with `redirect: "manual"`, followed at most 3 times, and each `Location` goes
back through the same policy.

**Cap the body at 5 MiB while streaming, and time out at 10s.** `.text()` on an
uncapped body is a worker OOM, and `Content-Length` is attacker-controlled and
absent for chunked responses. One deadline covers the whole fetch, redirects
included, so a chain of slow hops cannot hold the worker for longer than that.

**Keep the detail admins need, drop the detail they do not.** Upstream HTTP
statuses still come back as `{valid: false, error: "Feed returned HTTP 404"}`
because that is the feature. Raw exception text (`String(err)`) is gone:
failures are logged and the caller gets a fixed message. A URL the policy
refuses answers 200 with `valid: false` and the reason, the same shape the
dialog already renders for a non-ICS feed, so admins read "That host is not
allowed" instead of a generic failure. Only auth failures are non-2xx.

## Consequences

- A non-admin with the publishable key can no longer use the function at all;
  the dialog was already hidden from them.
- An expired admin session now fails validation with a 401 the dialog renders
  as a generic "Failed to validate feed"; saving a feed already failed the same
  way.
- A hostname that is public in DNS but resolves to a private address is still
  fetched. Judging by hostname keeps the check synchronous and testable, and
  closing the gap needs resolve-then-pin, which `fetch` cannot express. The
  residual risk is an admin pasting a hostile feed URL, not an anonymous
  attacker. Revisit if this endpoint ever serves non-admins.
- `supabase/functions/validate-feed/url_policy_test.ts` pins the policy and
  `auth_test.ts` asserts that an unauthorized request triggers zero outbound
  fetches.

## Alternatives Considered

- **Require any signed-in user** (the `capture-event` gate). Rejected: every
  account could then proxy fetches, and only admins can act on the result.
- **Turn `verify_jwt` back on.** Rejected: the publishable key passes it, so it
  adds no authorization (ADR 0019).
- **Allowlist known feed hosts.** Rejected: this project's discovery
  philosophy is complete long-tail coverage, and a new source would need a code
  deploy before it could be previewed.
- **Resolve DNS and reject private answers.** Rejected for now: `Deno.resolveDns`
  has broken in this runtime before, cannot be exercised in CI without network,
  and the resolve-then-fetch window leaves the same hole a determined attacker
  wants.
- **Disallow redirects entirely.** Rejected: real feeds redirect
  (`http`→`https`, feed proxies), and admins would see "invalid feed" for
  working sources.
