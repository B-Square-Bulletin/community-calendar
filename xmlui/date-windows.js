// date-windows.js — pure city-timezone date-window engine + URL codec.
//
// Ticket #104: no UI, feed, scraper, prefetch, or backend change. This file
// has no dependencies (only Intl/Date) and no side effects beyond exporting
// globals, so later tickets (#105+) can call it from Main.xmlui bindings.
// Tested in xmlui/test.html ("Date windows (#104)" group) over a stubbed
// clock (explicit `now`) and a stubbed city timezone (`timeZone`).
//
// Vocabulary (CONTEXT.md): a Preset resolves to an absolute [start, end)
// Date window in the city timezone. Clamping moves a stale custom start
// forward to today (with URL rewrite); truncation cuts a window at the
// Horizon and labels it; Custom carries exact dates, rolling presets stay
// evergreen.
(function () {
  'use strict';

  // Maximum custom-window length in wall-clock days.
  var MAX_WINDOW_DAYS = 180;

  // Canonical preset keys. Rolling presets encode as ?date=<key>; Custom
  // encodes as an exact ?from=yyyy-MM-dd&to=yyyy-MM-dd pair with no preset
  // key; All strips every date key. This list is the single source of truth
  // for preset keys (prio-80): helpers.js DATE_TAB_PRESETS and the shell
  // boot HONORED set both derive from window.DATE_PRESETS, so adding a
  // preset means editing this list only. Legacy read aliases live in
  // DATE_PRESET_ALIASES next to it — the one place the alias decision is
  // documented — and resolve/decode normalize through it.
  var DATE_PRESETS = ['all', 'today', 'tonight', 'tomorrow', 'weekend', 'next7', 'thismonth'];

  // Legacy read fallback: pre-rename links encoded ?date=month; the
  // canonical key per the #103 URL contract is ?date=thismonth. Only
  // thismonth ever encodes; month decodes.
  var DATE_PRESET_ALIASES = { month: 'thismonth' };

  var DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

  function isKnownPreset(preset) {
    return DATE_PRESETS.indexOf(preset) >= 0;
  }

  // Minutes east of UTC for `timeZone` at the absolute instant `utcMs`,
  // derived from Intl so DST transitions resolve by wall-clock.
  function tzOffsetMs(timeZone, utcMs) {
    var dtf = new Intl.DateTimeFormat('en-US', {
      timeZone: timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    });
    var parts = dtf.formatToParts(new Date(utcMs));
    var v = {};
    parts.forEach(function (p) { v[p.type] = p.value; });
    var hour = v.hour === '24' ? '00' : v.hour;
    var asUtc = Date.UTC(+v.year, +v.month - 1, +v.day, +hour, +v.minute, +v.second);
    return asUtc - utcMs;
  }

  // Absolute instant (ms) of a wall-clock time in `timeZone`. Two-pass
  // offset resolution so the days around a DST transition land on the
  // correct side of the jump.
  function zonedTimeToUtcMs(y, mo, d, h, mi, timeZone) {
    var guess = Date.UTC(y, mo - 1, d, h, mi, 0);
    var off = tzOffsetMs(timeZone, guess);
    var utc = guess - off;
    var off2 = tzOffsetMs(timeZone, utc);
    if (off2 !== off) {
      utc = guess - off2;
    }
    return utc;
  }

  function cityParts(nowMs, timeZone) {
    var parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
      weekday: 'short'
    }).formatToParts(new Date(nowMs));
    var v = {};
    parts.forEach(function (p) { v[p.type] = p.value; });
    var wd = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }[v.weekday];
    return { y: +v.year, mo: +v.month, d: +v.day, wd: wd };
  }

  function addDays(y, mo, d, n) {
    var shifted = new Date(Date.UTC(y, mo - 1, d) + n * 86400000);
    return { y: shifted.getUTCFullYear(), mo: shifted.getUTCMonth() + 1, d: shifted.getUTCDate() };
  }

  function midnightMs(y, mo, d, timeZone) {
    return zonedTimeToUtcMs(y, mo, d, 0, 0, timeZone);
  }

  function toISO(ms) {
    return new Date(ms).toISOString();
  }

  function toMs(value) {
    if (value == null) return null;
    if (typeof value === 'number') return value;
    var ms = new Date(value).getTime();
    return isNaN(ms) ? null : ms;
  }

  function parseDateOnly(s) {
    if (typeof s !== 'string') return null;
    var m = DATE_RE.exec(s);
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    // Round-trip through the calendar so 2026-02-30 is rejected.
    var roundTrip = new Date(Date.UTC(y, mo - 1, d));
    if (roundTrip.getUTCFullYear() !== y || roundTrip.getUTCMonth() !== mo - 1 || roundTrip.getUTCDate() !== d) {
      return null;
    }
    return { y: y, mo: mo, d: d, iso: s };
  }

  function emptyWindow(preset) {
    return { preset: preset, start: null, end: null, startTimeOnly: false, truncated: false };
  }

  // Cut `endMs` at the horizon; never move it earlier than `startMs`.
  function applyHorizon(startMs, endMs, horizonMs) {
    if (horizonMs == null || endMs <= horizonMs) {
      return { endMs: endMs, truncated: false };
    }
    return { endMs: Math.max(startMs, horizonMs), truncated: true };
  }

  // Single truncation copy (#108, prio-70 dedup): every committed-window
  // label below the tabs reads
  // `Showing through {day} — the calendar currently ends there.` where
  // {day} is the inclusive last day. helpers.js dateTruncationText, the
  // Main.xmlui custom confirm, and the shell boot seed all route through
  // truncationLabelForWindow, so this prefix/suffix pair is the one place
  // the copy lives. date-windows.js owns it (not helpers.js) because the
  // shell boot seed runs before helpers.js loads (index.html injects the
  // engine scripts after boot) while date-windows.js is already present.
  var TRUNCATION_LABEL_PREFIX = 'Showing through ';
  var TRUNCATION_LABEL_SUFFIX = ' — the calendar currently ends there.';

  function formatTruncationLabel(day) {
    if (!day) return null;
    return TRUNCATION_LABEL_PREFIX + day + TRUNCATION_LABEL_SUFFIX;
  }

  // Null unless `windowRange` overran the prefetch horizon. Names the inclusive last
  // day (the exclusive end instant minus 1ms) in `timeZone`.
  function truncationLabelForWindow(windowRange, timeZone) {
    if (!windowRange || !windowRange.truncated || !windowRange.end) return null;
    try {
      var tz = timeZone || 'UTC';
      var lastMs = new Date(windowRange.end).getTime() - 1;
      if (!isFinite(lastMs)) return null;
      var day = new Intl.DateTimeFormat('en-CA', {
        timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit'
      }).format(new Date(lastMs));
      return formatTruncationLabel(day);
    } catch (e) {
      return null;
    }
  }

  // Move a custom start earlier than today forward to today (Clamping).
  // Preset windows are computed from today and never clamp; only stale
  // Custom ranges (and decoded URLs) do.
  function clampStartToToday(startMs, todayMs) {
    return startMs < todayMs ? todayMs : startMs;
  }

  // Resolve one rolling preset to its absolute window. `opts` carries the
  // stubbed clock (`now`: Date/ms/ISO, default Date.now()), the stubbed
  // city timezone (`timeZone`, default 'UTC'), and the optional Horizon
  // (`horizonEnd`: Date/ms/ISO, no truncation when absent).
  function resolveDatePreset(preset, opts) {
    opts = opts || {};
    var tz = opts.timeZone || 'UTC';
    var nowMs = toMs(opts.now) != null ? toMs(opts.now) : Date.now();
    var horizonMs = toMs(opts.horizonEnd);

    // Legacy read fallback via the single alias map above.
    if (Object.prototype.hasOwnProperty.call(DATE_PRESET_ALIASES, preset)) preset = DATE_PRESET_ALIASES[preset];
    if (preset === 'all' || !isKnownPreset(preset)) {
      return emptyWindow('all');
    }

    var todayParts = cityParts(nowMs, tz);
    var todayMs = midnightMs(todayParts.y, todayParts.mo, todayParts.d, tz);
    var startMs, endMs, startTimeOnly = false;

    if (preset === 'today') {
      var tomorrow = addDays(todayParts.y, todayParts.mo, todayParts.d, 1);
      startMs = todayMs;
      endMs = midnightMs(tomorrow.y, tomorrow.mo, tomorrow.d, tz);
    } else if (preset === 'tonight') {
      // Start-time-only: events qualify by start time in
      // [today 17:00, tomorrow 00:00). 16:59 and all-day events are
      // excluded by the matcher (ticket #106); the engine reports the
      // window plus the flag.
      var tomorrowParts = addDays(todayParts.y, todayParts.mo, todayParts.d, 1);
      startMs = zonedTimeToUtcMs(todayParts.y, todayParts.mo, todayParts.d, 17, 0, tz);
      endMs = midnightMs(tomorrowParts.y, tomorrowParts.mo, tomorrowParts.d, tz);
      startTimeOnly = true;
    } else if (preset === 'tomorrow') {
      var tomorrowStart = addDays(todayParts.y, todayParts.mo, todayParts.d, 1);
      var dayAfterParts = addDays(todayParts.y, todayParts.mo, todayParts.d, 2);
      startMs = midnightMs(tomorrowStart.y, tomorrowStart.mo, tomorrowStart.d, tz);
      endMs = midnightMs(dayAfterParts.y, dayAfterParts.mo, dayAfterParts.d, tz);
    } else if (preset === 'weekend') {
      // [Fri 17:00 incl, Mon 00:00 excl). Mon-Thu resolve to the upcoming
      // weekend, Fri/Sat/Sun to the enclosing one.
      var friDelta = (5 - todayParts.wd + 7) % 7; // days from today to Friday
      var fri, mon;
      if (todayParts.wd >= 1 && todayParts.wd <= 4) {
        fri = addDays(todayParts.y, todayParts.mo, todayParts.d, friDelta);
        mon = addDays(fri.y, fri.mo, fri.d, 3);
      } else if (todayParts.wd === 5) {
        fri = { y: todayParts.y, mo: todayParts.mo, d: todayParts.d };
        mon = addDays(fri.y, fri.mo, fri.d, 3);
      } else if (todayParts.wd === 6) {
        fri = addDays(todayParts.y, todayParts.mo, todayParts.d, -1);
        mon = addDays(fri.y, fri.mo, fri.d, 3);
      } else {
        fri = addDays(todayParts.y, todayParts.mo, todayParts.d, -2);
        mon = addDays(fri.y, fri.mo, fri.d, 3);
      }
      startMs = zonedTimeToUtcMs(fri.y, fri.mo, fri.d, 17, 0, tz);
      endMs = midnightMs(mon.y, mon.mo, mon.d, tz);
    } else if (preset === 'next7') {
      var plus7 = addDays(todayParts.y, todayParts.mo, todayParts.d, 7);
      startMs = todayMs;
      endMs = midnightMs(plus7.y, plus7.mo, plus7.d, tz);
    } else if (preset === 'thismonth') {
      // This-month remainder: today through the end of the month.
      var firstNext = todayParts.mo === 12
        ? { y: todayParts.y + 1, mo: 1, d: 1 }
        : { y: todayParts.y, mo: todayParts.mo + 1, d: 1 };
      startMs = todayMs;
      endMs = midnightMs(firstNext.y, firstNext.mo, firstNext.d, tz);
    }

    var hz = applyHorizon(startMs, endMs, horizonMs);
    return {
      preset: preset,
      start: toISO(startMs),
      end: toISO(hz.endMs),
      startTimeOnly: startTimeOnly,
      truncated: hz.truncated
    };
  }

  // Resolve an exact Custom range. `from`/`to` are yyyy-MM-dd wall-clock
  // dates in the city timezone; the window is [from 00:00, to+1 00:00).
  // End-before-start coerces to the single `from` day on the picker path;
  // the URL-decode path passes {coerceInverted:false} so an inverted pair
  // returns null (ignored per #103: from <= to required, else ignore).
  // Over-long ranges cap at 180 days; past starts clamp to today; ends
  // past the Horizon truncate. Returns null when either date is missing
  // or invalid.
  function resolveCustomRange(from, to, opts) {
    opts = opts || {};
    var tz = opts.timeZone || 'UTC';
    var nowMs = toMs(opts.now) != null ? toMs(opts.now) : Date.now();
    var horizonMs = toMs(opts.horizonEnd);

    var fromParts = parseDateOnly(from);
    var toParts = parseDateOnly(to);
    if (!fromParts || !toParts) return null;

    var todayParts = cityParts(nowMs, tz);
    var todayMs = midnightMs(todayParts.y, todayParts.mo, todayParts.d, tz);

    var startMs = midnightMs(fromParts.y, fromParts.mo, fromParts.d, tz);
    var endDay = addDays(toParts.y, toParts.mo, toParts.d, 1);
    var endMs = midnightMs(endDay.y, endDay.mo, endDay.d, tz);

    if (endMs <= startMs) {
      // Inverted pair on the URL path is ignored (null); the picker path
      // keeps the single-`from`-day coercion.
      if (opts && opts.coerceInverted === false) return null;
      // Inverted or zero-length range coerces to the single `from` day.
      var next = addDays(fromParts.y, fromParts.mo, fromParts.d, 1);
      endMs = midnightMs(next.y, next.mo, next.d, tz);
    }

    // 180-day cap, measured in wall-clock days from `from`.
    var capDay = addDays(fromParts.y, fromParts.mo, fromParts.d, MAX_WINDOW_DAYS);
    var capMs = midnightMs(capDay.y, capDay.mo, capDay.d, tz);
    if (endMs > capMs) {
      endMs = capMs;
    }

    var clamped = false;
    var clampedStart = clampStartToToday(startMs, todayMs);
    if (clampedStart !== startMs) {
      clamped = true;
      startMs = clampedStart;
      if (endMs <= startMs) {
        var sNext = new Date(startMs + 86400000);
        var sd = { y: sNext.getUTCFullYear(), mo: sNext.getUTCMonth() + 1, d: sNext.getUTCDate() };
        endMs = midnightMs(sd.y, sd.mo, sd.d, tz);
      }
    }

    var hz = applyHorizon(startMs, endMs, horizonMs);
    return {
      preset: 'custom',
      from: clamped ? isoDateInTz(startMs, tz) : fromParts.iso,
      to: null, // filled below
      start: toISO(startMs),
      end: toISO(hz.endMs),
      startTimeOnly: false,
      truncated: hz.truncated,
      clamped: clamped
    };
  }

  function isoDateInTz(utcMs, timeZone) {
    var parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: timeZone, year: 'numeric', month: '2-digit', day: '2-digit'
    }).format(new Date(utcMs));
    return parts; // en-CA yields yyyy-MM-dd
  }

  // Fill the canonical `to` (inclusive last day) on a custom resolution.
  function withToFields(res, timeZone) {
    if (!res) return res;
    var endMs = new Date(res.end).getTime();
    // `end` is exclusive midnight; the inclusive last day is end - 1ms.
    res.to = isoDateInTz(endMs - 1, timeZone);
    return res;
  }

  // Encode a selection to URL params. `sel` is {preset} for rolling
  // presets, or {preset:'custom', from, to} for Custom. All encodes to no
  // keys (All-strip). Returns a plain {key: value} object.
  function encodeDateParams(sel) {
    sel = sel || {};
    if (sel.preset === 'custom') {
      if (parseDateOnly(sel.from) && parseDateOnly(sel.to)) {
        return { from: sel.from, to: sel.to };
      }
      return {};
    }
    if (sel.preset && sel.preset !== 'all' && isKnownPreset(sel.preset)) {
      return { date: sel.preset };
    }
    return {};
  }

  function readParams(params) {
    if (!params) return {};
    if (typeof params.get === 'function') {
      var out = {};
      ['date', 'from', 'to'].forEach(function (k) {
        var v = params.get(k);
        if (v != null) out[k] = v;
      });
      return out;
    }
    return { date: params.date, from: params.from, to: params.to };
  }

  // Decode URL params to a window. The Custom pair wins when both dates
  // are valid; partial/invalid pairs are ignored entirely so a valid
  // ?date= preset is still honored; unknown preset keys fall back to
  // All; a clamped past start reports `rewritten: true` with corrected
  // `from`/`to` so the caller can rewrite the URL for stable reload.
  function decodeDateParams(params, opts) {
    opts = opts || {};
    var tz = opts.timeZone || 'UTC';
    var q = readParams(params);

    if (q.from != null && q.to != null) {
      var customOpts = Object.assign({}, opts, { coerceInverted: false });
      var res = withToFields(resolveCustomRange(q.from, q.to, customOpts), tz);
      if (res) {
        res.rewritten = !!res.clamped;
        delete res.clamped;
        return res;
      }
      // Invalid pair: ignore it entirely and defer to ?date= below.
    }

    if (q.date != null) {
      // Legacy read fallback via the single alias map (see DATE_PRESETS):
      // ?date=month decodes to the canonical thismonth window; only
      // thismonth encodes.
      if (Object.prototype.hasOwnProperty.call(DATE_PRESET_ALIASES, q.date)) q.date = DATE_PRESET_ALIASES[q.date];
      if (isKnownPreset(q.date)) {
        var windowRange = q.date === 'all'
          ? emptyWindow('all')
          : resolveDatePreset(q.date, opts);
        windowRange.rewritten = false;
        return windowRange;
      }
      return Object.assign(emptyWindow('all'), { rewritten: false });
    }

    return Object.assign(emptyWindow('all'), { rewritten: false });
  }

  // Public surface (repo style: bare functions on window).
  var api = {
    DATE_PRESETS: DATE_PRESETS,
    DATE_PRESET_ALIASES: DATE_PRESET_ALIASES,
    MAX_WINDOW_DAYS: MAX_WINDOW_DAYS,
    TRUNCATION_LABEL_PREFIX: TRUNCATION_LABEL_PREFIX,
    TRUNCATION_LABEL_SUFFIX: TRUNCATION_LABEL_SUFFIX,
    formatTruncationLabel: formatTruncationLabel,
    truncationLabelForWindow: truncationLabelForWindow,
    resolveDatePreset: resolveDatePreset,
    resolveCustomRange: function (from, to, opts) {
      var tz = (opts && opts.timeZone) || 'UTC';
      return withToFields(resolveCustomRange(from, to, opts), tz);
    },
    encodeDateParams: encodeDateParams,
    decodeDateParams: decodeDateParams
  };

  if (typeof window !== 'undefined') {
    window.DATE_PRESETS = api.DATE_PRESETS;
    window.DATE_PRESET_ALIASES = api.DATE_PRESET_ALIASES;
    window.MAX_WINDOW_DAYS = api.MAX_WINDOW_DAYS;
    window.TRUNCATION_LABEL_PREFIX = api.TRUNCATION_LABEL_PREFIX;
    window.TRUNCATION_LABEL_SUFFIX = api.TRUNCATION_LABEL_SUFFIX;
    window.formatTruncationLabel = api.formatTruncationLabel;
    window.truncationLabelForWindow = api.truncationLabelForWindow;
    window.resolveDatePreset = api.resolveDatePreset;
    window.resolveCustomRange = api.resolveCustomRange;
    window.encodeDateParams = api.encodeDateParams;
    window.decodeDateParams = api.decodeDateParams;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})();
