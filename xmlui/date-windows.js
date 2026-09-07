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
  // key; All strips every date key.
  var DATE_PRESETS = ['all', 'today', 'tonight', 'tomorrow', 'weekend', 'next7', 'month'];

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
    var t = new Date(Date.UTC(y, mo - 1, d) + n * 86400000);
    return { y: t.getUTCFullYear(), mo: t.getUTCMonth() + 1, d: t.getUTCDate() };
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
    var t = new Date(value).getTime();
    return isNaN(t) ? null : t;
  }

  function parseDateOnly(s) {
    if (typeof s !== 'string') return null;
    var m = DATE_RE.exec(s);
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    // Round-trip through the calendar so 2026-02-30 is rejected.
    var t = new Date(Date.UTC(y, mo - 1, d));
    if (t.getUTCFullYear() !== y || t.getUTCMonth() !== mo - 1 || t.getUTCDate() !== d) {
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

    if (preset === 'all' || !isKnownPreset(preset)) {
      return emptyWindow('all');
    }

    var c = cityParts(nowMs, tz);
    var todayMs = midnightMs(c.y, c.mo, c.d, tz);
    var startMs, endMs, startTimeOnly = false;

    if (preset === 'today') {
      var tomorrow = addDays(c.y, c.mo, c.d, 1);
      startMs = todayMs;
      endMs = midnightMs(tomorrow.y, tomorrow.mo, tomorrow.d, tz);
    } else if (preset === 'tonight') {
      // Start-time-only: events qualify by start time in
      // [today 17:00, tomorrow 00:00). 16:59 and all-day events are
      // excluded by the matcher (ticket #106); the engine reports the
      // window plus the flag.
      var tomorrowT = addDays(c.y, c.mo, c.d, 1);
      startMs = zonedTimeToUtcMs(c.y, c.mo, c.d, 17, 0, tz);
      endMs = midnightMs(tomorrowT.y, tomorrowT.mo, tomorrowT.d, tz);
      startTimeOnly = true;
    } else if (preset === 'tomorrow') {
      var t1 = addDays(c.y, c.mo, c.d, 1);
      var t2 = addDays(c.y, c.mo, c.d, 2);
      startMs = midnightMs(t1.y, t1.mo, t1.d, tz);
      endMs = midnightMs(t2.y, t2.mo, t2.d, tz);
    } else if (preset === 'weekend') {
      // [Fri 17:00 incl, Mon 00:00 excl). Mon-Thu resolve to the upcoming
      // weekend, Fri/Sat/Sun to the enclosing one.
      var friDelta = (5 - c.wd + 7) % 7; // days from today to Friday
      var fri, mon;
      if (c.wd >= 1 && c.wd <= 4) {
        fri = addDays(c.y, c.mo, c.d, friDelta);
        mon = addDays(fri.y, fri.mo, fri.d, 3);
      } else if (c.wd === 5) {
        fri = { y: c.y, mo: c.mo, d: c.d };
        mon = addDays(fri.y, fri.mo, fri.d, 3);
      } else if (c.wd === 6) {
        fri = addDays(c.y, c.mo, c.d, -1);
        mon = addDays(fri.y, fri.mo, fri.d, 3);
      } else {
        fri = addDays(c.y, c.mo, c.d, -2);
        mon = addDays(fri.y, fri.mo, fri.d, 3);
      }
      startMs = zonedTimeToUtcMs(fri.y, fri.mo, fri.d, 17, 0, tz);
      endMs = midnightMs(mon.y, mon.mo, mon.d, tz);
    } else if (preset === 'next7') {
      var plus7 = addDays(c.y, c.mo, c.d, 7);
      startMs = todayMs;
      endMs = midnightMs(plus7.y, plus7.mo, plus7.d, tz);
    } else if (preset === 'month') {
      // This-month remainder: today through the end of the month.
      var firstNext = c.mo === 12
        ? { y: c.y + 1, mo: 1, d: 1 }
        : { y: c.y, mo: c.mo + 1, d: 1 };
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
  // End-before-start coerces to the single `from` day; over-long ranges
  // cap at 180 days; past starts clamp to today; ends past the Horizon
  // truncate. Returns null when either date is missing or invalid.
  function resolveCustomRange(from, to, opts) {
    opts = opts || {};
    var tz = opts.timeZone || 'UTC';
    var nowMs = toMs(opts.now) != null ? toMs(opts.now) : Date.now();
    var horizonMs = toMs(opts.horizonEnd);

    var f = parseDateOnly(from);
    var t = parseDateOnly(to);
    if (!f || !t) return null;

    var c = cityParts(nowMs, tz);
    var todayMs = midnightMs(c.y, c.mo, c.d, tz);

    var startMs = midnightMs(f.y, f.mo, f.d, tz);
    var endDay = addDays(t.y, t.mo, t.d, 1);
    var endMs = midnightMs(endDay.y, endDay.mo, endDay.d, tz);

    if (endMs <= startMs) {
      // Inverted or zero-length range coerces to the single `from` day.
      var next = addDays(f.y, f.mo, f.d, 1);
      endMs = midnightMs(next.y, next.mo, next.d, tz);
    }

    // 180-day cap, measured in wall-clock days from `from`.
    var capDay = addDays(f.y, f.mo, f.d, MAX_WINDOW_DAYS);
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
      from: clamped ? isoDateInTz(startMs, tz) : f.iso,
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
  // are valid; partial/invalid pairs and unknown preset keys fall back to
  // All; a clamped past start reports `rewritten: true` with corrected
  // `from`/`to` so the caller can rewrite the URL for stable reload.
  function decodeDateParams(params, opts) {
    opts = opts || {};
    var tz = opts.timeZone || 'UTC';
    var q = readParams(params);

    if (q.from != null || q.to != null) {
      var res = (q.from != null && q.to != null)
        ? withToFields(resolveCustomRange(q.from, q.to, opts), tz)
        : null;
      if (res) {
        res.rewritten = !!res.clamped;
        delete res.clamped;
        return res;
      }
      return Object.assign(emptyWindow('all'), { rewritten: false });
    }

    if (q.date != null) {
      if (isKnownPreset(q.date)) {
        var w = q.date === 'all'
          ? emptyWindow('all')
          : resolveDatePreset(q.date, opts);
        w.rewritten = false;
        return w;
      }
      return Object.assign(emptyWindow('all'), { rewritten: false });
    }

    return Object.assign(emptyWindow('all'), { rewritten: false });
  }

  // Public surface (repo style: bare functions on window).
  var api = {
    DATE_PRESETS: DATE_PRESETS,
    MAX_WINDOW_DAYS: MAX_WINDOW_DAYS,
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
    window.MAX_WINDOW_DAYS = api.MAX_WINDOW_DAYS;
    window.resolveDatePreset = api.resolveDatePreset;
    window.resolveCustomRange = api.resolveCustomRange;
    window.encodeDateParams = api.encodeDateParams;
    window.decodeDateParams = api.decodeDateParams;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})();
