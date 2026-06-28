// Tests for the report-health edge function.
//
// Run:
//   SUPABASE_URL=http://127.0.0.1:54321 \
//   SUPABASE_SERVICE_ROLE_KEY=sb_secret_REDACTED \
//   deno test --allow-net --allow-env supabase/functions/report-health/index_test.ts -q

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import {
  assertEquals,
  assertExists,
} from "https://deno.land/std/testing/asserts.ts";
import { processHealthReport } from "./index.ts";

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

Deno.test("processHealthReport inserts feed_health rows", async () => {
  const city = "test-report-health";

  // Clean up any leftovers
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

  // Verify rows in the database
  const { data: rows } = await supabase
    .from("feed_health")
    .select("*")
    .eq("city", city)
    .eq("checked_date", "2026-06-28");

  assertEquals(rows?.length, 2);

  // Cleanup
  await supabase.from("feed_health").delete().eq("city", city);
});
