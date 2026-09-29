// recurring.js — Recurring: the one client authority on the long-running-series
// weekly collapse (#169 / ADR-0017).
//
// A long-running series (an exhibition, a weekly service) is shown once per
// week so the calendar is not buried under repetitions. Recurring owns that
// rule: first occurrence per week, the five-occurrence minimum that decides
// which series qualify, and the `isRecurring` mark. It is a pure function of
// `(events, { now })` — no DOM, no network, no engine — so it is a test seam
// with a deterministic injected clock. helpers.js owns only the pipeline-level
// content-key cache; the rule itself lives here.
//
// It is shipped as a plain `window`-attached module loaded before helpers.js
// and before app start, then applied exactly once at its composition point in
// processEvents (after exclusions and source ordering, before hidden-source
// filtering and the search index). The active city's timezone is read from the
// shared `window.SourceHelpers` module rather than re-derived here (#169 review).
//
// Cockpit note: weeks are anchored to browser-local midnight while the
// time-of-day that identifies a series is computed in the city timezone. That
// mixed-zone quirk predates this extraction and is deliberately unchanged.
(function () {
  'use strict';

  var MIN_OCCURRENCES = 5;

  // Resolve the injected clock: Date | ms | ISO string, defaulting to the real
  // clock for the pipeline call site.
  function resolveNow(value) {
    if (value == null) return new Date();
    if (value instanceof Date) return new Date(value.getTime());
    return new Date(value);
  }

  function timeOfDay(dateStr, tz, cache) {
    if (cache[dateStr]) return cache[dateStr];
    var d = new Date(dateStr);
    var hourOpts = { hour: 'numeric', hour12: false };
    var minuteOpts = { minute: 'numeric' };
    if (tz) {
      hourOpts.timeZone = tz;
      minuteOpts.timeZone = tz;
    }
    var h = String(parseInt(d.toLocaleString('en-US', hourOpts))).padStart(2, '0');
    var m = String(parseInt(d.toLocaleString('en-US', minuteOpts))).padStart(2, '0');
    var result = h + ':' + m;
    cache[dateStr] = result;
    return result;
  }

  // Pure: collapse a long-running series to one occurrence per week.
  function collapse(events, opts) {
    if (!Array.isArray(events) || !events.length) return [];
    opts = opts || {};
    var tz = window.SourceHelpers.cityTimezone();
    var now = resolveNow(opts.now);
    var todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    function weekFromToday(dateStr) {
      var d = new Date(dateStr);
      var eventDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
      var daysDiff = Math.floor((eventDay - todayStart) / (24 * 60 * 60 * 1000));
      return Math.floor(daysDiff / 7);
    }

    var todCache = {};
    function seriesKey(e) {
      return (
        (e.title || '').trim().toLowerCase() +
        '|' +
        (e.location || '').trim().toLowerCase() +
        '|' +
        timeOfDay(e.start_time, tz, todCache)
      );
    }

    // A series qualifies for collapse only when it has enough occurrences.
    var counts = {};
    events.forEach(function (e) {
      var key = seriesKey(e);
      counts[key] = (counts[key] || 0) + 1;
    });

    var seenWeeks = {};
    var result = [];
    events.forEach(function (e) {
      var key = seriesKey(e);
      if ((counts[key] || 0) < MIN_OCCURRENCES) {
        result.push(e);
        return;
      }
      var week = weekFromToday(e.start_time);
      if (!seenWeeks[key]) seenWeeks[key] = {};
      if (!seenWeeks[key][week]) {
        seenWeeks[key][week] = true;
        result.push(Object.assign({}, e, { isRecurring: true }));
      }
    });

    result.sort(function (a, b) {
      return (a.start_time || '').localeCompare(b.start_time || '');
    });
    return result;
  }

  window.Recurring = {
    collapse: collapse,
    MIN_OCCURRENCES: MIN_OCCURRENCES,
  };
})();
