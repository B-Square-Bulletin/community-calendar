// boot-decisions.js — pure pre-boot decision functions.
//
// bootShell() in shell.js runs BEFORE helpers.js is injected (engine
// scripts load after), so hostname-to-theme and city-default mappings
// live here in a tiny synchronously-loaded script with no dependencies.
// Loaded by index.html before shell.js and by test.html before its test
// script. Nothing else belongs here.
(function () {
  // Exact BSB host maps to the BSB skin; everything else keeps the
  // default community-calendar theme. Exact match (no subdomain
  // wildcard, no port handling) so local dev and project Pages hosts
  // render the default theme.
  window.getThemeIdForHost = function (hostname) {
    if (hostname === 'calendar.bsquarebulletin.com') {
      return 'b-square-bulletin';
    }
    return 'community-calendar';
  };

  // Single-city boot default: on a host whose City list has exactly one
  // entry, a root visit without ?city= resolves to that City so the
  // calendar loads immediately instead of a one-button picker. Generic
  // (not hardcoded): empty string counts as absent, an explicit
  // non-empty param passes through verbatim (including unknown slugs,
  // so deep-links behave as today), and empty/null/multi-entry lists
  // yield no default (null).
  window.resolveCity = function (cityParam, cityKeys) {
    if (cityParam) {
      return cityParam;
    }
    if (Array.isArray(cityKeys) && cityKeys.length === 1 && cityKeys[0]) {
      return cityKeys[0];
    }
    return null;
  };
})();
