#!/usr/bin/env bash
# Git merge driver that filters cities based on ENABLED_CITIES environment variable
# Usage: Called automatically by Git during merge via .gitattributes
# Arguments: %O (base) %A (ours) %B (theirs) %P (path)

set -euo pipefail

# Read which cities this fork wants to keep from environment
if [[ -z "${ENABLED_CITIES:-}" ]]; then
    echo "Error: ENABLED_CITIES environment variable not set" >&2
    echo "Add to .envrc in the repo root:" >&2
    echo "  export ENABLED_CITIES='bloomington'" >&2
    echo "Then run: source .envrc  (or 'direnv allow .' if using direnv)" >&2
    exit 1
fi

# Check for jq (needed for JSON filtering)
if ! command -v jq &> /dev/null; then
    echo "Error: jq is not installed" >&2
    echo "Install with: brew install jq  (macOS) or apt-get install jq  (Linux)" >&2
    exit 1
fi

# Extract arguments
BASE="$1"
OURS="$2"
THEIRS="$3"
PATH_NAME="$4"

# Handle cities.json specially - filter to only enabled cities
if [[ "$PATH_NAME" == "cities.json" ]]; then
    # Convert comma-separated ENABLED_CITIES to jq object filter
    # Example: "bloomington,bedford" becomes '{bloomington: .bloomington, bedford: .bedford}'
    FILTER=$(echo "$ENABLED_CITIES" | awk -F',' '{
        printf "{"
        for(i=1; i<=NF; i++) {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)  # trim whitespace
            if(i>1) printf ", "
            printf "%s: .%s", $i, $i
        }
        printf "}"
    }')
    
    # Apply filter to our version (which may already have upstream cities merged in)
    # Write filtered result back to OURS
    if jq "$FILTER" "$OURS" > "$OURS.tmp" 2>/dev/null; then
        mv "$OURS.tmp" "$OURS"
        exit 0
    else
        echo "Error: Failed to filter cities.json with jq" >&2
        echo "Filter expression: $FILTER" >&2
        rm -f "$OURS.tmp"
        exit 1
    fi
fi

# For all other files (cities/** contents), keep ours unchanged
# Git has already placed our version in OURS, we just signal success
exit 0
