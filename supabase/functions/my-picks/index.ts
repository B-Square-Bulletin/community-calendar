import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { dedupePickedEvents, withGroupMembership } from "./dedupe.ts";
import { respondWithICS, CACHE_CONTROL } from "./cache.ts";
import { compareEvents, generateICS } from "./ics.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// Fetch city→timezone mapping from repo (single source of truth: cities.json)
let _cityTimezones: Record<string, string> | null = null;
async function getCityTimezones(): Promise<Record<string, string>> {
  if (_cityTimezones) return _cityTimezones;
  try {
    const ghRepo = Deno.env.get("GITHUB_REPO") || "judell/community-calendar";
    const resp = await fetch(`https://raw.githubusercontent.com/${ghRepo}/main/cities.json`);
    const cities = await resp.json();
    _cityTimezones = {};
    for (const [city, config] of Object.entries(cities as Record<string, any>)) {
      if (config.timezone) _cityTimezones[city] = config.timezone;
    }
  } catch {
    // Do not cache the failure: a cached {} makes this isolate render other
    // bytes than its peers, and the feed's ETag never settles.
    return {};
  }
  return _cityTimezones;
}

Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    // Get token and format from query params
    const url = new URL(req.url);
    const token = url.searchParams.get("token");
    const format = url.searchParams.get("format") || "ics";

    if (!token) {
      return new Response(JSON.stringify({ error: "Missing token parameter" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Create Supabase client with service role for database access
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    // Validate token and get user_id
    const { data: tokenData, error: tokenError } = await supabase
      .from("feed_tokens")
      .select("user_id")
      .eq("token", token)
      .single();

    if (tokenError || !tokenData) {
      return new Response(JSON.stringify({ error: "Invalid token" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const userId = tokenData.user_id;

    // Get user's picks with event details and enrichments
    const { data: picks, error: picksError } = await supabase
      .from("picks")
      .select(`
        event_id,
        events (
          id,
          title,
          start_time,
          end_time,
          location,
          description,
          url,
          source,
          image_url,
          city,
          source_uid,
          duplicate_group,
          duplicate_group_representative,
          created_at
        )
      `)
      .eq("user_id", userId);

    // Get user's enrichments for these events
    const eventIds = (picks || []).map((p: any) => p.event_id).filter(Boolean);
    const { data: enrichments } = await supabase
      .from("event_enrichments")
      .select("*")
      .eq("curator_id", userId)
      .in("event_id", eventIds);

    // Create a map of enrichments by event_id
    const enrichmentMap = new Map(
      (enrichments || []).map((e: any) => [e.event_id, e])
    );

    if (picksError) {
      console.error("Error fetching picks:", picksError);
      return new Response(JSON.stringify({ error: "Failed to fetch picks" }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const groupIds = [...new Set(
      (picks || [])
        .map((pick: any) => pick.events?.duplicate_group)
        .filter((group: unknown): group is string => typeof group === "string" && group.length > 0),
    )];
    const memberships = new Map<string, Array<number | string>>();
    if (groupIds.length) {
      const { data: groups, error: groupsError } = await supabase
        .from("deduplicated_events")
        .select("duplicate_group, merged_ids")
        .in("duplicate_group", groupIds);
      if (groupsError) {
        console.error("Error fetching duplicate group membership:", groupsError);
        return new Response(JSON.stringify({ error: "Failed to fetch duplicate groups" }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      for (const group of groups || []) {
        if (group.duplicate_group && Array.isArray(group.merged_ids)) {
          memberships.set(group.duplicate_group, group.merged_ids);
        }
      }
    }

    // Extract events from picks and merge with enrichments. The feed renders
    // one entry per stored duplicate group; NULL groups stay separate.
    const pickedEvents = (picks || [])
      .map((p: any) => {
        const event = p.events;
        if (!event) return null;
        const enrichment = enrichmentMap.get(event.id);
        return {
          ...event,
          // Enrichment overrides
          rrule: enrichment?.rrule || null,
          categories: enrichment?.categories || null,
          notes: enrichment?.notes || null,
          // A curator edit is a feed change, and DTSTAMP carries it.
          updated_at: enrichment?.updated_at || null,
          // Enrichment can override these if present
          description: enrichment?.description || event.description,
          location: enrichment?.location || event.location,
        };
      })
      .filter((e: any) => e !== null);
    // id breaks start-time ties so the byte order (and the ETag) is stable
    const events = dedupePickedEvents(withGroupMembership(pickedEvents, memberships)).sort(compareEvents);

    // Return JSON or ICS based on format parameter
    if (format === "json") {
      return new Response(JSON.stringify(events), {
        headers: {
          ...corsHeaders,
          "Content-Type": "application/json",
          "Cache-Control": CACHE_CONTROL,
        },
      });
    }

    // Generate ICS
    const cityTimezones = await getCityTimezones();
    const ics = generateICS(events, "My Picks - Community Calendar", cityTimezones);

    return await respondWithICS(req, ics, {
      ...corsHeaders,
      "Content-Type": "text/calendar; charset=utf-8",
      "Content-Disposition": 'attachment; filename="my-picks.ics"',
    });
  } catch (error) {
    console.error("Error:", error);
    return new Response(JSON.stringify({ error: "Internal server error" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
