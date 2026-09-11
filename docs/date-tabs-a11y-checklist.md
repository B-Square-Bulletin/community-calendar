# Date Tabs Accessibility Acceptance Checklist (#109)

This is the human gate for the tabbed date-filtering effort. The structural
criteria are automated in `tests/js/date-tabs-a11y.browser.spec.js` (see
[ADR 0008](adr/0008-date-tab-a11y-verification.md)); what remains here needs a
person with a keyboard, a screen reader, and a narrow viewport.

Run it against a local serve of the real app with live data:

```bash
python3 -m http.server 8080
# open http://localhost:8080/xmlui/index.html
```

On macOS the screen reader is VoiceOver: press `Cmd+F5` to toggle it.

## Automated (do not re-check by hand)

Covered by `pnpm playwright test tests/js/date-tabs-a11y.browser.spec.js`:

- [x] Region-scoped axe scan (WCAG A/AA) on the tab strip and heading is clean
- [x] Exactly one tab carries `aria-pressed="true"`; it tracks the committed window
- [x] Custom reads pressed while its flow is open, before any range commits
- [x] Keyboard-only: Enter on a focused tab commits the window and syncs `?date=`
- [x] Committing a preset moves no focus
- [x] Escape in the picker returns focus to the Custom tab
- [x] Tab from page load reaches every date tab in Safari/WebKit tab order
      (explicit `tabindex="0"` on the tabs; run under the `webkit` project)
- [x] 360px: the strip wraps with every preset reachable and no horizontal scroll

## Human: screen reader (VoiceOver)

- [ ] With VoiceOver on, tabbing to a date tab announces the tab name **and**
      that it is pressed/selected (e.g. "Today, pressed, button"). Confirm the
      state is spoken, not just visually styled.
- [ ] Committing a tab (Enter/Space) announces the new state without the
      reading position being thrown to the top of the page.
- [ ] In the Custom picker, the date range control announces its label
      ("Custom date range") and the two inputs announce start and end.
- [ ] Escape from the picker returns the reading/focus position to the Custom
      tab.

## Human: keyboard-only

- [ ] Every one of the eight tabs is reachable with `Tab` and shows a visible
      focus ring. (Reachability is automated in the WebKit gate; the visible
      focus ring still needs an eye.)
- [ ] Enter or Space commits the focused tab.
- [ ] The full Custom flow (open, pick start, pick end, Proceed) completes
      without a mouse, and Escape returns focus to the Custom tab.
- [ ] The empty-state "Show next 7 days" button is reachable and moves focus to
      the tab-strip heading without scrolling the page.

## Human: 360px viewport

- [ ] At 360px wide the strip wraps to multiple rows with no horizontal
      scrolling and every preset reachable.
- [ ] The embedded calendar (`?embed=true`) shows the identical filter UI at
      360px.

## Human: live-data browser checklist

- [ ] All seven presets plus All dates produce the expected windows.
- [ ] Tonight applies the 5pm city-time start-time-only cutoff (16:59 excluded,
      17:00 included; all-day excluded).
- [ ] Custom commits once on Proceed; nothing filters mid-drag or per tick.
- [ ] Empty window shows `No events {windowLabel}.` and the reset commits Next 7.
- [ ] Horizon truncation shows `Showing through {horizonDate} — the calendar
      currently ends there.` below the tabs.
- [ ] URL round-trips: preset link, custom link, unknown key falls back to All,
      malformed pair ignored, past `from` clamps and rewrites, clear strips only
      the date keys, reload restores, Back exits rather than unpicking, and
      city+date Back leaves the calendar.
- [ ] Embed plus date params round-trip together.
- [ ] Category counts reflect the active window.
- [ ] The visible result count updates only when a tab or range is committed —
      never mid-interaction — and the new count is spoken/readable without a
      live-region announcement.
- [ ] Picks and Dashboard are unaffected by the date window.
- [ ] The production slider stays gone (no dual control).

## Sign-off

- [ ] Any failure above is filed back to the ticket that owns it, not fixed
      inline in the verification ticket.
- [ ] `109` can be closed with the automation green and this checklist
      complete.
