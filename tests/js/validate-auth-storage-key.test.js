// tests/js/validate-auth-storage-key.test.js — #248: sign out must clear the
// configured project's session, not a hardcoded one belonging to another
// project (which leaves fork users signed in after the reload).
//
// WHY static: shell.js has no unit-testable seam — bootShell() needs the full
// browser (document, fetch, IndexedDB, supabase global) and defines signOut
// only after the boot fetches resolve. This is the repo's usual fast
// file-content check for shipped JS (see validate-date-tabs.test.js). The
// click path itself is checked in a browser (see the issue's manual step).
'use strict';
import fs from 'fs';
import path from 'path';
import { describe, it, expect } from 'vitest';
import { readShipped, ROOT } from './load-shipped.js';

// Every shipped page, because the CLI used to rewrite this literal in these
// same files: index.html and test.html under xmlui/, report.html at the root.
const SHIPPED_PAGES = {
  'shell.js': readShipped('shell.js'),
  'index.html': readShipped('index.html'),
  'test.html': readShipped('test.html'),
  'report.html': fs.readFileSync(path.join(ROOT, '..', 'report.html'), 'utf8'),
};
const shell = SHIPPED_PAGES['shell.js'];

// supabase-js defaultStorageKey is `sb-<ref>-auth-token`, where <ref> is the
// first hostname label of the auth URL. Any quoted literal of that shape is a
// project-specific key baked into shared source, whatever the ref's length.
const HARDCODED_KEY = /['"]sb-[a-zA-Z0-9-]{3,}-auth-token['"]/;

function bodyOf(declaration) {
  const start = shell.indexOf(declaration);
  if (start < 0) return '';
  return shell.slice(start, shell.indexOf('\n    }', start));
}

describe('#248 sign out clears the configured project session', () => {
  for (const [name, source] of Object.entries(SHIPPED_PAGES)) {
    it(`ships no hardcoded auth storage key in ${name}`, () => {
      expect(source).not.toMatch(HARDCODED_KEY);
    });
  }

  it('derives the key from the first hostname label, as supabase-js does', () => {
    const body = bodyOf('function authStorageKey');
    expect(body).toMatch(/new URL\(SUPABASE_URL\)/);
    expect(body).toMatch(/\.hostname\.split\('\.'\)\[0\]/);
  });

  it('boot read and sign out address the same derived key', () => {
    expect(shell).toMatch(/localStorage\.getItem\(authStorageKey\(\)\)/);
    expect(bodyOf('window.signOut = function')).toMatch(
      /localStorage\.removeItem\(authStorageKey\(\)\)/
    );
  });
});
