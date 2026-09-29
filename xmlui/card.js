// card.js — Card: the one client authority on card membership (#169 / ADR-0017).
//
// A *card* is one rendered calendar row: the client-side view of one real-world
// event. Card reads only the stored route decision the view already carries
// (`duplicate_group`, `merged_ids`, `source_names`, `source_urls`) and never
// recomputes similarity — the build-time confidence route (ADR-0013) stays the
// sole authority on which listings are one event. A NULL `duplicate_group` means
// one row is one card.
//
// The load-bearing job is *enrichment folding*. A curator enrichment's
// occurrences arrive on a separate fetch as virtual rows with synthetic string
// ids. The occurrence flagged `_enrichment_is_original_occurrence` attaches to
// its linked group's card; every other occurrence stays its own card, marked
// `isVirtual`, and synthetic ids never enter membership.
//
// Shipped as a plain `window`-attached module (loaded before helpers.js and
// before app start) so it is a pure test seam: no DOM, no network, no engine.
(function () {
  'use strict';

  function isNumericId(id) {
    return typeof id === 'number' || (typeof id === 'string' && /^\d+$/.test(id));
  }

  function normalizeTime(startTime) {
    return startTime ? new Date(startTime).toISOString() : '';
  }

  // The composite key that identifies one stored group: the route's group id
  // when present, else the row's own id. Grouping and the picks-list dedupe key
  // on it, so it is written once.
  function routeKey(duplicateGroup, id) {
    return duplicateGroup != null && duplicateGroup !== '' ? 'g:' + duplicateGroup : 'r:' + id;
  }

  function routeGroupKey(e) {
    return routeKey(e.duplicate_group, e.id);
  }

  // The stored member ids a row (or card) carries: the view's rolled-up list
  // when present, else the row's own id. `members(card)` additionally drops
  // synthetic ids and refuses virtual cards; grouping seeds with the raw list so
  // an enrichment occurrence can resolve its linked event.
  function memberIdList(row) {
    if (!row) return [];
    if (Array.isArray(row.merged_ids) && row.merged_ids.length) return row.merged_ids;
    return [row.id];
  }

  function seedMemberIds(e) {
    return memberIdList(e).slice();
  }

  function compareCards(a, b) {
    var timeCmp = (a.start_time || '').localeCompare(b.start_time || '');
    if (timeCmp !== 0) return timeCmp;
    // Within one instant, grouped rows before Separate rows; then group id,
    // then title. Pinned so a build cannot silently reshuffle equal instants.
    var ga = a.duplicate_group || '';
    var gb = b.duplicate_group || '';
    if (ga && gb) {
      if (ga !== gb) return ga.localeCompare(gb);
      return (a.title || '').localeCompare(b.title || '');
    }
    if (ga) return -1;
    if (gb) return 1;
    return (a.title || '').localeCompare(b.title || '');
  }

  // Pure: group stored listings into cards.
  function group(events) {
    if (!Array.isArray(events) || !events.length) return [];

    // Pass 1: each stored member id -> its route group and instant, so an
    // original enrichment occurrence can fold onto the card that carries its
    // linked event.
    var routeGroupByMember = new Map();
    events.forEach(function (e) {
      if (e._enrichment_event_id != null) return;
      var groupName = routeGroupKey(e);
      var startTime = normalizeTime(e.start_time);
      seedMemberIds(e).forEach(function (id) {
        routeGroupByMember.set(String(id), { group: groupName, startTime: startTime });
      });
    });

    // Pass 2: one card per (route group, normalised instant).
    var groups = Object.create(null);
    var order = [];
    events.forEach(function (e) {
      var virtual = e._enrichment_event_id != null;
      var linked =
        virtual && e._enrichment_is_original_occurrence === true
          ? routeGroupByMember.get(String(e._enrichment_event_id))
          : null;
      var normalizedTime = linked ? linked.startTime : normalizeTime(e.start_time);
      var groupName = (linked && linked.group) || routeGroupKey(e);
      var key = groupName + '|' + normalizedTime;

      var names = window.SourceHelpers.eventSourceNames(e);
      var structured =
        Array.isArray(e.source_names) && e.source_names.length ? names.slice() : null;
      var seedIds = seedMemberIds(e);

      if (!groups[key]) {
        groups[key] = {
          // A shallow copy: the merge branch below may backfill missing fields
          // (url/location/description/rrule) and must not mutate the caller's row.
          row: Object.assign({}, e),
          sourceNames: names.slice(),
          structured: structured != null,
          source_urls: Object.assign({}, e.source_urls || {}),
          merged_ids: seedIds.slice(),
          // Marked only when a virtual row did not fold onto a stored card.
          isVirtual: virtual && !linked,
        };
        order.push(key);
        return;
      }

      var g = groups[key];
      seedIds.forEach(function (id) {
        if (g.merged_ids.indexOf(id) < 0) g.merged_ids.push(id);
      });
      names.forEach(function (s) {
        if (g.sourceNames.indexOf(s) < 0) g.sourceNames.push(s);
      });
      g.structured = g.structured || structured != null;
      Object.assign(g.source_urls, e.source_urls || {});
      if (!g.row.url && e.url) g.row.url = e.url;
      if (!g.row.location && e.location) g.row.location = e.location;
      if (!g.row.description && e.description) g.row.description = e.description;
      if (!g.row.rrule && e.rrule) g.row.rrule = e.rrule;
    });

    var cards = order.map(function (key) {
      var g = groups[key];
      var sourcesArr = g.structured
        ? g.sourceNames.slice()
        : window.SourceHelpers.orderSourceNames(g.sourceNames, g.row.location);
      var card = Object.assign({}, g.row, {
        source: sourcesArr.join(', '),
        source_names: sourcesArr,
        // g.row is a copy of the first row, so its own `source_urls` is not the
        // union built above; emit the tracked map or a second member's link is
        // lost (endpoint/url rendering reads this).
        source_urls: Object.assign({}, g.source_urls),
        // Synthetic ids never enter membership (the picks FK enforces it too).
        merged_ids: g.merged_ids.filter(isNumericId),
      });
      if (g.isVirtual) card.isVirtual = true;
      delete card._enrichment_event_id;
      delete card._enrichment_is_original_occurrence;
      return card;
    });

    cards.sort(compareCards);
    return cards;
  }

  // The list item's complete membership. Virtual cards are never pickable, so
  // they read as empty.
  function members(card) {
    if (!card || card.isVirtual) return [];
    return memberIdList(card).filter(isNumericId);
  }

  function isPicked(card, picks) {
    if (!card || card.isVirtual) return false;
    if (!Array.isArray(picks)) return false;
    var ids = members(card);
    return picks.some(function (p) {
      return (
        p &&
        ids.some(function (id) {
          return p.event_id == id;
        })
      );
    });
  }

  // One entry per stored group. Ranking is exactly the my-picks ICS feed's
  // (ADR-0013): the route's canonical representative first, then the smallest
  // member event id, so the list and the feed cannot choose different members.
  function normalizePick(rawPick) {
    if (!rawPick) {
      return {
        id: null,
        eventId: null,
        duplicateGroup: null,
        sourceUid: null,
        isRepresentative: false,
      };
    }
    var ev = rawPick.events || rawPick;
    var eventId = rawPick.event_id != null ? rawPick.event_id : ev.id;
    var duplicateGroup =
      ev.duplicate_group != null
        ? ev.duplicate_group
        : rawPick.duplicate_group != null
          ? rawPick.duplicate_group
          : null;
    if (duplicateGroup === '') duplicateGroup = null;
    var sourceUid =
      ev.source_uid != null
        ? ev.source_uid
        : rawPick.source_uid != null
          ? rawPick.source_uid
          : null;
    var representative =
      ev.duplicate_group_representative != null
        ? ev.duplicate_group_representative
        : rawPick.duplicate_group_representative != null
          ? rawPick.duplicate_group_representative
          : null;
    return {
      id: rawPick.id != null ? rawPick.id : null,
      eventId: eventId != null ? Number(eventId) : null,
      duplicateGroup: duplicateGroup,
      sourceUid: sourceUid,
      isRepresentative: representative != null && sourceUid === representative,
    };
  }

  function uniquePicks(picks) {
    if (!Array.isArray(picks)) return [];
    var best = new Map();
    var order = [];
    picks.forEach(function (pick) {
      var n = normalizePick(pick);
      var key = routeKey(n.duplicateGroup, n.eventId);
      var rank = [n.isRepresentative ? 0 : 1, n.eventId || 0];
      var current = best.get(key);
      if (!current) {
        best.set(key, { pick: pick, rank: rank });
        order.push(key);
        return;
      }
      if (rank[0] < current.rank[0] || (rank[0] === current.rank[0] && rank[1] < current.rank[1])) {
        best.set(key, { pick: pick, rank: rank });
      }
    });
    return order.map(function (key) {
      return best.get(key).pick;
    });
  }

  function pickPlan(card) {
    return { memberEventIds: members(card) };
  }

  // Resolve a pick to its card in the processed list. The mirror the caller
  // passes is city+window scoped, so a miss is expected for other-city,
  // out-of-window, and pre-populate picks; the caller falls back to the DB.
  function cardForPick(pick, cards) {
    if (!Array.isArray(cards)) return null;
    var n = normalizePick(pick);
    if (n.eventId != null) {
      for (var i = 0; i < cards.length; i++) {
        if (
          members(cards[i]).some(function (id) {
            return Number(id) === n.eventId;
          })
        ) {
          return cards[i];
        }
      }
    }
    if (n.duplicateGroup != null && n.duplicateGroup !== '') {
      for (var j = 0; j < cards.length; j++) {
        if (cards[j] && cards[j].duplicate_group === n.duplicateGroup) return cards[j];
      }
    }
    return null;
  }

  // Composite fallback signature, mirroring the existing ingest memo: array
  // signature (length + first/last id) + enrichment-linkage signature + the
  // emission signature. Call sites that already hold the strong
  // window.eventsSignature(rows) pass it instead.
  function compositeSignature(events) {
    if (!Array.isArray(events)) return 'na';
    if (!events.length) return '0';
    var sig = events.length + ':' + events[0].id + ':' + events[events.length - 1].id;
    var hasLinkage = events.some(function (e) {
      return e && e._enrichment_id != null;
    });
    if (hasLinkage) {
      sig +=
        ':' +
        events
          .map(function (e) {
            return [
              e._enrichment_id,
              e._enrichment_event_id,
              e._enrichment_is_original_occurrence,
            ].join('|');
          })
          .join(',');
    }
    return sig;
  }

  var _memoKey = null;
  var _memoResult = null;

  function groupMemo(events, signature) {
    if (!Array.isArray(events) || !events.length) return group(events);
    var sig = signature || compositeSignature(events);
    var key = sig + '\u0000' + ((typeof window !== 'undefined' && window.__ccEmitSig) || '');
    if (_memoKey !== null && key === _memoKey) return _memoResult;
    var result = group(events);
    _memoKey = key;
    _memoResult = result;
    return result;
  }

  // Test-only memo reset (mirrors clearDedupeCache): a weak caller-supplied or
  // composite signature can collide across fixtures.
  function resetMemo() {
    _memoKey = null;
    _memoResult = null;
  }

  window.Card = {
    group: group,
    groupMemo: groupMemo,
    members: members,
    isPicked: isPicked,
    uniquePicks: uniquePicks,
    pickPlan: pickPlan,
    cardForPick: cardForPick,
    normalizePick: normalizePick,
    resetMemo: resetMemo,
  };
})();
