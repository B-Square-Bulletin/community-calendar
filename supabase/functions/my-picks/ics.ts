// ICS rendering for the my-picks feed. Kept free of Supabase and Deno.serve so
// the byte-stability the ETag depends on is testable without a database.

// Format date for ICS as UTC (YYYYMMDDTHHMMSSZ)
function formatICSDateUTC(isoString: string): string {
  const d = new Date(isoString);
  return d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

// Format date for ICS as local time (YYYYMMDDTHHMMSS) for use with TZID
function formatICSDateLocal(isoString: string, timezone: string): string {
  const d = new Date(isoString);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const v: Record<string, string> = {};
  parts.forEach(p => { v[p.type] = p.value; });
  const hour = v.hour === "24" ? "00" : v.hour;
  return `${v.year}${v.month}${v.day}T${hour}${v.minute}${v.second}`;
}

// Escape text for ICS format
function escapeICS(text: string | null): string {
  if (!text) return "";
  return text
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\n/g, "\\n");
}

// Total order over picks: equal start times would otherwise render in whatever
// order PostgREST returned, and the ETag hashes that order.
export function compareEvents(a: any, b: any): number {
  return a.start_time.localeCompare(b.start_time) || Number(a.id) - Number(b.id);
}

// Generate ICS content from events. The output must be byte-identical for the
// same input: the feed's ETag is a hash of these bytes.
export function generateICS(events: any[], calendarName: string, cityTimezones: Record<string, string>): string {
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Community Calendar//My Picks//EN",
    `X-WR-CALNAME:${escapeICS(calendarName)}`,
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
  ];

  for (const event of events) {
    // For recurring events, use TZID so BYDAY expands in the correct timezone
    const tz = event.rrule && event.city ? cityTimezones[event.city] : null;

    lines.push("BEGIN:VEVENT");
    lines.push(`UID:pick-${event.id}@community-calendar`);
    // DTSTAMP is the only per-event timestamp a calendar client reads, so it
    // must move when the event does and stay put when it does not: a request
    // clock here changes the body (and the ETag) on every poll.
    // shortcut: source-side field edits do not bump DTSTAMP; switch to
    // events.updated_at when that column exists.
    lines.push(
      `DTSTAMP:${formatICSDateUTC(event.updated_at || event.created_at || event.start_time)}`,
    );
    if (tz) {
      lines.push(`DTSTART;TZID=${tz}:${formatICSDateLocal(event.start_time, tz)}`);
    } else {
      lines.push(`DTSTART:${formatICSDateUTC(event.start_time)}`);
    }
    if (event.end_time) {
      if (tz) {
        lines.push(`DTEND;TZID=${tz}:${formatICSDateLocal(event.end_time, tz)}`);
      } else {
        lines.push(`DTEND:${formatICSDateUTC(event.end_time)}`);
      }
    }
    // RRULE for recurring events (from enrichment)
    if (event.rrule) {
      lines.push(`RRULE:${event.rrule}`);
    }
    lines.push(`SUMMARY:${escapeICS(event.title)}`);
    if (event.location) {
      lines.push(`LOCATION:${escapeICS(event.location)}`);
    }
    // Build description: original + curator notes
    let description = event.description || "";
    if (event.notes) {
      description = description
        ? `${description}\n\n--- Curator notes ---\n${event.notes}`
        : event.notes;
    }
    if (description) {
      lines.push(`DESCRIPTION:${escapeICS(description)}`);
    }
    if (event.url) {
      lines.push(`URL:${event.url}`);
    }
    if (event.image_url) {
      lines.push(`ATTACH;FMTTYPE=image/jpeg:${event.image_url}`);
    }
    // Categories from enrichment
    if (event.categories && event.categories.length > 0) {
      lines.push(`CATEGORIES:${event.categories.join(",")}`);
    }
    lines.push("END:VEVENT");
  }

  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}
