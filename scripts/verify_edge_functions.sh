#!/usr/bin/env bash
# Verify that deployed edge functions match the repo source.
#
# How to use:
#   1. Get a Supabase Management API token:
#      https://supabase.com/dashboard/account/tokens
#   2. Run from the repo root:
#      SUPABASE_ACCESS_TOKEN=sbp_... SUPABASE_PROJECT_REF=your_ref bash scripts/verify_edge_functions.sh
#
# What it does:
#   - Fetches the deployed source for each edge function via the Management API
#   - Diffs it against the repo source in supabase/functions/*/index.ts
#   - Reports matches, differences, and missing (undeployed) functions
#   - Flags if verify_jwt is ON (it should usually be OFF for these functions)
#
# Requirements: curl, diff, jq

set -euo pipefail

: "${SUPABASE_ACCESS_TOKEN:?Set SUPABASE_ACCESS_TOKEN (Management API token from supabase.com/dashboard/account/tokens)}"
: "${SUPABASE_PROJECT_REF:?Set SUPABASE_PROJECT_REF (your Supabase project ref)}"

API="https://api.supabase.com/v1/projects/${SUPABASE_PROJECT_REF}/functions"
TMPDIR_BASE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

# Discover functions from the repo
FUNCTIONS=()
for dir in supabase/functions/*/; do
  if [[ -f "${dir}index.ts" ]]; then
    FUNCTIONS+=("$(basename "$dir")")
  fi
done

if [[ ${#FUNCTIONS[@]} -eq 0 ]]; then
  echo "No edge functions found in supabase/functions/*/index.ts"
  exit 1
fi

pass=0
fail=0
missing=0

for fn in "${FUNCTIONS[@]}"; do
  repo_file="supabase/functions/${fn}/index.ts"
  echo -n "${fn}: "

  # Fetch deployed function metadata + source
  resp=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer ${SUPABASE_ACCESS_TOKEN}" \
    "${API}/${fn}")

  http_code=$(echo "$resp" | tail -1)
  body=$(echo "$resp" | sed '$d')

  if [[ "$http_code" == "404" ]]; then
    echo "NOT DEPLOYED"
    echo "   Fix: supabase functions deploy ${fn} --no-verify-jwt"
    ((missing++)) || true
    continue
  fi

  if [[ "$http_code" != "200" ]]; then
    echo "API error (HTTP ${http_code})"
    echo "   ${body}" | head -3
    ((fail++)) || true
    continue
  fi

  # Extract source from the files array
  deployed_source=$(echo "$body" | jq -r '.files[] | select(.name == "index.ts") | .content')
  deployed_file="${TMPDIR_BASE}/${fn}.deployed.ts"
  echo "$deployed_source" > "$deployed_file"

  # Also check verify_jwt setting
  verify_jwt=$(echo "$body" | jq -r '.verify_jwt')
  version=$(echo "$body" | jq -r '.version')

  # Compare
  if diff -q "$repo_file" "$deployed_file" > /dev/null 2>&1; then
    jwt_warn=""
    if [[ "$verify_jwt" == "true" ]]; then
      jwt_warn=" !! verify_jwt is ON (should probably be OFF)"
    fi
    echo "OK (v${version})${jwt_warn}"
    ((pass++)) || true
  else
    echo "DIFFERS from repo (deployed v${version})"
    if [[ "$verify_jwt" == "true" ]]; then
      echo "   !! verify_jwt is ON (should probably be OFF)"
    fi
    echo "   Diff (deployed vs repo):"
    diff --unified=3 "$deployed_file" "$repo_file" | head -30 | sed 's/^/   /'
    echo "   Fix: supabase functions deploy ${fn} --no-verify-jwt"
    ((fail++)) || true
  fi
done

echo ""
echo "========================================"
echo "Results: ${pass} OK, ${fail} differ, ${missing} not deployed"
if [[ $fail -gt 0 || $missing -gt 0 ]]; then
  echo ""
  echo "To deploy all functions:"
  echo "  supabase link --project-ref \${SUPABASE_PROJECT_REF}"
  for fn in "${FUNCTIONS[@]}"; do
    echo "  supabase functions deploy ${fn} --no-verify-jwt"
  done
  echo ""
  echo "After deploying, check Supabase Dashboard > Edge Functions"
  echo "and confirm 'Require JWT' is OFF for each function."
fi
echo "========================================"
