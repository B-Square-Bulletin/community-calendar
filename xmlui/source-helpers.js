// source-helpers.js — the one client derivation of source names, source
// ordering, and the active city timezone (#169 review item 11).
//
// WHY this module exists: helpers.js, Card, and Recurring all need the same
// source-name parsing, the aggregator/location ordering helpers.js applies to
// raw rows, and the active city's IANA timezone. Forking those into each module
// let the copies drift. This standalone `window` module owns them once; it is
// loaded before all three (shell.js's loader list, xmlui/test.html,
// tests/js/load-shipped.js, and the node benchmarks).
//
// It is a plain `window`-attached module: no DOM, no network, no engine, so it
// is safe to evaluate before app start and inside the vm harness.
(function () {
  'use strict';

  // The view's structured `source_names` is authoritative; only a raw row
  // without it falls back to splitting the legacy comma-joined `source` string.
  // A human source name may itself contain a comma, so the split would
  // fabricate names (spec amendment L402).
  function uniqueSourceNames(source) {
    if (!source) return [];
    var seen = new Set();
    return source
      .split(',')
      .map(function (s) {
        return s.trim();
      })
      .filter(function (s) {
        if (!s || seen.has(s)) return false;
        seen.add(s);
        return true;
      });
  }

  function eventSourceNames(e) {
    if (e && Array.isArray(e.source_names) && e.source_names.length) {
      var seen = new Set();
      return e.source_names
        .map(function (s) {
          return String(s).trim();
        })
        .filter(function (s) {
          if (!s || seen.has(s)) return false;
          seen.add(s);
          return true;
        });
    }
    return uniqueSourceNames((e && e.source) || '');
  }

  // Aggregators come from source_priority.json (`window._sourcePriority`), the
  // same data helpers.js and scripts/combine_ics.py read. Read lazily, cached by
  // the config array's identity, so a load-order change or a test that swaps
  // `_sourcePriority` cannot leave a stale set.
  var _aggCacheSet = null;
  var _aggCacheSrc = null;
  function aggregatorSet() {
    var src =
      (typeof window !== 'undefined' &&
        window._sourcePriority &&
        window._sourcePriority.aggregators) ||
      [];
    if (_aggCacheSrc !== src) {
      _aggCacheSet = new Set(src);
      _aggCacheSrc = src;
    }
    return _aggCacheSet;
  }

  function normalizeVenueToken(value) {
    return (value || '')
      .toLowerCase()
      .replace(/[^\w\s]/g, ' ')
      .replace(/\b(the|a|an)\b/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function sourceMatchesLocation(source, location) {
    if (!source || !location) return false;
    var normalizedLocation = normalizeVenueToken(location);
    if (!normalizedLocation) return false;
    var candidates = [];
    var raw = (source || '').toLowerCase().trim();
    var normalized = normalizeVenueToken(source);
    if (raw) candidates.push(raw);
    if (normalized && candidates.indexOf(normalized) < 0) candidates.push(normalized);
    return candidates.some(function (candidate) {
      return candidate && normalizedLocation.includes(candidate);
    });
  }

  // Legacy raw-row ordering: aggregators last, then alphabetical, then a source
  // whose name appears in the venue location promoted to the front. Inert on
  // view rows, which already carry a structured, representative-ordered
  // `source_names`.
  function orderSourceNames(names, location) {
    var agg = aggregatorSet();
    var sorted = names.slice().sort(function (a, b) {
      var aAgg = agg.has(a) ? 1 : 0;
      var bAgg = agg.has(b) ? 1 : 0;
      if (aAgg !== bAgg) return aAgg - bAgg;
      return a.localeCompare(b);
    });
    if (location) {
      var authIdx = -1;
      for (var i = 0; i < sorted.length; i++) {
        if (!agg.has(sorted[i]) && sourceMatchesLocation(sorted[i], location)) {
          authIdx = i;
          break;
        }
      }
      if (authIdx > 0) sorted.unshift(sorted.splice(authIdx, 1)[0]);
    }
    return sorted;
  }

  // The IANA timezone for the current city, or undefined to fall back to the
  // browser default.
  function cityTimezone() {
    var w = typeof window !== 'undefined' ? window : null;
    if (w && w.cityFilter && w._cities && w._cities[w.cityFilter]) {
      return w._cities[w.cityFilter].timezone;
    }
    return undefined;
  }

  window.SourceHelpers = {
    uniqueSourceNames: uniqueSourceNames,
    eventSourceNames: eventSourceNames,
    orderSourceNames: orderSourceNames,
    cityTimezone: cityTimezone,
  };
})();
