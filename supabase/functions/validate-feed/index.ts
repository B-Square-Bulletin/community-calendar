// Validates an ICS feed URL and previews its upcoming events.
//
// Deployed with `verify_jwt` off, so this function carries its own
// authorization: admins only (GHSA-758r-g4xx-2j8r). The publishable key ships
// in xmlui/config.json, which means the gateway's JWT check would accept any
// visitor (ADR 0019) — and the only caller is the admin-gated Manage Feeds
// dialog. The fetch itself is restricted to public https URLs by url_policy.ts
// and every redirect hop is re-checked.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { checkFeedUrl } from "./url_policy.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-ue-client-tx-id",
};

const FEED_HEADERS = {
  "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
};
const FETCH_TIMEOUT_MS = 10_000;
const MAX_FEED_BYTES = 5 * 1024 * 1024;
const MAX_REDIRECTS = 3;

interface ParsedEvent {
  title: string;
  start_time: string;
  end_time: string | null;
  location: string | null;
  description: string | null;
  url: string | null;
  source: string | null;
  all_day: boolean;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

/**
 * Refuse the request unless the caller is an admin, without touching the URL.
 * Returns the response to send when access is denied, or null when allowed.
 */
async function requireAdmin(req: Request): Promise<Response | null> {
  const authHeader = req.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return json({ error: "Missing authorization", valid: false }, 401);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  // Fail closed: a deploy missing its env must not reopen the open proxy.
  if (!supabaseUrl || !anonKey) {
    return json({ error: "Auth unavailable", valid: false }, 500);
  }

  try {
    const supabase = createClient(supabaseUrl, anonKey, {
      global: { headers: { Authorization: authHeader } },
    });

    const { data, error } = await supabase.auth.getUser(
      authHeader.slice("Bearer ".length),
    );
    if (error || !data?.user) {
      return json({ error: "Invalid authorization", valid: false }, 401);
    }

    const { data: admins, error: adminError } = await supabase
      .from("admin_users")
      .select("user_id")
      .eq("user_id", data.user.id);
    if (adminError) {
      return json({ error: "Auth unavailable", valid: false }, 500);
    }
    if (!admins?.length) {
      return json({ error: "Admin authorization required", valid: false }, 403);
    }

    return null;
  } catch (err) {
    console.error("validate-feed auth check failed:", err);
    return json({ error: "Auth unavailable", valid: false }, 500);
  }
}

class FeedUrlRejected extends Error {}

/** Fetch a feed, following redirects only to URLs the policy allows. */
async function fetchFeed(start: URL): Promise<Response> {
  // One deadline for the whole fetch, not one per hop.
  const deadline = AbortSignal.timeout(FETCH_TIMEOUT_MS);
  let url = start;

  for (let hop = 0; ; hop++) {
    const resp = await fetch(url, {
      headers: FEED_HEADERS,
      redirect: "manual",
      signal: deadline,
    });

    if (resp.status < 300 || resp.status >= 400) return resp;

    const location = resp.headers.get("location");
    if (!location || hop === MAX_REDIRECTS) return resp;

    await resp.body?.cancel();

    let redirectTo: string;
    try {
      redirectTo = new URL(location, url).href;
    } catch {
      throw new FeedUrlRejected("Feed redirected to an invalid URL");
    }

    const next = checkFeedUrl(redirectTo);
    if (!next.ok) throw new FeedUrlRejected(next.error);
    url = next.url;
  }
}

/** Read at most MAX_FEED_BYTES of the body, or null when it is larger. */
async function readCapped(resp: Response): Promise<string | null> {
  const reader = resp.body?.getReader();
  if (!reader) return "";

  const chunks: Uint8Array[] = [];
  let total = 0;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    total += value.length;
    if (total > MAX_FEED_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }

  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  return new TextDecoder().decode(bytes);
}

function isTimeout(err: unknown): boolean {
  return err instanceof DOMException &&
    (err.name === "TimeoutError" || err.name === "AbortError");
}

/**
 * Parse an ICS datetime string into an ISO string.
 * Handles: 20260405T040000Z, 20260405T040000, 20260405
 */
function parseICSDate(raw: string): string | null {
  if (!raw) return null;
  // Strip any TZID prefix — take value after the colon if present
  const val = raw.includes(":") ? raw.split(":").pop()! : raw;
  const s = val.trim();

  if (s.length === 8) {
    // All-day: YYYYMMDD
    return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T00:00:00Z`;
  }
  if (s.length >= 15) {
    const iso = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T${s.slice(9, 11)}:${s.slice(11, 13)}:${s.slice(13, 15)}`;
    // naive datetimes are treated as UTC for the preview
    return iso + "Z";
  }
  return null;
}

/**
 * Unfold ICS continuation lines (lines starting with space or tab).
 */
function unfold(ics: string): string {
  return ics.replace(/\r?\n[ \t]/g, "");
}

/**
 * Extract field value from a VEVENT block.
 */
function extractField(block: string, field: string): string | null {
  const re = new RegExp(`^${field}[;:](.*)$`, "im");
  const m = block.match(re);
  if (!m) return null;
  return m[1].trim();
}

/**
 * Unescape ICS text values.
 */
function unescapeICS(text: string): string {
  return text
    .replace(/\\n/gi, "\n")
    .replace(/\\,/g, ",")
    .replace(/\\;/g, ";")
    .replace(/\\\\/g, "\\");
}

/**
 * Parse an ICS string into an array of events.
 */
function parseICS(ics: string): ParsedEvent[] {
  const unfolded = unfold(ics);
  const events: ParsedEvent[] = [];
  const blocks = unfolded.split("BEGIN:VEVENT");

  for (let i = 1; i < blocks.length; i++) {
    const block = blocks[i].split("END:VEVENT")[0];

    const rawStart = extractField(block, "DTSTART");
    if (!rawStart) continue;

    const startTime = parseICSDate(rawStart);
    if (!startTime) continue;

    const rawEnd = extractField(block, "DTEND");
    const endTime = rawEnd ? parseICSDate(rawEnd) : null;

    const summary = extractField(block, "SUMMARY");
    if (!summary) continue;

    const location = extractField(block, "LOCATION");
    const description = extractField(block, "DESCRIPTION");
    const url = extractField(block, "URL");
    const source = extractField(block, "X-SOURCE");

    // Detect all-day: VALUE=DATE or 8-char date
    const isAllDay =
      rawStart.includes("VALUE=DATE") ||
      (rawStart.replace(/.*:/, "").trim().length === 8);

    events.push({
      title: unescapeICS(summary),
      start_time: startTime,
      end_time: endTime,
      location: location ? unescapeICS(location) : null,
      description: description ? unescapeICS(description) : null,
      url: url ? unescapeICS(url) : null,
      source: source ? unescapeICS(source) : null,
      all_day: isAllDay,
    });
  }

  return events;
}

export async function handler(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const denied = await requireAdmin(req);
  if (denied) return denied;

  const body = await req.json().catch(() => null);
  const url = body?.url;
  if (!url || typeof url !== "string") {
    return json({ error: "Missing or invalid 'url' parameter", valid: false }, 400);
  }

  const target = checkFeedUrl(url);
  if (!target.ok) {
    // A rejected URL is a validation result, not a transport error: the
    // dialog renders `error` from a 200 the same way it does for a non-ICS
    // feed. Only auth failures are non-2xx, so an admin sees the reason.
    return json({ error: target.error, valid: false });
  }

  let feedResp: Response;
  try {
    feedResp = await fetchFeed(target.url);
  } catch (err) {
    if (err instanceof FeedUrlRejected) {
      return json({ error: err.message, valid: false });
    }
    if (isTimeout(err)) {
      return json({ error: "Feed timed out", valid: false }, 504);
    }
    console.error("validate-feed fetch failed:", err);
    return json({ error: "Validation failed", valid: false }, 500);
  }

  if (!feedResp.ok) {
    return json(
      { error: `Feed returned HTTP ${feedResp.status}`, valid: false },
    );
  }

  let icsText: string | null;
  try {
    icsText = await readCapped(feedResp);
  } catch (err) {
    if (isTimeout(err)) {
      return json({ error: "Feed timed out", valid: false }, 504);
    }
    console.error("validate-feed read failed:", err);
    return json({ error: "Validation failed", valid: false }, 500);
  }

  if (icsText === null) {
    return json({ error: "Feed is larger than 5 MiB", valid: false }, 413);
  }

  if (!icsText.includes("BEGIN:VCALENDAR")) {
    return json(
      { error: "Not a valid ICS feed (missing BEGIN:VCALENDAR)", valid: false },
    );
  }

  const allEvents = parseICS(icsText);
  const hasRecurrence = icsText.includes("RRULE:");

  // Filter to future events, sort by start_time, take first 10
  const now = new Date().toISOString();
  const futureEvents = allEvents
    .filter((e) => e.start_time >= now)
    .sort((a, b) => a.start_time.localeCompare(b.start_time))
    .slice(0, 10);

  return json({
    valid: true,
    totalEvents: allEvents.length,
    futureEvents: futureEvents.length,
    hasRecurrence,
    events: futureEvents,
  });
}

if (import.meta.main) Deno.serve(handler);
