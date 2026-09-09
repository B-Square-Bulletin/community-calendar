'use strict';
// validate-date-tabs.test.js — vitest migration of scripts/validate_date_tabs.js.
//
// WHY: static chrome check for #105 (day-preset tab strip, slider removed)
// plus #106 (Tonight + This-weekend intraday tabs), plus #107 (Custom range
// picker) and #108 (hardening). Same file-content assertions as the original
// node script: they fail in seconds without Chromium if any acceptance
// criterion regresses. Source of truth stays the `Date tabs (#105)` group in
// xmlui/test.html, which fetches served files in the Playwright CI step.
//
// Migration notes: every `check(name, cond)` from scripts/validate_date_tabs.js
// becomes `it(name, () => { expect(cond).toBe(true); })` with the condition
// preserved verbatim. Top-level file reads use `readShipped()` from
// ./load-shipped instead of the script's local fs/path `read()` helper.
// No assertions changed, no behavior added.
//
// NOTE: the brief asked for `require('vitest')` (CommonJS), but vitest 3
// throws "Vitest cannot be imported in a CommonJS module using require()",
// so this file uses ESM `import` (vitest transforms it fine). Everything
// else follows the brief: `readShipped()` for xmlui reads, verbatim
// conditions, verbatim commitBody() extraction logic.
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { readShipped, ROOT } from './load-shipped.js';
function read(p) {
  try { return readShipped(p); } catch { return null; }
}
// Body of the single date commit helper (Globals.xs code-behind): every
// preset tap plus the empty-state reset funnels through commitDatePreset,
// so commit-contract assertions below read the helper body once instead of
// repeating per-button inline sequences.
function commitBody() {
  const g = read('Globals.xs') || '';
  const at = g.indexOf('function commitDatePreset(');
  return at < 0 ? '' : g.substring(at, at + 2500);
}

const main = (() => { try { return readShipped('Main.xmlui'); } catch { return null; } })();
const helpers = (() => { try { return readShipped('helpers.js'); } catch { return null; } })();
const shell = (() => { try { return readShipped('shell.js'); } catch { return null; } })();
const index = (() => { try { return readShipped('index.html'); } catch { return null; } })();
const globals = (() => { try { return readShipped('Globals.xs'); } catch { return null; } })();

describe('tab strip present', () => {
// Tonight/Weekend/Custom arrive in later tickets and must stay untouched here.
  it('main exists', () => { expect(!!main).toBe(true); });
  it('tab strip carries All dates tab', () => { expect(!!main && />All dates</.test(main)).toBe(true); });
  it('tab strip carries Today tab', () => { expect(!!main && />Today</.test(main)).toBe(true); });
  it('tab strip carries Tomorrow tab', () => { expect(!!main && />Tomorrow</.test(main)).toBe(true); });
  it('tab strip carries Next 7 days tab', () => { expect(!!main && />Next 7 days</.test(main)).toBe(true); });
  it('tab strip carries This month tab', () => { expect(!!main && />This month</.test(main)).toBe(true); });
  it('tab strip carries Tonight tab (#106)', () => { expect(!!main && />Tonight</.test(main)).toBe(true); });
  it('tab strip carries This weekend tab (#106)', () => { expect(!!main && />This weekend</.test(main)).toBe(true); });
// Tonight/Weekend landed in #106; Custom arrives in #107 (checked below).
  it('tab strip wraps without horizontal scroll', () => { expect(!!main && /id="dateTabStrip"[\s\S]{0,400}?wrapContent="true"/.test(main)).toBe(true); });
});

describe('slider gone', () => {
  it('no Slider control in markup', () => { expect(!!main && !/<Slider/.test(main)).toBe(true); });
  it('no dateSlider id', () => { expect(!!main && !/dateSlider/.test(main)).toBe(true); });
  it('no sliderRange var', () => { expect(!!main && !/sliderRange/.test(main)).toBe(true); });
  it('no sliderStart var', () => { expect(!!main && !/sliderStart/.test(main)).toBe(true); });
  it('no sliderEnd var', () => { expect(!!main && !/sliderEnd/.test(main)).toBe(true); });
  it('no eventDayRange var', () => { expect(!!main && !/eventDayRange/.test(main)).toBe(true); });
  it('no getEventDayRange wiring', () => { expect(!!main && !/getEventDayRange/.test(main)).toBe(true); });
  it('no formatDayOffset wiring', () => { expect(!!main && !/formatDayOffset/.test(main)).toBe(true); });
  it('no day-offset base feeding the list', () => { expect(!!main && !/_dateRangeBase/.test(main)).toBe(true); });
  it('no filterByDayWindow wiring', () => { expect(!!main && !/filterByDayWindow/.test(main)).toBe(true); });
  it('no filterByDayRange wiring', () => { expect(!!main && !/filterByDayRange/.test(main)).toBe(true); });
  it('Globals.xs getPagedEvents takes no date params', () => { expect(!!globals && /function getPagedEvents\(events, term, startIndex, pageSize, category\)/.test(globals)
  && !/dateStart|dateEnd/.test(globals)).toBe(true); });
  it('helpers.js drops slider helpers', () => { expect(!!helpers && !/window\.filterByDayWindow/.test(helpers)
  && !/window\.filterByDayRange/.test(helpers)
  && !/window\.getEventDayRange/.test(helpers)
  && !/window\.formatDayOffset/.test(helpers)
  && !/window\.dayOffsetToISO/.test(helpers)
  && !/window\._dateRangeBase/.test(helpers)).toBe(true); });
});

describe('single committed window', () => {
  it('one committed window variable feeds the list', () => { expect(!!main && /name="dateFilteredEvents"/.test(main)).toBe(true); });
  it('pager guard reads the same window (not a second filter)', () => { expect(!!main && /moreHasMore\(dateFilteredEvents/.test(main)).toBe(true); });
  it('commit resets paging and scrolls on commit only', () => { expect(!!main && /commitDatePreset\('today'\)/.test(main)
  && /displayStartIndex = 0/.test(commitBody())
  && /scrollRequest = scrollRequest \+ 1/.test(commitBody())).toBe(true); });
});

describe('URL contract', () => {
  it('helpers.js exposes the date-tab seam', () => { expect(!!helpers && /window\.filterByDateWindow/.test(helpers)
  && /window\.dateWindowForPreset/.test(helpers)
  && /window\.syncDateParams/.test(helpers)).toBe(true); });
  it('date commit syncs with history-replace (Back skips filter states)', () => { expect(!!helpers && /window\.replaceDateUrlParams/.test(helpers)
  && /replaceDateUrlParams[\s\S]{0,1200}?replaceState/.test(helpers)
  && /syncDateParams[\s\S]{0,400}?replaceDateUrlParams/.test(helpers)).toBe(true); });
  it('shell.js seeds the date preset before first paint', () => { expect(!!shell && /initialDatePreset/.test(shell)).toBe(true); });
  it('date-windows engine loads before shell boots', () => { expect(!!index && index.includes('date-windows.js')).toBe(true); });
});

describe('intraday tabs', () => {
  it('tonight commits via the engine with paging reset, scroll, and URL sync', () => { expect(!!main && /commitDatePreset\('tonight'\)/.test(main)
  && /dateWindowForPreset/.test(commitBody())
  && /displayStartIndex = 0/.test(commitBody())
  && /syncDateParams/.test(commitBody())).toBe(true); });
  it('weekend commits via the engine with paging reset, scroll, and URL sync', () => { expect(!!main && /commitDatePreset\('weekend'\)/.test(main)
  && /dateWindowForPreset/.test(commitBody())
  && /displayStartIndex = 0/.test(commitBody())
  && /syncDateParams/.test(commitBody())).toBe(true); });
  it('intraday tabs show pressed state when active', () => { expect(!!main && /datePreset === 'tonight' && !customOpen \? 'solid' : 'outlined'/.test(main)
  && /datePreset === 'weekend' && !customOpen \? 'solid' : 'outlined'/.test(main)).toBe(true); });
  it('helpers.js date-tab presets derive from the engine canonical list (single source)', () => { expect(!!helpers && /window\.DATE_TAB_PRESETS[\s\S]{0,300}?window\.DATE_PRESETS/.test(helpers)
  && /DATE_TAB_PRESETS/.test(helpers)).toBe(true); });
  it('shell.js boot seed derives the honored set from the engine list plus its alias map', () => { expect(!!shell && /window\.DATE_PRESETS/.test(shell) && /window\.DATE_PRESET_ALIASES/.test(shell)
  && /HONORED/.test(shell)).toBe(true); });
  it('this month commits and boots as ?date=thismonth (#103 contract)', () => { expect(!!main && /commitDatePreset\('thismonth'\)/.test(main)
  && /datePreset === 'thismonth' && !customOpen \? 'solid' : 'outlined'/.test(main)
  && !!helpers && /DATE_PRESET_ALIASES/.test(helpers)
  && !!shell && /DATE_PRESET_ALIASES/.test(shell)).toBe(true); });
});

describe('composition', () => {
  it('category counts computed after date filtering', () => { expect(!!main && /getActiveCategories\(dateFilteredEvents\)/.test(main)).toBe(true); });
  it('picks view ignores the window', () => { expect(!!main && (() => {
    const picksBlock = (main.match(/viewMode === 'picks'[\s\S]*?(?=<\/VStack>)/g) || []).join('\n');
    return !/dateWindow|datePreset|dateFilteredEvents/.test(picksBlock);
  })()).toBe(true); });
});

describe('custom picker', () => {
  it('tab strip carries the Custom tab (#107)', () => { expect(!!main && />Custom</.test(main)).toBe(true); });
  it('custom tab shows pressed state when active', () => { expect(!!main && /datePreset === 'custom' \|\| customOpen/.test(main)).toBe(true); });
  it('custom range picker present in range mode with auto-commit on second click', () => { expect(!!main && /<DatePicker[\s\S]{0,600}?mode="range"/.test(main)
  && /<DatePicker[\s\S]{0,1200}?confirmRangeSelection="false"/.test(main)).toBe(true); });
  it('custom picker uses date-only format plus the city timezone', () => { expect(!!main && /<DatePicker[\s\S]{0,1200}?dateFormat="yyyy-MM-dd"/.test(main)
  && /<DatePicker[\s\S]{0,1200}?timeZone=/.test(main)).toBe(true); });
  it('custom picker disables past dates with today as the minimum', () => { expect(!!main && /<DatePicker[\s\S]{0,1600}?disabledDates=/.test(main)
  && /<DatePicker[\s\S]{0,1600}?startDate=/.test(main)).toBe(true); });
  it('custom picker offers only forward presets (no built-in backward keys)', () => { expect(!!main && /<DatePicker[\s\S]{0,1600}?presets=/.test(main)
  && !/last7Days|last30Days|thisMonth|lastMonth/.test(main)).toBe(true); });
  it('custom picker hides the preset sidebar (ranges live on the tab strip)', () => { expect(!!main && /<DatePicker[\s\S]{0,1600}?showPresets="false"/.test(main)).toBe(true); });
  it('custom picker carries the in-box calendar glyph (plain adornment, opens the popup)', () => { expect(!!main && (() => {
    let config = null;
    try { config = fs.readFileSync(path.join(ROOT, 'config.json'), 'utf8'); } catch { return false; }
    const at = main.indexOf('<DatePicker');
    if (at < 0) return false;
    const picker = main.substring(at, at + 1600);
    const m = picker.match(/endIcon="([^"]+)"/);
    return !!m && config.includes('"icon.' + m[1] + '"');
  })()).toBe(true); });
  it('custom confirm commits once via the engine with paging reset, scroll, and canonical link', () => { expect(!!main && /dateWindowForCustom\(/.test(main)
  && /datePreset = 'custom'[\s\S]{0,500}?displayStartIndex = 0/.test(main)
  && /datePreset = 'custom'[\s\S]{0,600}?syncCustomParams/.test(main)).toBe(true); });
  it('horizon overrun renders the truncation label below the tabs (single copy in the engine)', () => { expect(!!main && /dateTruncationLabel/.test(main)
  && /window\.dateTruncationText\(customWindow\)/.test(main)
  && (() => {
    const eng = read('date-windows.js') || '';
    return /Showing through/.test(eng) && /calendar currently ends there/.test(eng);
  })()).toBe(true); });
  it('helpers.js exposes the custom seam', () => { expect(!!helpers && /window\.dateWindowForCustom/.test(helpers)
  && /window\.syncCustomParams/.test(helpers)
  && /window\.customForwardPresets/.test(helpers)
  && /window\.todayDateOnly/.test(helpers)).toBe(true); });
  it('helpers.js custom seam commits with history-replace and canonical from/to only', () => { expect(!!helpers && /syncCustomParams[\s\S]{0,400}?replaceDateUrlParams/.test(helpers)
  && /replaceDateUrlParams[\s\S]{0,1200}?replaceState/.test(helpers)).toBe(true); });
  it('shell.js boot seed honors the custom from/to pair with clamp rewrite', () => { expect(!!shell && /from/.test(shell) && /initialDatePreset = 'custom'/.test(shell)).toBe(true); });
});

describe('hardening', () => {
  it('tab strip carries a heading for the empty-reset focus target', () => { expect(!!main && /id="dateTabHeading"/.test(main)).toBe(true); });
  it('empty window reads No events {label} with a one-tap Next 7 reset', () => { expect(!!main && /No events /.test(main)
  && /window\.dateWindowLabel\(datePreset\)/.test(main)
  && />Show next 7 days</.test(main)).toBe(true); });
  it('reset commits Next 7 with paging reset, URL sync, and heading focus but no scroll', () => { expect(!!main && (() => {
    const at = main.indexOf('Show next 7 days');
    if (at < 0) return false;
    const handler = main.substring(Math.max(0, at - 900), at);
    return /commitDatePreset\('next7'/.test(handler)
      && /focusDateTabHeading/.test(handler)
      && !/scrollRequest/.test(handler)
      && /displayStartIndex = 0/.test(commitBody())
      && /syncDateParams/.test(commitBody());
  })()).toBe(true); });
  it('helpers.js exposes the hardening seam', () => { expect(!!helpers && /window\.dateWindowLabel/.test(helpers)
  && /window\.dateTruncationText/.test(helpers)
  && /window\.focusDateTabHeading/.test(helpers)).toBe(true); });
  it('preset commits surface the truncation label at the horizon', () => { expect(!!main && /commitDatePreset\('today'\)/.test(main)
  && /dateTruncationText/.test(commitBody())
  && /horizonEnd/.test(helpers) && /getToDate/.test(helpers)).toBe(true); });
  it('shell.js boot seed restores the truncation label at the horizon', () => { expect(!!shell && /initialDateTruncationLabel/.test(shell)
  && /horizonEnd: window\.toDate/.test(shell)).toBe(true); });
  it('tab strip shows identically in the embed (no embed gate)', () => { expect(!!main && (() => {
    const at = main.indexOf('id="dateTabStrip"');
    if (at < 0) return false;
    return !/window\.embed/.test(main.substring(Math.max(0, at - 600), at));
  })()).toBe(true); });
  it('city stays a push while date stays a replace (Back leaves)', () => { expect(!!shell && /selectCity[\s\S]{0,300}?pushState/.test(shell)
  && /replaceDateUrlParams[\s\S]{0,1200}?replaceState/.test(helpers)
  && /syncDateParams[\s\S]{0,400}?replaceDateUrlParams/.test(helpers)
  && /syncCustomParams[\s\S]{0,400}?replaceDateUrlParams/.test(helpers)).toBe(true); });
  it('date sync preserves embed; All clears only date keys', () => { expect(!!helpers && (() => {
    const r = helpers.indexOf('window.replaceDateUrlParams');
    const d = helpers.indexOf('window.syncDateParams');
    const c = helpers.indexOf('window.syncCustomParams');
    if (r < 0 || d < 0 || c < 0) return false;
    const rb = helpers.substring(r, r + 1200);
    const db = helpers.substring(d, d + 400);
    const cb = helpers.substring(c, c + 400);
    return /replaceDateUrlParams/.test(db) && /replaceDateUrlParams/.test(cb)
      && !/delete\('embed'\)/.test(rb)
      && /delete\('date'\)/.test(rb) && /delete\('from'\)/.test(rb) && /delete\('to'\)/.test(rb)
      && !/delete\('(city|search|category|embed|mode|images|cards)'\)/.test(rb);
  })()).toBe(true); });
});

describe('single commit path', () => {
  it('code-behind exposes one shared date commit helper', () => { expect(!!globals && /function commitDatePreset\(/.test(globals)).toBe(true); });
  it('commit helper uses no var-in-function declarations (XMLUI rejects them)', () => { expect(!!globals && !/^\s*var\s+\w/m.test(commitBody())).toBe(true); });
  it('every preset tab routes through the shared commit helper', () => { expect(!!main && ['all', 'today', 'tonight', 'tomorrow', 'weekend', 'next7', 'thismonth'].every(function(k) {
    return main.includes("commitDatePreset('" + k + "'");
  })).toBe(true); });
  it('no inline engine commits remain in markup (single path only)', () => { expect(!!main && !/dateWindowForPreset\('/.test(main)).toBe(true); });
  it('no inline preset assignments remain in markup (helper owns the commit)', () => { expect(!!main && ['all', 'today', 'tonight', 'tomorrow', 'weekend', 'next7', 'thismonth'].every(function(k) {
    // The Custom confirm keeps its own from/to path (syncCustomParams);
    // unifying it rides prio-70. Only the seven preset keys must be gone.
    return !main.includes("datePreset = '" + k + "'");
  })).toBe(true); });
});

describe('single window-resolution path', () => {
  it('engine owns the single truncation copy plus a window formatter', () => { expect((() => {
    const eng = read('date-windows.js') || '';
    return /TRUNCATION/.test(eng)
      && /truncationLabelForWindow/.test(eng)
      && /calendar currently ends there/.test(eng);
  })()).toBe(true); });
  it('helpers preset+custom resolvers share one opts builder', () => { expect((() => {
    const at = (helpers || '').indexOf('window.dateWindowOpts');
    if (at < 0) return false;
    const pb = (helpers || '').indexOf('window.dateWindowForPreset');
    const cb = (helpers || '').indexOf('window.dateWindowForCustom');
    if (pb < 0 || cb < 0) return false;
    const tail = helpers.substring(at, at + 300);
    if (!/getCityTimezone/.test(tail) || !/getToDate/.test(tail)) return false;
    return /dateWindowOpts\(\)/.test(helpers.substring(pb, pb + 900))
      && /dateWindowOpts\(\)/.test(helpers.substring(cb, cb + 900));
  })()).toBe(true); });
  it('helpers truncation text delegates to the engine formatter (one copy)', () => { expect(!!helpers && /window\.dateTruncationText/.test(helpers)
  && /truncationLabelForWindow/.test(helpers)).toBe(true); });
  it('custom confirm routes truncation through dateTruncationText (no inline copy)', () => { expect(!!main && (() => {
    const at = main.indexOf('<DatePicker');
    if (at < 0) return false;
    const handler = main.substring(at, at + 2200);
    return /dateTruncationText/.test(handler)
      && !/Showing through/.test(handler);
  })()).toBe(true); });
  it('shell boot seed resolves the preset-only path via decodeDateParams (one resolver)', () => { expect(!!shell && !/resolveDatePreset\(key/.test(shell)
  && /decodeDateParams\(\{ date: key/.test(shell)).toBe(true); });
  it('shell boot seed routes truncation through the shared formatter (no hand-rolled copy)', () => { expect(!!shell && /truncationLabelForWindow|dateTruncationText/.test(shell)
  && !/Showing through '/.test(shell)).toBe(true); });
});

describe('committed window object', () => {
  it('date list filters through the window-object form', () => { expect(!!main && /filterByDateWindow\(processedEvents,\s*\{start:\s*dateWindowStart,\s*end:\s*dateWindowEnd\}/.test(main)).toBe(true); });
  it('custom confirm resolves and syncs through the window-object form', () => { expect(!!main && (() => {
    const at = main.indexOf('<DatePicker');
    if (at < 0) return false;
    const handler = main.substring(at, at + 2200);
    return /dateWindowForCustom\(val\)/.test(handler)
      && /syncCustomParams\(customWindow\)/.test(handler)
      && !/dateWindowForCustom\(val && val\.from/.test(handler)
      && !/syncCustomParams\(customWindow\.from/.test(handler);
  })()).toBe(true); });
  it('helpers window seams accept the object form (with positional fallback)', () => { expect(!!helpers && /window\.dateWindowForCustom = function\(rangeOrFrom/.test(helpers)
  && /window\.syncCustomParams = function\(rangeOrFrom/.test(helpers)
  && /function filterByDateWindow\(events, windowOrStartISO/.test(helpers)).toBe(true); });
});

describe('custom affordance', () => {
  it('custom flow tracks an explicit UI-only open flag seeded from boot', () => { expect(!!main && /var\.customOpen="\{window\.initialDatePreset === 'custom'\}"/.test(main)).toBe(true); });
  it('custom tab opens the flow UI-only without committing a window', () => { expect(!!main && (() => {
    const at = main.indexOf('>Custom<');
    if (at < 0) return false;
    const handler = main.substring(Math.max(0, at - 400), at);
    return /customOpen = true/.test(handler)
      && !/datePreset = 'custom'/.test(handler);
  })()).toBe(true); });
  it('custom picker row mounts only while the custom flow is open', () => { expect(!!main && /id="customPickerRow"[\s\S]{0,200}?when="\{customOpen\}"/.test(main)).toBe(true); });
  it('custom picker carries an accessible label plus a placeholder', () => { expect(!!main && /<DatePicker[\s\S]{0,1600}?label="Custom date range"/.test(main)
  && /<DatePicker[\s\S]{0,1600}?placeholder=/.test(main)).toBe(true); });
  it('shared commit helper closes the custom flow (no stale range display)', () => { expect(!!globals && /customOpen = false/.test(commitBody())).toBe(true); });
  it('custom tab reads pressed while the custom flow is open (not only after commit)', () => { expect(!!main && (() => {
    const at = main.indexOf('>Custom</');
    if (at < 0) return false;
    const open = main.lastIndexOf('<Button', at);
    if (open < 0) return false;
    return /variant="\{[^"]*customOpen/.test(main.substring(open, at));
  })()).toBe(true); });
  it("exactly one tab pressed at a time: non-custom tabs yield while the custom flow is open", () => { expect(!!main && (() => {
    const m = main.match(/&& !customOpen \? 'solid' : 'outlined'/g) || [];
    return m.length === 7;
  })()).toBe(true); });
  it('custom tab opens the popup via the click seam (focus() only selects text)', () => { expect(!!main && (() => {
    const at = main.indexOf('>Custom</');
    if (at < 0) return false;
    const open = main.lastIndexOf('<Button', at);
    if (open < 0) return false;
    const el = main.substring(open, at);
    return /window\.openCustomPicker\(\)/.test(el)
      && !/\.focus\(\)/.test(el);
  })()).toBe(true); });
  it('no redundant picker trigger survives beside the Custom tab', () => { expect(!!main && !/Choose dates/.test(main)).toBe(true); });
  it('helpers.js exposes the picker-open seam used by the trigger', () => { expect(!!helpers && /window\.openCustomPicker = function/.test(helpers)).toBe(true); });
});
