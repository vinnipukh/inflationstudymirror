#!/usr/bin/env bash
# Daily housekeeping. Never touches the scraped CSVs: those are research data,
# you download and delete them yourself (see export_data.sh).
set -u
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"  # <repo-root>: bin/ lives directly under it
STATUS_LOG="$ROOT/log.txt"

# per-run logs older than 30 days
find "$ROOT/server_logs" -type f -name '*.log' -mtime +30 -delete 2>/dev/null

# keep log.txt small (last 5000 lines once it passes 5 MB)
if [ -f "$STATUS_LOG" ] && [ "$(stat -c %s "$STATUS_LOG")" -gt 5242880 ]; then
  tail -n 5000 "$STATUS_LOG" > "$STATUS_LOG.tmp" && mv "$STATUS_LOG.tmp" "$STATUS_LOG"
fi

# Samsung resume checkpoints, half-written CSVs from killed runs
find "$ROOT/InflationItems/Codes/TechnologicalProducts/Samsung/checkpoints" -type f -mtime +7 -delete 2>/dev/null
find "$ROOT/InflationItems/Datas/TechnologicalProducts" -type f -name '*.part' -mtime +2 -delete 2>/dev/null

# temp Chrome profiles left by a crash (only when no scraper is running)
if ! pgrep -f 'chrome' >/dev/null; then
  find /tmp -maxdepth 1 \( -name 'koctas_chrome_*' -o -name 'beymen_chrome_*' -o -name '.org.chromium.*' \) \
       -mmin +720 -exec rm -rf {} + 2>/dev/null
fi

# pip / apt caches
rm -rf "${HOME:-/root}/.cache/pip" 2>/dev/null
apt-get clean 2>/dev/null

free_mb=$(df -Pm "$ROOT" | awk 'NR==2 {print $4}')
data_mb=$(du -sm "$ROOT/InflationItems/Datas" 2>/dev/null | awk '{print $1}')
echo "$(date '+%F %T') [cleanup] free ${free_mb} MB, data ${data_mb:-0} MB" >> "$STATUS_LOG"
