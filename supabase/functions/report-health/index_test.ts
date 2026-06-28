// Tests for the report-health edge function.
//
// Run:
//   SUPABASE_URL=http://127.0.0.1:54321 \
//   SUPABASE_SERVICE_ROLE_KEY=sb_secret_REDACTED \
//   deno test --allow-net --allow-env supabase/functions/report-health/index_test.ts -q
//
// Prerequisite: local Supabase must have RLS disabled and GRANTs applied:
//   ALTER TABLE feed_health DISABLE ROW LEVEL SECURITY;
//   ALTER TABLE feed_anomalies DISABLE ROW LEVEL SECURITY;
//   GRANT ALL ON feed_health TO anon, authenticated, service_role;
//   GRANT ALL ON feed_anomalies TO anon, authenticated, service_role;

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import {
  assertEquals,
  assertExists,
} from "https://deno.land/std/testing/asserts.ts";
import { processHealthReport, handler } from "./index.ts";

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

// ============================================================================
// Task 1: Basic insert
// ============================================================================

Deno.test("processHealthReport inserts feed_health rows", async () => {
  const city = "test-report-health";

  await supabase.from("feed_health").delete().eq("city", city);

  const payload = {
    city,
    feeds: [
      {
        feed_name: "test_feed_1",
        checked_date: "2026-06-28",
        event_count: 5,
        feed_type: "ics_url",
      },
      {
        feed_name: "test_feed_2",
        checked_date: "2026-06-28",
        event_count: 10,
        error: null,
        feed_type: "scraper",
      },
    ],
    anomalies: [],
  };

  const result = await processHealthReport(supabase, payload);

  assertEquals(result.success, true);
  assertEquals(result.inserted, 2);
  assertEquals(result.skipped, 0);
  assertEquals(result.city, city);

  const { data: rows } = await supabase
    .from("feed_health")
    .select("*")
    .eq("city", city)
    .eq("checked_date", "2026-06-28");

  assertEquals(rows?.length, 2);

  await supabase.from("feed_health").delete().eq("city", city);
});

// ============================================================================
// Task 2: Input validation
// ============================================================================

Deno.test("processHealthReport returns error for missing city", async () => {
  const result = await processHealthReport(supabase, {
    city: "",
    feeds: [],
  });

  assertEquals(result.success, false);
  assertEquals(result.error, "Missing required fields: city, feeds");
});

Deno.test("processHealthReport returns error for non-array feeds", async () => {
  // deno-lint-ignore no-explicit-any
  const result = await processHealthReport(supabase, {
    city: "test",
    feeds: "not-an-array" as any,
  });

  assertEquals(result.success, false);
});

// ============================================================================
// Task 3: Skip rows with missing fields
// ============================================================================

Deno.test("processHealthReport skips feeds with missing fields", async () => {
  const city = "test-skip-fields";

  await supabase.from("feed_health").delete().eq("city", city);

  const payload = {
    city,
    feeds: [
      { checked_date: "2026-06-28", event_count: 5 }, // no feed_name
      { feed_name: "no_date", event_count: 3 }, // no checked_date
      {
        feed_name: "valid",
        checked_date: "2026-06-28",
        event_count: 7,
        feed_type: "ics_url",
      },
    ],
    anomalies: [],
  };

  const result = await processHealthReport(supabase, payload);

  assertEquals(result.inserted, 1);
  assertEquals(result.skipped, 2);

  const { data: rows } = await supabase
    .from("feed_health")
    .select("feed_name")
    .eq("city", city)
    .eq("checked_date", "2026-06-28");

  assertEquals(rows?.length, 1);
  assertEquals(rows?.[0]?.feed_name, "valid");

  await supabase.from("feed_health").delete().eq("city", city);
});

// ============================================================================
// Task 4: Upsert — success row survives error
// ============================================================================

Deno.test("processHealthReport preserves success row over error row", async () => {
  const city = "test-conflict-resolution";
  const date = "2026-06-28";

  // Insert a successful row directly
  await supabase.from("feed_health").insert({
    city,
    feed_name: "conflict_feed",
    feed_type: "ics_url",
    event_count: 10,
    error: null,
    checked_date: date,
  });

  // Call with an error for the same (city, feed, date)
  const result = await processHealthReport(supabase, {
    city,
    feeds: [
      {
        feed_name: "conflict_feed",
        checked_date: date,
        event_count: 0,
        error: "Something broke",
        feed_type: "scraper",
      },
    ],
    anomalies: [],
  });

  // Should skip, not overwrite the successful row
  assertEquals(result.skipped, 1);
  assertEquals(result.inserted, 0);

  // Verify the success row still has event_count=10, error=null
  const { data: row } = await supabase
    .from("feed_health")
    .select("event_count, error")
    .eq("city", city)
    .eq("feed_name", "conflict_feed")
    .eq("checked_date", date)
    .single();

  assertEquals(row?.event_count, 10);
  assertEquals(row?.error, null);

  await supabase.from("feed_health").delete().eq("city", city);
});

// ============================================================================
// Task 5: Upsert — error row overwritten by success
// ============================================================================

Deno.test("processHealthReport overwrites error row with success", async () => {
  const city = "test-error-overwrite";
  const date = "2026-06-28";

  // Insert an error row
  await supabase.from("feed_health").insert({
    city,
    feed_name: "flaky_feed",
    feed_type: "ics_url",
    event_count: 0,
    error: "Connection timeout",
    checked_date: date,
  });

  // Call with success for the same key
  const result = await processHealthReport(supabase, {
    city,
    feeds: [
      {
        feed_name: "flaky_feed",
        checked_date: date,
        event_count: 42,
        error: null,
        feed_type: "ics_url",
      },
    ],
    anomalies: [],
  });

  assertEquals(result.inserted, 1);
  assertEquals(result.skipped, 0);

  const { data: row } = await supabase
    .from("feed_health")
    .select("event_count, error")
    .eq("city", city)
    .eq("feed_name", "flaky_feed")
    .eq("checked_date", date)
    .single();

  assertEquals(row?.event_count, 42);
  assertEquals(row?.error, null);

  await supabase.from("feed_health").delete().eq("city", city);
});

// ============================================================================
// Task 6: Anomaly insertion
// ============================================================================

Deno.test("processHealthReport inserts anomalies", async () => {
  const city = "test-anomalies";

  await supabase.from("feed_health").delete().eq("city", city);
  await supabase.from("feed_anomalies").delete().eq("city", city);

  const result = await processHealthReport(supabase, {
    city,
    feeds: [
      {
        feed_name: "empty_feed",
        checked_date: "2026-06-28",
        event_count: 0,
        feed_type: "ics_url",
      },
    ],
    anomalies: [
      {
        feed_name: "empty_feed",
        type: "zero_events",
        severity: "high",
        message: "Feed produced 0 events today",
        previous_count: 15,
        current_count: 0,
      },
    ],
  });

  assertEquals(result.anomalies_inserted, 1);

  const { data: rows } = await supabase
    .from("feed_anomalies")
    .select("*")
    .eq("city", city);

  assertEquals(rows?.length, 1);
  assertEquals(rows?.[0]?.feed_name, "empty_feed");
  assertEquals(rows?.[0]?.anomaly_type, "zero_events");
  assertEquals(rows?.[0]?.severity, "high");
  assertEquals(rows?.[0]?.previous_count, 15);
  assertEquals(rows?.[0]?.current_count, 0);

  await supabase.from("feed_health").delete().eq("city", city);
  await supabase.from("feed_anomalies").delete().eq("city", city);
});

// ============================================================================
// Task 7: HTTP handler — CORS on OPTIONS
// ============================================================================

Deno.test("handler returns CORS headers on OPTIONS", async () => {
  const req = new Request("http://localhost/functions/v1/report-health", {
    method: "OPTIONS",
  });
  const resp = await handler(req);

  assertEquals(resp.headers.get("Access-Control-Allow-Origin"), "*");
  assertEquals(
    resp.headers.get("Access-Control-Allow-Headers"),
    "authorization, x-client-info, apikey, content-type",
  );
});

// ============================================================================
// Task 8: HTTP handler — 400 on invalid payload
// ============================================================================

Deno.test("handler returns 400 on missing city", async () => {
  const req = new Request("http://localhost/functions/v1/report-health", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feeds: [] }),
  });
  const resp = await handler(req);
  assertEquals(resp.status, 400);
  const body = await resp.json();
  assertEquals(body.success, false);
  assertEquals(body.error, "Missing required fields: city, feeds");
});
