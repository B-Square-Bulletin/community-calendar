'use strict';
// tests/js/load-shipped.js — vm + stub loader for the shipped browser globals.
//
// WHY: date-windows.js / helpers.js attach to `window` and expect
// window._categories, cityFilter, localStorage, etc. This keeps the existing
// bare-node `vm` + stub pattern inside vitest (per grill decision Q2) so the
// shipped sources load with zero changes. Each test file calls loadShipped()
// with its own stubs; vm runs in the current context like scripts/validate_*.js.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..', '..', 'xmlui');

function loadShipped(opts = {}) {
  const win = {
    _categories: [],
    _sourcePriority: { aggregators: [] },
    cityFilter: opts.cityFilter || 'davis',
    _cities: opts.cities || { davis: { timezone: 'America/Los_Angeles' } },
    location: new URL(opts.url || 'https://example.com/?city=davis'),
    history: {
      replaceState(o, t, u) { win.location = new URL(u); },
      pushState(o, t, u) { win.location = new URL(u); },
    },
  };
  global.window = win;
  global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  if (opts.document) global.document = opts.document;

  vm.runInThisContext(fs.readFileSync(path.join(ROOT, 'date-windows.js'), 'utf8'), {
    filename: 'date-windows.js',
  });
  vm.runInThisContext(fs.readFileSync(path.join(ROOT, 'helpers.js'), 'utf8'), {
    filename: 'helpers.js',
  });
  return win;
}

function readShipped(rel) {
  return fs.readFileSync(path.join(ROOT, rel), 'utf8');
}

module.exports = { loadShipped, readShipped, ROOT };
