#!/usr/bin/env node
// bench_card_group.js — verify the Card.group memo in the browser's real shape.
//
// Card (#169) is the one client authority on card membership. The processed
// pipeline evaluates it more than once per load (cached emit, then network
// emit) with different object references but the same content, so groupMemo
// must HIT on the warm path and return the previous array BY REFERENCE. It must
// recompute whenever shell.js publishes a new emission signature (__ccEmitSig,
// the #86 lesson), even when the payload's length and endpoint ids are
// unchanged.
//
// This benchmark loads the shipped xmlui/card.js, runs groupMemo over
// synthetic view-shaped rows, and asserts:
//   1. run #2 (fresh references, same content, same emission) is a HIT and ~0ms
//   2. run #2 returns the same result as run #1
//   3. a new emission recomputes even when only the middle row changed
//
// Usage:
//   node scripts/bench_card_group.js                    # synthetic rows
//   node scripts/bench_card_group.js --rows data.json   # a view-shaped payload
//
// Exit code 0 = verified, 1 = regression detected.

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');

// --- Window shim (card.js is a browser-global module) ----------------------
const windowObj = {
  _sourcePriority: { aggregators: [] },
  __ccEmitSig: 'emit-1',
  performance: performance,
};
windowObj.window = windowObj;
windowObj.self = windowObj;

const sandbox = {
  window: windowObj,
  performance,
  console,
  Date,
  Set,
  Map,
  Number,
  Array,
  Object,
  JSON,
};
sandbox.global = sandbox;
vm.createContext(sandbox);

const cardSrc = fs.readFileSync(path.join(ROOT, 'xmlui', 'card.js'), 'utf8');
vm.runInContext(cardSrc, sandbox, { filename: 'xmlui/card.js' });

// --- Event generation (view-shaped: one row per stored group) ---------------
function syntheticRows(count, seed = 1234) {
  // Deterministic LCG so runs are reproducible.
  let state = seed >>> 0;
  const rng = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
  const titles = [
    'Gallery Opening Reception',
    'Farmers Market',
    'Book Club Discussion',
    'Yoga in the Park',
    'Live Jazz Night',
    'Film Screening Series',
    'Art Exhibition',
    'Community Cleanup',
    'Poetry Slam',
    'Craft Workshop',
  ];
  const locations = [
    'Buskirk-Chumley Theater',
    'WonderLab Museum',
    'Monroe County Public Library',
    'Switchyard Park',
    'The Bishop Bar',
  ];
  const sources = ['visitbloomington.com', 'wfhb.org', 'bloomington.in.gov', 'iub.edu'];

  const base = Date.UTC(2026, 8, 28, 12, 0, 0);
  const rows = [];
  for (let i = 0; i < count; i++) {
    const source = sources[Math.floor(rng() * sources.length)];
    const id = 100000 + i;
    // ~8% grouped rows carry the route's rolled-up membership; the rest are
    // Separate rows, one id each.
    const grouped = rng() < 0.08;
    rows.push({
      id,
      title: titles[Math.floor(rng() * titles.length)],
      start_time: new Date(base + Math.floor(rng() * 90) * 24 * 3600 * 1000).toISOString(),
      end_time: null,
      url: 'https://example.com/events/' + i,
      location: locations[Math.floor(rng() * locations.length)],
      description: 'Synthetic view row ' + i,
      source,
      source_names: [source],
      source_urls: { [source]: 'https://example.com/events/' + i },
      category: 'Community / Social',
      image_url: null,
      all_day: false,
      merged_ids: grouped ? [id, id + 1] : [id],
      duplicate_group: grouped ? 'cr' + i + ':g' : null,
      city: 'bloomington',
    });
  }
  // The pipeline keeps rows sorted by start_time; match that so endpoint ids
  // are stable across the fresh-reference run.
  rows.sort((a, b) => (a.start_time < b.start_time ? -1 : a.start_time > b.start_time ? 1 : 0));
  return rows;
}

function main() {
  const argv = process.argv.slice(2);
  const rowsIdx = argv.indexOf('--rows');
  let rows;
  if (rowsIdx >= 0 && argv[rowsIdx + 1]) {
    rows = JSON.parse(fs.readFileSync(path.resolve(argv[rowsIdx + 1]), 'utf8'));
    if (!Array.isArray(rows)) throw new Error('--rows file must contain a JSON array of rows');
  } else {
    rows = syntheticRows(3202);
  }

  console.log('Card.groupMemo benchmark');
  console.log(
    'rows: ' +
      rows.length +
      (rowsIdx >= 0 ? ' (real data: ' + argv[rowsIdx + 1] + ')' : ' (synthetic)')
  );
  console.log('');

  const Card = windowObj.Card;
  if (!Card || typeof Card.groupMemo !== 'function') {
    console.error('ERROR: window.Card.groupMemo not found — card.js did not load');
    process.exit(2);
  }

  // Run #1 — cold compute.
  let t0 = performance.now();
  const run1 = Card.groupMemo(rows);
  const run1ms = performance.now() - t0;
  console.log('run#1 (cold): ' + run1ms.toFixed(1) + 'ms, ' + run1.length + ' cards');

  // Run #2 — network emit: same content, fresh references, same emission.
  const fresh = JSON.parse(JSON.stringify(rows));
  if (fresh[0] === rows[0]) {
    console.error('ERROR: fresh reference array not actually fresh — test is broken');
    process.exit(2);
  }
  t0 = performance.now();
  const run2 = Card.groupMemo(fresh);
  const run2ms = performance.now() - t0;
  console.log('run#2 (warm, fresh refs): ' + run2ms.toFixed(1) + 'ms');

  // Run #3 — a new emission whose middle row changed (same length, same
  // endpoint ids): the emission signature must force a recompute.
  const changed = JSON.parse(JSON.stringify(rows));
  const mid = Math.floor(changed.length / 2);
  changed[mid].title = changed[mid].title + ' (edited)';
  windowObj.__ccEmitSig = 'emit-2';
  t0 = performance.now();
  const run3 = Card.groupMemo(changed);
  const run3ms = performance.now() - t0;
  console.log('run#3 (new emission, mid edit): ' + run3ms.toFixed(1) + 'ms');
  console.log('');

  const failures = [];
  const HIT_THRESHOLD_MS = 5; // cache hits take microseconds; 5ms is generous

  if (run2 !== run1) {
    failures.push('run#2 did not return the cached array by reference (memo miss)');
  }
  if (run2ms > HIT_THRESHOLD_MS) {
    failures.push('run#2 took ' + run2ms.toFixed(1) + 'ms (expected < ' + HIT_THRESHOLD_MS + 'ms)');
  }
  if (JSON.stringify(run1) !== JSON.stringify(run2)) {
    failures.push('run#2 results differ from run#1 (cache returned wrong data)');
  }
  if (run3 === run2) {
    failures.push('run#3 reused the previous result despite a new emission');
  }
  if (run1.length !== rows.length) {
    failures.push(
      'run#1 produced ' +
        run1.length +
        ' cards for ' +
        rows.length +
        ' view rows (expected pass-through)'
    );
  }

  if (failures.length) {
    console.error('FAIL — regression detected:');
    failures.forEach(function (f) {
      console.error('  ✗ ' + f);
    });
    process.exit(1);
  }
  console.log(
    'PASS — Card.groupMemo warm path verified (' + run2ms.toFixed(1) + 'ms, same reference).'
  );
  process.exit(0);
}

main();
