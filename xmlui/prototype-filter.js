// PROTOTYPE — throwaway, branch prototype/date-filter-variants, NEVER merge.
// Supports the ?variant=A|B|C filter UX prototypes (wayfinder map #95).
// Preset semantics locked in ticket #98; commit contract locked in #100:
// discrete selections commit immediately, continuous gestures coalesce.
(function () {
  var MS_PER_DAY = 86400000;

  function baseMidnight() {
    if (window._dateRangeBase) return new Date(window._dateRangeBase.getTime());
    var d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function isoOf(offset) {
    var d = new Date(baseMidnight().getTime() + offset * MS_PER_DAY);
    var m = d.getMonth() + 1, day = d.getDate();
    return d.getFullYear() + '-' + (m < 10 ? '0' : '') + m + '-' + (day < 10 ? '0' : '') + day;
  }

  // Day-offset window for a named preset, honoring the #98 semantics:
  // tonight from 5pm city-time, weekend Fri-5pm..Sun-night, rolling 7d,
  // remainder-of-month, custom clamped to today..horizon (clamping lives
  // in protoRangeToOffsets). Returns {start, end, label, key}.
  window.protoPreset = function (name) {
    var b = baseMidnight(), dow = b.getDay(); // 0 = Sunday
    switch (name) {
      case 'today':
        return { start: 0, end: 0, label: 'Today', key: 'today' };
      case 'tonight':
        // Day-granular pipeline: tonight rides on today's window. The 5pm
        // cutoff needs an intraday filter stage the implementer adds; the
        // prototype surfaces this honestly in the state line.
        return { start: 0, end: 0, label: 'Tonight', key: 'tonight', intraday: 'from 5pm' };
      case 'tomorrow':
        return { start: 1, end: 1, label: 'Tomorrow', key: 'tomorrow' };
      case 'weekend': {
        var s, e;
        if (dow === 5) { s = 0; e = 2; }        // Friday -> Fri..Sun
        else if (dow === 6) { s = -1; e = 1; }  // Saturday -> Fri..Sun
        else if (dow === 0) { s = -2; e = 0; }  // Sunday -> Fri..Sun
        else { s = 5 - dow; e = 7 - dow; }      // Mon..Thu -> upcoming Fri..Sun
        return { start: s, end: e, label: 'This weekend', key: 'weekend' };
      }
      case 'next7':
        return { start: 0, end: 6, label: 'Next 7 days', key: 'next7' };
      case 'thismonth': {
        var last = new Date(b.getFullYear(), b.getMonth() + 1, 0).getDate();
        return { start: 0, end: last - b.getDate(), label: 'This month', key: 'thismonth' };
      }
      default:
        return { start: null, end: null, label: 'All dates', key: 'all' };
    }
  };

  // Reverse-map a committed (start, end) window to a preset key for strip
  // highlighting; returns 'custom', 'all', or the preset key.
  window.protoValueFor = function (start, end) {
    if (start === null || start === undefined) return 'all';
    var keys = ['today', 'tonight', 'tomorrow', 'weekend', 'next7', 'thismonth'];
    for (var i = 0; i < keys.length; i++) {
      var p = window.protoPreset(keys[i]);
      if (p.start === start && p.end === end) return keys[i] === 'tonight' ? 'today' : keys[i];
    }
    return 'custom';
  };

  // Human label for the state line: preset name, or Custom range via the
  // app's own day formatter. Null window -> All dates.
  window.protoLabelFor = function (start, end) {
    if (start === null || start === undefined) return 'All dates';
    var key = window.protoValueFor(start, end);
    if (key !== 'custom') {
      var names = { today: 'Today', tomorrow: 'Tomorrow', weekend: 'This weekend', next7: 'Next 7 days', thismonth: 'This month' };
      if (key === 'today' && start === 0 && end === 0) {
        // Ambiguous with tonight (same day window); label the day and let
        // the variant's own state carry the tonight note when it committed it.
        return 'Today';
      }
      return names[key] || 'Today';
    }
    try {
      return 'Custom: ' + window.formatDayOffset(start) + ' – ' + window.formatDayOffset(end);
    } catch (e) {
      return 'Custom range';
    }
  };

  // Forward-looking custom presets for DatePicker `presets` (ISO strings
  // are always accepted by the parser, whatever dateFormat is active).
  window.protoForwardPresets = function () {
    function asRange(name) {
      var p = window.protoPreset(name);
      return { label: p.label, from: isoOf(p.start), to: isoOf(p.end) };
    }
    return [asRange('today'), asRange('tomorrow'), asRange('weekend'), asRange('next7'), asRange('thismonth')];
  };

  function parseLooseDate(v) {
    var m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(v);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
    var d = new Date(v);
    d.setHours(0, 0, 0, 0);
    return d;
  }

  // DatePicker {from, to} -> {start, end} day offsets, start clamped to
  // today per #98 (never a silent empty from a stale start date).
  // Returns null when the range is incomplete; {start:null,end:null} only
  // via protoClearWindow (picker cleared = All dates).
  window.protoRangeToOffsets = function (range) {
    if (!range || !range.from || !range.to) return null;
    var b = baseMidnight().getTime();
    var s = Math.round((parseLooseDate(range.from).getTime() - b) / MS_PER_DAY);
    var e = Math.round((parseLooseDate(range.to).getTime() - b) / MS_PER_DAY);
    if (s < 0) s = 0;
    if (e < s) e = s;
    return { start: s, end: e };
  };

  window.protoClearWindow = function () {
    return { start: null, end: null };
  };
})();
