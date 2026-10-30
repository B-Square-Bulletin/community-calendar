// tests/js/validate-auth-storage-key.test.js — #248: sign out must clear the
// configured project's session, not a hardcoded one belonging to another
// project (which leaves fork users signed in after the reload).
//
// WHY static: shell.js has no unit-testable seam — bootShell() needs the full
// browser (document, fetch, IndexedDB, supabase global) and defines signOut
// only after the boot fetches resolve. This is the repo's usual fast
// file-content check for shipped JS (see validate-date-tabs.test.js).
'use strict';
import { describe, it, expect } from 'vitest';
import { readShipped } from './load-shipped.js';

const shell = readShipped('shell.js');

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
  it('ships no hardcoded auth storage key', () => {
    expect(shell).not.toMatch(HARDCODED_KEY);
  });

  it('derives the key from the configured project URL', () => {
    expect(bodyOf('function authStorageKey')).toMatch(/new URL\(SUPABASE_URL\)/);
  });

  it('boot read and sign out address the same derived key', () => {
    expect(shell).toMatch(/localStorage\.getItem\(authStorageKey\(\)\)/);
    expect(bodyOf('window.signOut = function')).toMatch(
      /localStorage\.removeItem\(authStorageKey\(\)\)/
    );
  });
});
