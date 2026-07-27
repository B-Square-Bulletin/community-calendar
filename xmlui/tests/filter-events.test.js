// Unit tests for xmlui/helpers.js — search filtering functions
// Run: node --test xmlui/tests/filter-events.test.js

const { describe, it, beforeEach } = require('node:test');
const assert = require('node:assert');

// Load the functions under test by evaluating helpers.js in a minimal context
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function loadHelpers() {
  const code = fs.readFileSync(path.join(__dirname, '..', 'helpers.js'), 'utf8');

  // Stub browser globals that helpers.js touches at load time
  const sandbox = {
    window: {},
    performance: { now: () => Date.now() },
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    console: { log: () => {} },
    document: { write: () => {}, createElement: () => ({}) },
    XMLHttpRequest: function() {},
    fetch: () => Promise.resolve({ json: () => [] }),
    indexedDB: { open: () => ({ onupgradeneeded: null, onsuccess: null, onerror: null }) },
    URLSearchParams: URLSearchParams,
    URL: URL,
    supabase: { createClient: () => ({ auth: { onAuthStateChange: () => {} } }) },
    navigator: {},
    setInterval: () => {},
    clearInterval: () => {},
    Date: Date,
    Math: Math,
    JSON: JSON,
    Object: Object,
    Array: Array,
    String: String,
    Number: Number,
    Set: Set,
    Map: Map,
    RegExp: RegExp,
    Error: Error,
    TypeError: TypeError,
    Promise: Promise,
    isNaN: isNaN,
    parseInt: parseInt,
    parseFloat: parseFloat,
    encodeURIComponent: encodeURIComponent,
    decodeURIComponent: decodeURIComponent,
    unescape: unescape,
    escape: escape,
    atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
  };
  sandbox.window = sandbox; // self-reference like browser
  // Initialize browser globals that helpers.js expects at load time
  sandbox._categories = [];
  sandbox.categoryColorMap = {};
  sandbox._cities = {};
  sandbox._sourcePriority = { aggregators: [] };
  sandbox._filterLog = [];
  sandbox._localHiddenSources = null;
  sandbox._dateRangeBase = new Date();
  sandbox.embed = false;
  sandbox.hasLayoutModeParam = false;
  sandbox.hasImagesParam = false;
  sandbox.showListImages = false;
  sandbox.layoutMode = 'list';
  sandbox.initialSearch = '';
  sandbox.initialCategory = '';
  sandbox.APP_VERSION = 'test';
  sandbox.cityFilter = 'test';
  sandbox.SUPABASE_URL = 'https://test.supabase.co';
  sandbox.SUPABASE_KEY = 'test-key';
  sandbox.authUser = null;
  sandbox.authSession = null;

  // Stub functions that helpers.js calls during initialization
  sandbox.syncSearchParam = function(){};
  sandbox.syncCategoryParam = function(){};
  sandbox.setLayoutMode = function(){};
  sandbox.setShowListImages = function(){};
  sandbox.getActiveCategories = function() { return []; };
  sandbox.toDisplayName = function(slug) { return slug; };
  sandbox.getFromDate = function() { return new Date().toISOString(); };
  sandbox.getToDate = function() {
    var d = new Date(); d.setMonth(d.getMonth() + 3); return d.toISOString();
  };
  sandbox.getEventDayRange = function() { return null; };
  sandbox.expandEnrichments = function() { return []; };
  sandbox.filterHiddenSources = function(events) { return events; };
  sandbox.collapseLongRunningEvents = function(events) { return events; };
  sandbox.sortSourcesForDisplay = function(events) { return events; };
  sandbox.filterExternalExclusions = function(events) { return events; };
  sandbox.saveUserSetting = function() { return []; };
  sandbox.saveHiddenSources = function() { return []; };
  sandbox.toggleSourceAndSave = function() { return []; };
  sandbox.isSourceHidden = function() { return false; };
  sandbox.getSourceCounts = function() { return {}; };
  sandbox.dedupeEvents = function(events) { return events; };
  sandbox.formatDayOfWeek = function() { return 'Mon'; };
  sandbox.formatMonthDay = function() { return 'Jan 1'; };
  sandbox.formatTime = function() { return '8:00 PM'; };
  sandbox.formatDayOffset = function() { return 'Today'; };
  sandbox.getSnippet = function() { return 'snippet'; };
  sandbox.getDescriptionSnippet = function() { return null; };
  sandbox.formatSourceLinks = function() { return 'source'; };
  sandbox.isEventPicked = function() { return false; };
  sandbox.clusterBorder = function() { return false; };
  sandbox.defaultDashboardTile = function() { return {}; };
  sandbox.defaultDashboardLayout = function() { return {}; };
  sandbox.saveDashboardConfig = function() {};
  sandbox.getCityTimezone = function() { return 'America/New_York'; };
  sandbox.getQueryMonths = function() { return 3; };
  sandbox.refetchEvents = function() {};
  sandbox.xsTraceEvent = function() {};
  sandbox.xsTraceWith = function(name, fn) { return fn(); };

  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return sandbox;
}

let helpers;

beforeEach(() => {
  helpers = loadHelpers();
});

// Minimal event factory matching the shape used by the app
function makeEvent(id, title, opts = {}) {
  return {
    id,
    title,
    start_time: new Date().toISOString(),
    end_time: new Date(Date.now() + 3600000).toISOString(),
    location: opts.location || 'Test Venue',
    source: opts.source || 'Test Source',
    description: opts.description || 'A test event description',
    category: opts.category || 'Test',
    url: opts.url || `https://example.com/event/${id}`,
    ...opts,
  };
}

describe('getEventSearchText', () => {
  it('concatenates title, location, source, description and lowercases', () => {
    const text = helpers.getEventSearchText(makeEvent('1', 'Live Music', {
      location: 'The Bluebird',
      source: 'Visit Bloomington',
      description: 'Rock and roll all night',
    }));
    assert.strictEqual(text, 'live music the bluebird visit bloomington rock and roll all night');
  });

  it('handles missing fields gracefully', () => {
    const text = helpers.getEventSearchText({ id: '2', title: 'Solo' });
    assert.strictEqual(text, 'solo   ');
  });
});

describe('buildSearchIndex', () => {
  it('populates _search on every event', () => {
    const events = [
      makeEvent('1', 'Concert'),
      makeEvent('2', 'Art Show'),
    ];
    helpers.buildSearchIndex(events);
    assert.ok(events[0]._search.includes('concert'));
    assert.ok(events[1]._search.includes('art show'));
  });

  it('recomputes unconditionally even if _search already exists', () => {
    const event = makeEvent('1', 'Old Title');
    event._search = 'stale cached value';
    helpers.buildSearchIndex([event]);
    assert.ok(!event._search.includes('stale'));
    assert.ok(event._search.includes('old title'));
  });

  it('handles empty and null input', () => {
    const emptyResult = helpers.buildSearchIndex([]);
    const nullResult = helpers.buildSearchIndex(null);
    assert.ok(Array.isArray(emptyResult));
    assert.ok(Array.isArray(nullResult));
    assert.strictEqual(emptyResult.length, 0);
    assert.strictEqual(nullResult.length, 0);
  });
});

describe('filterEvents', () => {
  // Reset module-level state between tests
  beforeEach(() => {
    helpers = loadHelpers();
  });

  it('uses pre-computed _search when available', () => {
    const event = makeEvent('1', 'Jazz Night');
    helpers.buildSearchIndex([event]);

    // Monkey-patch getEventSearchText to detect if it gets called
    let getEventSearchTextCalled = false;
    const original = helpers.getEventSearchText;
    helpers.getEventSearchText = function(...args) {
      getEventSearchTextCalled = true;
      return original.apply(this, args);
    };

    const results = helpers.filterEvents([event], 'jazz', '');
    assert.strictEqual(results.length, 1);
    assert.strictEqual(getEventSearchTextCalled, false, 'should not recompute when _search exists');
  });

  it('falls back to getEventSearchText when _search is missing', () => {
    const event = makeEvent('1', 'Jazz Night');
    delete event._search; // no pre-computed index

    const results = helpers.filterEvents([event], 'jazz', '');
    assert.strictEqual(results.length, 1);
    assert.ok(event._search, 'should populate _search as fallback');
  });

  it('returns all events when term is empty', () => {
    const events = [makeEvent('1', 'A'), makeEvent('2', 'B')];
    const results = helpers.filterEvents(events, '', '');
    assert.strictEqual(results.length, 2);
  });

  it('filters by category when provided', () => {
    const events = [
      makeEvent('1', 'Concert', { category: 'Music' }),
      makeEvent('2', 'Lecture', { category: 'Education' }),
    ];
    const results = helpers.filterEvents(events, '', 'Music');
    assert.strictEqual(results.length, 1);
    assert.strictEqual(results[0].title, 'Concert');
  });

  it('progressive narrowing reuses previous result when extending term', () => {
    const events = [
      makeEvent('1', 'Jazz Night'),
      makeEvent('2', 'Jazz Festival'),
      makeEvent('3', 'Rock Concert'),
    ];
    helpers.buildSearchIndex(events);

    // First search: 'jazz' → 2 results
    const r1 = helpers.filterEvents(events, 'jazz', '');
    assert.strictEqual(r1.length, 2);

    // Extended search: 'jazz n' → should narrow to 1 result
    const r2 = helpers.filterEvents(events, 'jazz n', '');
    assert.strictEqual(r2.length, 1);
    assert.strictEqual(r2[0].title, 'Jazz Night');
  });

  it('full re-scan on backspace (no narrowing possible)', () => {
    const events = [
      makeEvent('1', 'Jazz Night'),
      makeEvent('2', 'Jazz Festival'),
      makeEvent('3', 'Rock Concert'),
    ];
    helpers.buildSearchIndex(events);

    // Search 'jazz n' → 1 result
    const r1 = helpers.filterEvents(events, 'jazz n', '');
    assert.strictEqual(r1.length, 1);

    // Backspace to 'jazz' → full re-scan, 2 results
    const r2 = helpers.filterEvents(events, 'jazz', '');
    assert.strictEqual(r2.length, 2);
  });

  it('full re-scan after clearing search', () => {
    const events = [
      makeEvent('1', 'Jazz Night'),
      makeEvent('2', 'Rock Concert'),
    ];
    helpers.buildSearchIndex(events);

    // Search 'jazz' → 1 result
    const r1 = helpers.filterEvents(events, 'jazz', '');
    assert.strictEqual(r1.length, 1);

    // Clear → all events
    const r2 = helpers.filterEvents(events, '', '');
    assert.strictEqual(r2.length, 2);

    // New search 'rock' → full re-scan, 1 result
    const r3 = helpers.filterEvents(events, 'rock', '');
    assert.strictEqual(r3.length, 1);
  });

  it('respects category filter combined with search term', () => {
    const events = [
      makeEvent('1', 'Jazz Night', { category: 'Music' }),
      makeEvent('2', 'Jazz Lecture', { category: 'Education' }),
    ];
    helpers.buildSearchIndex(events);

    const results = helpers.filterEvents(events, 'jazz', 'Music');
    assert.strictEqual(results.length, 1);
    assert.strictEqual(results[0].title, 'Jazz Night');
  });

  it('handles null and empty input arrays', () => {
    assert.ok(Array.isArray(helpers.filterEvents(null, 'test', '')));
    assert.ok(Array.isArray(helpers.filterEvents([], 'test', '')));
    assert.strictEqual(helpers.filterEvents(null, 'test', '').length, 0);
    assert.strictEqual(helpers.filterEvents([], 'test', '').length, 0);
  });
});

describe('sortSourcesForDisplay + buildSearchIndex integration', () => {
  // This tests the edge case Jon identified: sortSourcesForDisplay creates
  // new objects via Object.assign, so buildSearchIndex must recompute
  // unconditionally to ensure _search reflects the merged source string.

  it('search by source name works after source merge', () => {
    const event = makeEvent('1', 'Community Festival', {
      source: 'BloomingtonOnline Events, City of Bloomington',
      location: 'City Hall Plaza',
    });

    // Simulate what sortSourcesForDisplay does (creates new object)
    const sorted = Object.assign({}, event, {
      source: 'City of Bloomington, BloomingtonOnline Events',
    });

    // buildSearchIndex must recompute on the new object
    helpers.buildSearchIndex([sorted]);

    const results = helpers.filterEvents([sorted], 'city of bloomington', '');
    assert.strictEqual(results.length, 1);
  });

  it('does not use stale _search from before source merge', () => {
    const event = makeEvent('1', 'Community Festival', {
      source: 'BloomingtonOnline Events, City of Bloomington',
    });
    // Pre-merge search index (would NOT contain reordered source)
    event._search = helpers.getEventSearchText(event);

    // After sortSourcesForDisplay creates new object
    const sorted = Object.assign({}, event, {
      source: 'City of Bloomington, BloomingtonOnline Events',
    });
    // The old _search is stale — it was computed on the original event,
    // not the merged one. buildSearchIndex must overwrite it.
    helpers.buildSearchIndex([sorted]);

    const results = helpers.filterEvents([sorted], 'city of bloomington', '');
    assert.strictEqual(results.length, 1);
  });
});
