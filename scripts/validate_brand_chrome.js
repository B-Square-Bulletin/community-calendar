#!/usr/bin/env node
// validate_brand_chrome.js — static chrome check for #86 (branded masthead + footer)
// + #88 (content-link decoupling).
//
// WHY: header/footer are declarative XMLUI markup with no pure-logic seam, so
// test.html unit tests don't apply (per #83 Testing Decisions, chrome is
// browser-verified). These file-content assertions are the fast pre-check:
// they fail in seconds without Chromium if any acceptance criterion regresses.
// Source of truth stays the `Brand chrome (#86)` group in xmlui/test.html,
// which fetches served files in the Playwright CI step.
//
// Usage:
//   node scripts/validate_brand_chrome.js
//
// Exit code 0 = all checks pass, 1 = regression detected.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..', 'xmlui');
let failures = 0;
function check(name, cond) {
  if (cond) { console.log('PASS ' + name); }
  else { failures++; console.log('FAIL ' + name); }
}
function read(p) {
  try { return fs.readFileSync(path.join(ROOT, p), 'utf8'); } catch { return null; }
}

const header = read('components/BrandHeader.xmlui');
const footer = read('components/BrandFooter.xmlui');
const main = read('Main.xmlui');
const config = read('config.json');
const index = read('index.html');
const themeText = read('themes/b-square-bulletin.json');
let logo = null;
try { logo = fs.readFileSync(path.join(ROOT, 'icons/BSB_Logo-2-color-horiz.svg'), 'utf8'); } catch { logo = null; }

// --- BrandHeader ---
check('header exists', !!header);
check('header links logo to bsquarebulletin.com same-tab',
  !!header && header.includes('https://bsquarebulletin.com/') && !/to="https:\/\/bsquarebulletin\.com[^"]*"[^>]*target="_blank"/.test(header));
check('header sub-label black bold letter-spaced',
  !!header && header.includes('Community Calendar') && header.includes('color="black"')
  && header.includes('$fontWeight-bold') && /letterSpacing/i.test(header));
check('header 4px red bottom rule',
  !!header && /borderBottom="4px solid \$color-primary"/.test(header));
check('header Inter chrome font scoped to component',
  !!header && header.includes('Inter'));
check('header hidden on embed', !!header && header.includes('!window.embed'));
check('header references vendored logo with APP_VERSION',
  !!header && /BSB_Logo-2-color-horiz\.svg\?v=.*APP_VERSION/.test(header));

// --- BrandFooter ---
check('footer exists', !!footer);
check('footer red bar white text',
  !!footer && footer.includes('$color-primary') && footer.includes('$color-surface'));
check('footer Chronicle link new-tab',
  !!footer && footer.includes('https://thebloomingtonchronicle.org/index.php/Main_Page') && /thebloomingtonchronicle[^>]*target="_blank"/.test(footer));
check('footer BloomDocs link new-tab',
  !!footer && footer.includes('https://bloomdocs.org/') && /bloomdocs\.org[^>]*target="_blank"/.test(footer));
check('footer Contact link same-tab',
  !!footer && footer.includes('https://bsquarebulletin.com/contact-the-b-square/')
  && !/contact-the-b-square[^>]*target="_blank"/.test(footer));
check('footer Republishing link same-tab',
  !!footer && footer.includes('https://bsquarebulletin.com/republishing-guidelines/')
  && !/republishing-guidelines[^>]*target="_blank"/.test(footer));
check('footer has no Ghost portal links',
  !!footer && !footer.replace(/<!--[\s\S]*?-->/g, '').includes('#/portal/'));
check('footer copyright line',
  !!footer && footer.includes('© The B Square. All rights reserved.'));
check('footer Inter chrome font', !!footer && footer.includes('Inter'));
check('footer hidden on embed', !!footer && footer.includes('!window.embed'));

// --- Logo asset + registration ---
check('logo vendored under icons/', !!logo && logo.includes('<svg'));
check('logo has no scripts', !!logo && !/script|onload|onclick/i.test(logo));
check('logo registered in config.json resources',
  !!config && config.includes('BSB_Logo-2-color-horiz.svg'));

// --- Main.xmlui wiring ---
const headerIncludes = main ? (main.match(/IncludeMarkup[^>]*BrandHeader\.xmlui\?v=' \+ window\.APP_VERSION/g) || []).length : 0;
const footerIncludes = main ? (main.match(/IncludeMarkup[^>]*BrandFooter\.xmlui\?v=' \+ window\.APP_VERSION/g) || []).length : 0;
check('header included in all 3 standalone blocks (picker,list,dashboard)', headerIncludes === 3);
check('footer included in all 3 standalone blocks (picker,list,dashboard)', footerIncludes === 3);
check('dashboard loading state keeps chrome (not gated on tiles)',
  !!main && /when="\{layoutMode === 'dashboard'( && !window\.embed)?\}"/.test(main)
  && !/layoutMode === 'dashboard' && \(dashboardTiles !== null\)[^>]*Brand(Header|Footer)/.test(main));
check('picker redundant H1 dropped',
  !!main && !/<H1>Community Calendar<\/H1>/.test(main));
check('city-name heading intact',
  !!main && main.includes('{window.toDisplayName(city)}'));
check('title-row controls (IconRow) intact',
  !!main && (main.match(/components\/IconRow\.xmlui/g) || []).length === 2);
check('no fontFamily overrides on existing components',
  !!main && !/fontFamily/.test(main)
  && (() => {
    const files = fs.readdirSync(path.join(ROOT, 'components')).filter(f => f.endsWith('.xmlui') && f !== 'BrandHeader.xmlui' && f !== 'BrandFooter.xmlui');
    return files.every(f => !/fontFamily/.test(fs.readFileSync(path.join(ROOT, 'components', f), 'utf8')));
  })());

// --- Theme warm surfaces (#84) + boot versioning ---
check('theme surfaces are warm-neutral (not pure gray)',
  !!themeText && (() => {
    try {
      const theme = JSON.parse(themeText);
      return ['color-surface', 'color-surface-200', 'color-surface-300', 'color-surface-400', 'color-surface-500', 'color-surface-600']
        .every(k => /hsl\(40/.test(theme.themeVars[k] || ''));
    } catch { return false; }
  })());
check('index.html version-busts boot-decisions.js before shell.js',
  !!index && index.includes('boot-decisions.js')
  && !/<script src="boot-decisions\.js"><\/script>/.test(index)
  && index.indexOf('src="boot-decisions.js') < index.indexOf('src="shell.js'));

// --- Content links (#88): decouple from chrome red ---
// WHY: title/Event-link/Markdown anchors inherit textColor-Link, which
// defaults to $color-primary-500 (harsh BSB red). BSB theme must pin
// textColor-Link* to a darker desaturated maroon in the same hue family
// so Brand chrome stays red while content links soften + hold AA contrast.
function parseHsl(s) {
  const m = /hsl\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)/.exec(s || '');
  return m ? { h: +m[1], s: +m[2], l: +m[3] } : null;
}
function hslToRgb(h, s, l) {
  h /= 360; s /= 100; l /= 100;
  const k = (n) => (n + h * 12) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0), f(8), f(4)].map((v) => Math.round(v * 255));
}
function relLum([r, g, b]) {
  const ch = (c) => {
    c /= 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}
function contrastOf(fg, bg) {
  const l1 = relLum(fg);
  const l2 = relLum(bg);
  const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}
check('theme keeps chrome red primary (BSB brand)',
  !!themeText && (() => {
    try {
      return JSON.parse(themeText).themeVars['color-primary'] === 'hsl(354, 75%, 47%)';
    } catch { return false; }
  })());
check('theme decouples content links to darker maroon (not chrome red)',
  !!themeText && (() => {
    try {
      const vars = JSON.parse(themeText).themeVars;
      return ['textColor-Link', 'textColor-Link--hover', 'textColor-Link--active']
        .every((k) => {
          const c = parseHsl(vars[k]);
          return !!c && c.h >= 350 && c.h <= 356 && c.s >= 55 && c.s <= 70 && c.l >= 28 && c.l <= 40;
        });
    } catch { return false; }
  })());
check('content link color meets WCAG AA 4.5:1 on white card + warm surface',
  !!themeText && (() => {
    try {
      const vars = JSON.parse(themeText).themeVars;
      const c = parseHsl(vars['textColor-Link']);
      const surf = parseHsl(vars['color-surface']);
      const fg = hslToRgb(c.h, c.s, c.l);
      const white = [255, 255, 255];
      const surface = hslToRgb(surf.h, surf.s, surf.l);
      return contrastOf(fg, white) >= 4.5 && contrastOf(fg, surface) >= 4.5;
    } catch { return false; }
  })());
check('event title inherits theme link color (no per-instance override)',
  !!read('components/EventCard.xmlui') && (() => {
    const card = read('components/EventCard.xmlui');
    return card.includes('value="{$props.event.title}"')
      && !/<Text[^>]*value="\{\$props\.event\.title\}"[^>]*color=/.test(card);
  })());

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECKS FAILED`);
process.exit(failures === 0 ? 0 : 1);
