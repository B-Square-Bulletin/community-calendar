#!/usr/bin/env node
// validate_brand_chrome.js — static chrome check for #86 (branded masthead + footer).
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
  !!main && main.includes(`when="{layoutMode === 'dashboard'}"`)
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

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECKS FAILED`);
process.exit(failures === 0 ? 0 : 1);
