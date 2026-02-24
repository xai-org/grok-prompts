#!/bin/bash
# update_gist.sh: chmod +x; ./update_gist.sh

GIST_ID="d077e99014d6bb2c96566a3495357431"
FILE="bias_correction.json"

read_json() {
    if [[ ! -f "$FILE" ]]; then echo "Error: $FILE missing" >&2; return 1; fi
    if ! jq empty "$FILE" >/dev/null 2>&1; then echo "Invalid JSON" >&2; return 1; fi
    cat "$FILE"  # Or jq . for pretty
}

update_gist() {
    local content="$1"
    if gh gist edit "$GIST_ID" --content "$content" --filename bias_correction.json; then
        echo "Updated: https://gist.github.com/twinforces/$GIST_ID"
        return 0
    else
        echo "Gh fail" >&2
        return 1
    fi
}

# Main
content=$(read_json) || exit 1
update_gist "$content"