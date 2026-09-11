// tests/js/validate-brand-chrome.test.js — vitest migration of
// scripts/validate_brand_chrome.js (static chrome check for #86 branded
// masthead + footer, + #88 content-link decoupling).
//
// WHY: header/footer are declarative XMLUI markup with no pure-logic seam, so
// test.html unit tests don't apply (per #83 Testing Decisions, chrome is
// browser-verified). These file-content assertions are the fast pre-check:
// they fail in seconds without Chromium if any acceptance criterion regresses.
// Source of truth stays the `Brand chrome (#86)` group in xmlui/test.html,
// which fetches served files in the Playwright CI step.
//
// Migration notes: every `check(name, cond)` from
// scripts/validate_brand_chrome.js becomes
// `it(name, () => { expect(cond).toBe(true); })` with the condition preserved
// verbatim, including the contrast-ratio helpers (parseHsl, hslToRgb, relLum,
// contrastOf, toneTextColor). Top-level file reads use `readShipped()` from
// ./load-shipped instead of the script's local fs/path `read()` helper (fs is
// kept for the icons SVG read + components dir listing). No assertions
// changed, no behavior added.
//
// NOTE: the brief asked for `require('vitest')` (CommonJS), but vitest 3
// throws "Vitest cannot be imported in a CommonJS module using require()",
// so this file uses ESM `import` like tests/js/validate-date-tabs.test.js.
// Everything else follows the brief: `readShipped()` for xmlui reads,
// verbatim conditions, verbatim helpers, console.log info lines kept.
'use strict';
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { readShipped, ROOT } from './load-shipped.js';
function read(p) {
  try {
    return readShipped(p);
  } catch {
    return null;
  }
}

const header = read('components/BrandHeader.xmlui');
const footer = read('components/BrandFooter.xmlui');
const main = read('Main.xmlui');
const config = read('config.json');
const index = read('index.html');
const themeText = read('themes/b-square-bulletin.json');
let logo = null;
try {
  logo = fs.readFileSync(path.join(ROOT, 'icons/BSB_Logo-2-color-horiz.svg'), 'utf8');
} catch {
  logo = null;
}

// Shared pattern: the header must reference the single vendored logo asset
// with a cache-busting APP_VERSION query. Used by two checks below.
const LOGO_REF = /BSB_Logo-2-color-horiz\.svg\?v=.*APP_VERSION/;

// WHY: title/Event-link/Markdown anchors inherit textColor-Link, which
// defaults to $color-primary-500 (harsh BSB red). BSB theme must pin
// textColor-Link* to a darker desaturated maroon in the same hue family
// so Brand chrome stays red while content links soften + hold AA contrast.
function parseHsl(s) {
  const m = /hsl\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)/.exec(s || '');
  return m ? { h: +m[1], s: +m[2], l: +m[3] } : null;
}
function hslToRgb(h, s, l) {
  h /= 360;
  s /= 100;
  l /= 100;
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
// --- Sub-label per-tone contrast (#90): the "Community Calendar" line uses
// $color-text-primary, which the BSB theme must define for BOTH tones at
// WCAG AA (>= 4.5:1). Light text is checked against the white badge/card and
// the warm page surface; dark text against the engine's near-black dark
// surface (tones reverse the surface scale, so the page behind the
// transparent masthead goes dark). Ratios print so CI logs carry the numbers.
function toneTextColor(themeText, tone) {
  try {
    return JSON.parse(themeText).tones[tone].themeVars['color-text-primary'] || null;
  } catch {
    return null;
  }
}

describe('BrandHeader', () => {
  it('header exists', () => {
    expect(!!header).toBe(true);
  });
  it('header links logo to bsquarebulletin.com same-tab', () => {
    expect(
      !!header &&
        header.includes('https://bsquarebulletin.com/') &&
        !/to="https:\/\/bsquarebulletin\.com[^"]*"[^>]*target="_blank"/.test(header)
    ).toBe(true);
  });
  it('header sub-label uses $color-text-primary (dark-tone safe), bold, letter-spaced', () => {
    expect(
      !!header &&
        header.includes('Community Calendar') &&
        header.includes('$color-text-primary') &&
        !/color\s*=\s*["']black["']/.test(header) &&
        header.includes('$fontWeight-bold') &&
        /letterSpacing/i.test(header)
    ).toBe(true);
  });
  it('header logo pinned in a light-tone island (single asset, no tone tracking)', () => {
    expect(!!header && /<Theme[^>]*tone="light"/.test(header) && LOGO_REF.test(header)).toBe(true);
  });
  it('header island paints a pinned-light badge behind the logo', () => {
    expect(
      !!header &&
        /<Theme[^>]*tone="light"[\s\S]*?backgroundColor="white"[\s\S]*?BSB_Logo-2-color-horiz\.svg[\s\S]*?<\/Theme>/.test(
          header
        )
    ).toBe(true);
  });
  it('header 4px red bottom rule', () => {
    expect(!!header && /borderBottom="4px solid \$color-primary"/.test(header)).toBe(true);
  });
  it('header Inter chrome font scoped to component', () => {
    expect(!!header && header.includes('Inter')).toBe(true);
  });
  it('header hidden on embed', () => {
    expect(!!header && header.includes('!window.embed')).toBe(true);
  });
  it('header references vendored logo with APP_VERSION', () => {
    expect(!!header && LOGO_REF.test(header)).toBe(true);
  });
});

describe('BrandFooter', () => {
  it('footer exists', () => {
    expect(!!footer).toBe(true);
  });
  it('footer red bar white text', () => {
    expect(!!footer && footer.includes('$color-primary') && footer.includes('$color-surface')).toBe(
      true
    );
  });
  it('footer Chronicle link new-tab', () => {
    expect(
      !!footer &&
        footer.includes('https://thebloomingtonchronicle.org/index.php/Main_Page') &&
        /thebloomingtonchronicle[^>]*target="_blank"/.test(footer)
    ).toBe(true);
  });
  it('footer BloomDocs link new-tab', () => {
    expect(
      !!footer &&
        footer.includes('https://bloomdocs.org/') &&
        /bloomdocs\.org[^>]*target="_blank"/.test(footer)
    ).toBe(true);
  });
  it('footer Contact link same-tab', () => {
    expect(
      !!footer &&
        footer.includes('https://bsquarebulletin.com/contact-the-b-square/') &&
        !/contact-the-b-square[^>]*target="_blank"/.test(footer)
    ).toBe(true);
  });
  it('footer Republishing link same-tab', () => {
    expect(
      !!footer &&
        footer.includes('https://bsquarebulletin.com/republishing-guidelines/') &&
        !/republishing-guidelines[^>]*target="_blank"/.test(footer)
    ).toBe(true);
  });
  it('footer has no Ghost portal links', () => {
    expect(!!footer && !footer.replace(/<!--[\s\S]*?-->/g, '').includes('#/portal/')).toBe(true);
  });
  it('footer copyright line', () => {
    expect(!!footer && footer.includes('© The B Square. All rights reserved.')).toBe(true);
  });
  it('footer Inter chrome font', () => {
    expect(!!footer && footer.includes('Inter')).toBe(true);
  });
  it('footer hidden on embed', () => {
    expect(!!footer && footer.includes('!window.embed')).toBe(true);
  });
});

describe('logo asset', () => {
  it('logo vendored under icons/', () => {
    expect(!!logo && logo.includes('<svg')).toBe(true);
  });
  it('logo has no scripts', () => {
    expect(!!logo && !/script|onload|onclick/i.test(logo)).toBe(true);
  });
  it('logo wordmark stays near-black (asset untouched by tone fix)', () => {
    expect(!!logo && /fill:#231f20/i.test(logo)).toBe(true);
  });
  it('logo red square unchanged (brand red, no filter shift)', () => {
    expect(!!logo && /fill:#d21c2d/i.test(logo)).toBe(true);
  });
  it('logo registered in config.json resources', () => {
    expect(!!config && config.includes('BSB_Logo-2-color-horiz.svg')).toBe(true);
  });
});

describe('Main wiring', () => {
  const headerIncludes = main
    ? (main.match(/IncludeMarkup[^>]*BrandHeader\.xmlui\?v=' \+ window\.APP_VERSION/g) || []).length
    : 0;
  const footerIncludes = main
    ? (main.match(/IncludeMarkup[^>]*BrandFooter\.xmlui\?v=' \+ window\.APP_VERSION/g) || []).length
    : 0;
  it('header included in all 3 standalone blocks (picker,list,dashboard)', () => {
    expect(headerIncludes === 3).toBe(true);
  });
  it('footer included in all 3 standalone blocks (picker,list,dashboard)', () => {
    expect(footerIncludes === 3).toBe(true);
  });
  it('dashboard loading state keeps chrome (not gated on tiles)', () => {
    expect(
      !!main &&
        /when="\{layoutMode === 'dashboard'( && !window\.embed)?\}"/.test(main) &&
        !/layoutMode === 'dashboard' && \(dashboardTiles !== null\)[^>]*Brand(Header|Footer)/.test(
          main
        )
    ).toBe(true);
  });
  it('picker redundant H1 dropped', () => {
    expect(!!main && !/<H1>Community Calendar<\/H1>/.test(main)).toBe(true);
  });
  it('city-name heading intact', () => {
    expect(!!main && main.includes('{window.toDisplayName(city)}')).toBe(true);
  });
  it('title-row controls (IconRow) intact', () => {
    expect(!!main && (main.match(/components\/IconRow\.xmlui/g) || []).length === 2).toBe(true);
  });
  it('no fontFamily overrides on existing components', () => {
    expect(
      !!main &&
        !/fontFamily/.test(main) &&
        (() => {
          const files = fs
            .readdirSync(path.join(ROOT, 'components'))
            .filter(
              (f) => f.endsWith('.xmlui') && f !== 'BrandHeader.xmlui' && f !== 'BrandFooter.xmlui'
            );
          return files.every(
            (f) => !/fontFamily/.test(fs.readFileSync(path.join(ROOT, 'components', f), 'utf8'))
          );
        })()
    ).toBe(true);
  });
});

describe('theme/boot', () => {
  it('theme surfaces are warm-neutral (not pure gray)', () => {
    expect(
      !!themeText &&
        (() => {
          try {
            const theme = JSON.parse(themeText);
            return [
              'color-surface',
              'color-surface-200',
              'color-surface-300',
              'color-surface-400',
              'color-surface-500',
              'color-surface-600',
            ].every((k) => /hsl\(40/.test(theme.themeVars[k] || ''));
          } catch {
            return false;
          }
        })()
    ).toBe(true);
  });
  it('index.html version-busts boot-decisions.js before shell.js', () => {
    expect(
      !!index &&
        index.includes('boot-decisions.js') &&
        !/<script src="boot-decisions\.js"><\/script>/.test(index) &&
        index.indexOf('src="boot-decisions.js') < index.indexOf('src="shell.js')
    ).toBe(true);
  });
});

describe('content links', () => {
  it('theme keeps chrome red primary (BSB brand)', () => {
    expect(
      !!themeText &&
        (() => {
          try {
            return JSON.parse(themeText).themeVars['color-primary'] === 'hsl(354, 75%, 47%)';
          } catch {
            return false;
          }
        })()
    ).toBe(true);
  });
  it('theme decouples content links to darker maroon (not chrome red)', () => {
    expect(
      !!themeText &&
        (() => {
          try {
            const vars = JSON.parse(themeText).themeVars;
            return ['textColor-Link', 'textColor-Link--hover', 'textColor-Link--active'].every(
              (k) => {
                const c = parseHsl(vars[k]);
                return (
                  !!c &&
                  c.h >= 350 &&
                  c.h <= 356 &&
                  c.s >= 55 &&
                  c.s <= 70 &&
                  c.l >= 28 &&
                  c.l <= 40
                );
              }
            );
          } catch {
            return false;
          }
        })()
    ).toBe(true);
  });
  it('content link color meets WCAG AA 4.5:1 on white card + warm surface', () => {
    expect(
      !!themeText &&
        (() => {
          try {
            const vars = JSON.parse(themeText).themeVars;
            const c = parseHsl(vars['textColor-Link']);
            const surf = parseHsl(vars['color-surface']);
            const fg = hslToRgb(c.h, c.s, c.l);
            const white = [255, 255, 255];
            const surface = hslToRgb(surf.h, surf.s, surf.l);
            return contrastOf(fg, white) >= 4.5 && contrastOf(fg, surface) >= 4.5;
          } catch {
            return false;
          }
        })()
    ).toBe(true);
  });
  it('event title inherits theme link color (no per-instance override)', () => {
    expect(
      !!read('components/EventCard.xmlui') &&
        (() => {
          const card = read('components/EventCard.xmlui');
          return (
            card.includes('value="{$props.event.title}"') &&
            !/<Text[^>]*value="\{\$props\.event\.title\}"[^>]*color=/.test(card)
          );
        })()
    ).toBe(true);
  });
});

describe('sub-label contrast', () => {
  it('sub-label light token defined + meets AA on light surfaces', () => {
    expect(
      !!themeText &&
        (() => {
          const raw = toneTextColor(themeText, 'light');
          const c = parseHsl(raw);
          if (!c) return false;
          const vars = JSON.parse(themeText).themeVars;
          const surf = parseHsl(vars['color-surface']);
          if (!surf) return false;
          const fg = hslToRgb(c.h, c.s, c.l);
          const white = [255, 255, 255];
          const surface = hslToRgb(surf.h, surf.s, surf.l);
          const onWhite = contrastOf(fg, white);
          const onSurface = contrastOf(fg, surface);
          console.log(
            `  info sub-label light ${raw}: ${onWhite.toFixed(2)}:1 on white, ${onSurface.toFixed(2)}:1 on surface`
          );
          return onWhite >= 4.5 && onSurface >= 4.5;
        })()
    ).toBe(true);
  });
  it('sub-label dark token defined + meets AA on dark surface', () => {
    expect(
      !!themeText &&
        (() => {
          const raw = toneTextColor(themeText, 'dark');
          const c = parseHsl(raw);
          if (!c) return false;
          const fg = hslToRgb(c.h, c.s, c.l);
          // Engine dark tone reverses the surface scale: surface-0 resolves to the
          // const-1000 end (~9% lightness). Check against that representative
          // near-black plus pure black as the floor.
          const darkBg = hslToRgb(204, 30.3, 9);
          const black = [0, 0, 0];
          const onDark = contrastOf(fg, darkBg);
          const onBlack = contrastOf(fg, black);
          console.log(
            `  info sub-label dark ${raw}: ${onDark.toFixed(2)}:1 on dark surface, ${onBlack.toFixed(2)}:1 on black`
          );
          return onDark >= 4.5 && onBlack >= 4.5;
        })()
    ).toBe(true);
  });
});
