/** URL policy for validate-feed (GHSA-758r-g4xx-2j8r).
 *
 * The function fetches a caller-supplied URL from the Edge Runtime, so the
 * policy is the SSRF boundary: https on the default port, and a host that is
 * not loopback, private, link-local, CGNAT or cloud metadata.
 *
 * shortcut: hostnames are judged syntactically, with no DNS resolution, so a
 * public name that resolves to a private address still gets fetched. Closing
 * that needs resolve-then-pin (which fetch cannot express) — revisit if this
 * endpoint ever serves non-admins.
 */

export type UrlCheck = { ok: true; url: URL } | { ok: false; error: string };

const BLOCKED_HOST_SUFFIXES = [".localhost", ".local", ".internal", ".home.arpa"];

export function checkFeedUrl(raw: string): UrlCheck {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return { ok: false, error: "Not a valid URL" };
  }

  if (url.protocol !== "https:") {
    return { ok: false, error: "Only https feed URLs are allowed" };
  }
  // A default :443 is normalised away by URL, so any port left is explicit.
  if (url.port !== "") {
    return { ok: false, error: "Only the default https port is allowed" };
  }

  // A fully-qualified name may carry a trailing dot; drop it before matching.
  const host = url.hostname
    .toLowerCase()
    .replace(/^\[(.*)\]$/, "$1")
    .replace(/\.+$/, "");
  if (!host || isNonPublicHost(host)) {
    return { ok: false, error: "That host is not allowed" };
  }

  return { ok: true, url };
}

function isNonPublicHost(host: string): boolean {
  if (host === "localhost") return true;
  if (BLOCKED_HOST_SUFFIXES.some((suffix) => host.endsWith(suffix))) return true;

  if (host.includes(":")) return isNonPublicIPv6(host);
  // URL normalises every IPv4 spelling (1.2.3.4, 0x7f.0.0.1, 2130706433) to a
  // dotted quad, so a numeric host here is a real address.
  if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) return isNonPublicIPv4(host);
  // A single-label name is a LAN name, never a public feed host.
  return !host.includes(".");
}

function isNonPublicIPv4(host: string): boolean {
  const [a, b] = host.split(".").map(Number);
  if (a === 0 || a === 10 || a === 127) return true;
  if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT
  if (a === 169 && b === 254) return true; // link-local, cloud metadata
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 192 && (b === 0 || b === 168)) return true;
  if (a === 198 && (b === 18 || b === 19 || b === 51)) return true;
  if (a === 203 && b === 0) return true;
  if (a >= 224) return true; // multicast, reserved, broadcast
  return false;
}

/** Expand an IPv6 literal into its eight 16-bit groups. */
function ipv6Groups(host: string): number[] {
  const [head, tail] = host.split("::");
  const headGroups = head ? head.split(":") : [];
  const tailGroups = tail ? tail.split(":") : [];
  const fill = tail === undefined ? 0 : 8 - headGroups.length - tailGroups.length;
  return [...headGroups, ...Array(fill).fill("0"), ...tailGroups]
    .map((group) => parseInt(group, 16));
}

function isNonPublicIPv6(host: string): boolean {
  const g = ipv6Groups(host);
  const zeroPrefix = (count: number) => g.slice(0, count).every((v) => v === 0);
  const v4Of = (high: number, low: number) =>
    `${high >> 8}.${high & 255}.${low >> 8}.${low & 255}`;

  if (zeroPrefix(7) && (g[7] === 0 || g[7] === 1)) return true; // :: and ::1
  if ((g[0] & 0xfe00) === 0xfc00) return true; // unique local fc00::/7
  if ((g[0] & 0xffc0) === 0xfe80) return true; // link-local fe80::/10
  if ((g[0] & 0xffc0) === 0xfec0) return true; // deprecated site-local
  if ((g[0] & 0xff00) === 0xff00) return true; // multicast

  // IPv4 in the last 32 bits: ::ffff:7f00:1 (mapped), ::ffff:0:7f00:1
  // (translated), ::7f00:1 (compatible), 64:ff9b::7f00:1 (NAT64). Judge those
  // by the v4 address.
  if (zeroPrefix(4) && (g[4] === 0xffff || g[5] === 0xffff)) {
    return isNonPublicIPv4(v4Of(g[6], g[7]));
  }
  if (zeroPrefix(6)) return isNonPublicIPv4(v4Of(g[6], g[7]));
  if (g[0] === 0x64 && g[1] === 0xff9b && g.slice(2, 6).every((v) => v === 0)) {
    return isNonPublicIPv4(v4Of(g[6], g[7]));
  }
  // 6to4 carries the v4 address in groups 1-2.
  if (g[0] === 0x2002) return isNonPublicIPv4(v4Of(g[1], g[2]));

  return false;
}
