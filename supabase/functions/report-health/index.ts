import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    const body = await req.json().catch(() => ({}));
    const { city, feeds, anomalies } = body;

    if (!city || !Array.isArray(feeds)) {
      return new Response(
        JSON.stringify({
          success: false,
          error: "Missing required fields: city, feeds",
        }),
        {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    console.log(
      `report-health: ${city} — ${feeds.length} feeds, ${anomalies?.length || 0} anomalies`,
    );

    // --- Upsert feed_health rows with conflict resolution ---
    // Strategy: prefer a successful run (error IS NULL) over an error run.
    // If an existing row for (city, feed_name, checked_date) has no error, a
    // new error row does NOT overwrite it. A success always overwrites an
    // error. A newer error overwrites an older error.

    let inserted = 0;
    let skipped = 0;
    let errors = 0;
    const errorDetails: string[] = [];

    for (const feed of feeds) {
      const { feed_name, checked_date, event_count, error: feedError } = feed;

      if (!feed_name || !checked_date) {
        skipped++;
        continue;
      }

      // Check if an existing error-free row exists for today
      const { data: existing } = await supabase
        .from("feed_health")
        .select("id, error")
        .eq("city", city)
        .eq("feed_name", feed_name)
        .eq("checked_date", checked_date)
        .maybeSingle();

      // If a successful run already exists and this run has an error, skip
      if (existing && existing.error === null && feedError) {
        skipped++;
        continue;
      }

      // Upsert the row (with conflict on the unique constraint)
      const row = {
        city,
        feed_name,
        source_name: feed.source_name || null,
        source_url: feed.source_url || null,
        feed_type: feed.feed_type || "ics_url",
        scraper_cmd: feed.scraper_cmd || null,
        event_count: event_count ?? 0,
        error: feedError || null,
        checked_date,
      };

      let lastError: any = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        const { error: upsertError } = await supabase
          .from("feed_health")
          .upsert(row, {
            onConflict: "city,feed_name,checked_date",
          });
        if (!upsertError) {
          inserted++;
          lastError = null;
          break;
        }
        lastError = upsertError;
        console.error(
          `Feed ${feed_name} attempt ${attempt + 1} error:`,
          JSON.stringify(upsertError),
        );
        if (attempt < 2) {
          await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
        }
      }
      if (lastError) {
        errors++;
        errorDetails.push(
          `${feed_name}: ${lastError.message || JSON.stringify(lastError)}`,
        );
      }
    }

    // --- Insert anomalies ---
    let anomaliesInserted = 0;
    if (anomalies && Array.isArray(anomalies) && anomalies.length > 0) {
      const anomalyRows = anomalies.map((a: any) => ({
        city,
        feed_name: a.feed_name || a.feed,
        anomaly_type: a.type || a.anomaly_type || "unknown",
        severity: a.severity || "medium",
        message: a.message || "",
        previous_count: a.previous_count ?? null,
        current_count: a.current_count ?? null,
      }));

      let lastError: any = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        const { error: anomalyError } = await supabase
          .from("feed_anomalies")
          .insert(anomalyRows);
        if (!anomalyError) {
          anomaliesInserted = anomalyRows.length;
          lastError = null;
          break;
        }
        lastError = anomalyError;
        if (attempt < 2) {
          await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
        }
      }
      if (lastError) {
        errorDetails.push(
          `anomalies: ${lastError.message || JSON.stringify(lastError)}`,
        );
      }
    }

    // --- Prune old data ---
    let prunedHealth = 0;
    let prunedAnomalies = 0;

    const { data: hCount, error: hPruneError } = await supabase.rpc(
      "prune_feed_health",
      { p_city: city, p_days: 60 },
    );
    if (hPruneError) {
      console.error(`Prune feed_health error:`, hPruneError);
    } else {
      prunedHealth = hCount || 0;
    }

    const { data: aCount, error: aPruneError } = await supabase.rpc(
      "prune_feed_anomalies",
      { p_city: city, p_days: 60 },
    );
    if (aPruneError) {
      console.error(`Prune feed_anomalies error:`, aPruneError);
    } else {
      prunedAnomalies = aCount || 0;
    }

    const result: any = {
      success: errors === 0,
      city,
      inserted,
      skipped,
      pruned: prunedHealth + prunedAnomalies,
      // Internal detail — caller may ignore
      errors,
      anomalies_inserted: anomaliesInserted,
      pruned_health: prunedHealth,
      pruned_anomalies: prunedAnomalies,
    };
    if (errorDetails.length > 0) {
      result.errorDetails = errorDetails;
    }

    console.log("Result:", JSON.stringify(result));
    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Error:", error);
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }
});
