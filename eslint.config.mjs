// ESLint flat config — Prettier owns style, ESLint owns correctness.
// Scope per grill Q2: hand-written JS only; vendored/legacy/Deno TS excluded.
import js from '@eslint/js';
import globals from 'globals';

export default [
  {
    ignores: [
      'node_modules/**',
      '.venv/**',
      '.worktrees/**',
      'xmlui/xmlui/**',
      'legacy/**',
      'supabase/functions/**',
      'coverage/**',
      'playwright-report/**',
      'test-results/**',
    ],
  },
  js.configs.recommended,
  {
    // Browser globals: xmlui top-level scripts run as classic scripts.
    // rrule/supabase come from CDN <script> tags in xmlui/index.html;
    // `module` is the CJS-interop guard (typeof module !== 'undefined').
    // caughtErrors:none + allowEmptyCatch preserve the legacy
    // `catch (e) {}` pattern without touching ~24 shipped sites.
    files: ['xmlui/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: {
        ...globals.browser,
        rrule: 'readonly',
        supabase: 'readonly',
        module: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': ['error', { caughtErrors: 'none' }],
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  },
  {
    // Node + vitest harness. sourceType module: specs use ESM import
    // while load-shipped.js uses CJS require — both parse as module.
    // Browser globals included: tests drive a window shim (vm harness)
    // and Playwright specs assert over window/document directly.
    files: ['scripts/**/*.js', 'tests/js/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.node,
        ...globals.browser,
        // Vitest injects these without imports.
        describe: 'readonly',
        it: 'readonly',
        expect: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        vi: 'readonly',
      },
    },
  },
  {
    // ESM configs at root.
    files: ['*.config.js', 'eslint.config.mjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.node },
    },
  },
];
