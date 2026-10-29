// Conditional-response helper for the my-picks ICS feed.
//
// The feed is polled on a timer, so an unchanged calendar must cost a 304 and
// no body. The validator is a hash of the exact bytes served, which is why the
// ICS itself must be byte-stable between builds (see the DTSTAMP in ics.ts).

const encoder = new TextEncoder();

// The feed is revalidated on every poll, so it must not be served from a cache
// without asking us first.
export const CACHE_CONTROL = "no-cache, must-revalidate";

async function etagFor(body: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(body));
  return `"${Array.from(new Uint8Array(digest))
    .slice(0, 8)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")}"`;
}

// RFC 9110 allows "*", a comma-separated list, and a weak "W/" prefix.
function notModified(ifNoneMatch: string, etag: string): boolean {
  return ifNoneMatch.split(",").some((tag) => {
    const candidate = tag.trim().replace(/^W\//, "");
    return candidate === "*" || candidate === etag;
  });
}

export async function respondWithICS(
  req: Request,
  ics: string,
  headers: Record<string, string>,
): Promise<Response> {
  const etag = await etagFor(ics);
  const validatedHeaders = { ...headers, ETag: etag, "Cache-Control": CACHE_CONTROL };
  const ifNoneMatch = req.headers.get("If-None-Match");
  if (ifNoneMatch && notModified(ifNoneMatch, etag)) {
    return new Response(null, { status: 304, headers: validatedHeaders });
  }
  return new Response(ics, { headers: validatedHeaders });
}
