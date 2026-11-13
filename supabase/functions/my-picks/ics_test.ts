// The shared ICS text rule (#251): a title holding a bare carriage return must
// not split a property line, and the personal feed must render the same text
// as the browser download and the events.json artifact.
import { generateICS } from "./ics.ts";

const { escapeICS, unescapeICS } = globalThis as any;

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

const PICK = {
  id: 1,
  title: "Concert",
  start_time: "2030-10-31T19:00:00Z",
  end_time: null,
  location: null,
  description: null,
  url: null,
  image_url: null,
  city: "bloomington",
  rrule: null,
  notes: null,
  categories: null,
  created_at: "2026-01-02T03:04:05Z",
};

Deno.test("a bare carriage return cannot split a feed line", () => {
  const ics = generateICS([{ ...PICK, title: "Fright\rNight" }], "My Picks", {});

  assert(ics.includes("SUMMARY:Fright\\nNight"), `unexpected summary: ${ics}`);
  for (const line of ics.split("\r\n")) {
    assert(!/[\r\n]/.test(line), `raw line break inside: ${JSON.stringify(line)}`);
  }
});

Deno.test("browser, personal feed and JSON artifact share one text", () => {
  const artifactTitle = "Fright, Night\nPart 2"; // what events.json stores
  const icsText = "Fright\\, Night\\nPart 2"; // the same value inside the feed

  assert(escapeICS(artifactTitle) === icsText, "browser/feed escape differs");
  assert(unescapeICS(icsText) === artifactTitle, "feed unescape differs");
});
