// One rule for ICS text values (RFC 5545 §3.3.11), shared by the browser
// download, the my-picks personal feed and validate-feed. The site loads it as
// a classic script and the Deno functions import it for its globalThis side
// effect, so it must stay free of imports and exports. It lives under
// functions/_shared so a Docker-based deploy bundles it with each function.

function escapeICS(text) {
  if (!text) return '';
  return (
    text
      .replace(/\r\n/g, '\n')
      // A bare CR is a line break too; emitting it raw splits the property
      // line and makes the whole feed invalid.
      .replace(/\r/g, '\n')
      .replace(/\\/g, '\\\\')
      .replace(/;/g, '\\;')
      .replace(/,/g, '\\,')
      .replace(/\n/g, '\\n')
  );
}

function unescapeICS(text) {
  if (!text) return '';
  // One pass: "\\n" is a literal backslash followed by "n", not a newline.
  return text.replace(/\\([\\;,nN])/g, (match, escaped) =>
    escaped === 'n' || escaped === 'N' ? '\n' : escaped
  );
}

if (typeof globalThis !== 'undefined') {
  globalThis.escapeICS = escapeICS;
  globalThis.unescapeICS = unescapeICS;
}
