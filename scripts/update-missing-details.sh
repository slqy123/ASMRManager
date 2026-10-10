#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || ! -f "$1" ]]; then
    printf 'Usage: %s /path/to/data.db /path/to/download [/path/to/storage ...]\n' "$0" >&2
    exit 1
fi

database=$1
shift
roots=("$@")
for root in "${roots[@]}"; do
    if [[ ! -d "$root" ]]; then
        printf 'Directory not found: %s\n' "$root" >&2
        exit 1
    fi
done

command -v sqlite3 >/dev/null
command -v asmr >/dev/null

work_ids=$(sqlite3 -readonly "$database" "
    SELECT CASE
        WHEN id < 100000000 THEN printf('RJ%06d', id)
        WHEN id >= 300000000 AND id < 400000000 THEN printf('VJ%06d', id - 300000000)
        WHEN id >= 400000000 AND id < 500000000 THEN printf('BJ%06d', id - 400000000)
    END
    FROM asmr
    WHERE (details IS NULL OR details = 'null' OR details = '{}')
      AND (id < 100000000 OR (id >= 300000000 AND id < 500000000))
    ORDER BY id;
")

if [[ -z "$work_ids" ]]; then
    printf 'No works with missing details.\n'
    exit 0
fi

failed=0
skipped=0
first=1
while IFS= read -r work_id; do
    exists=0
    for root in "${roots[@]}"; do
        if [[ -d "$root/$work_id" ]]; then
            exists=1
            break
        fi
    done
    if (( ! exists )); then
        skipped=$((skipped + 1))
        continue
    fi
    if (( first )); then
        first=0
    else
        sleep 3
    fi
    printf '\nUpdating %s\n' "$work_id"
    if asmr dl update "$work_id"; then
        :
    else
        printf 'Update failed: %s\n' "$work_id" >&2
        failed=$((failed + 1))
    fi
done <<< "$work_ids"

printf '\nFinished; %d commands failed; %d works skipped without local directories.\n' "$failed" "$skipped"
(( failed == 0 ))
