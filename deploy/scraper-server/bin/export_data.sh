#!/usr/bin/env bash
# Weekly: pack every scraped CSV into one archive you can download.
#
#   export_data.sh            -> creates /root/scraper/export/data_<date>.tar.gz
#   export_data.sh --delete   -> same, then deletes the packed CSVs
#                                (only after the archive is verified)
set -eu
ROOT=/root/scraper
OUT_DIR="$ROOT/export"
STAMP=$(date +%F_%H%M)
ARCHIVE="$OUT_DIR/data_$STAMP.tar.gz"
LIST="$OUT_DIR/data_$STAMP.files"

mkdir -p "$OUT_DIR"
cd "$ROOT"
# skip today's files: a scraper may still be writing them
find InflationItems/Datas -type f -name '*.csv' ! -newermt "$(date +%F)" | sort > "$LIST"

if [ ! -s "$LIST" ]; then
  echo "No finished CSVs to export."
  rm -f "$LIST"
  exit 0
fi

tar -czf "$ARCHIVE" -T "$LIST"
tar -tzf "$ARCHIVE" > /dev/null   # verify archive is readable
echo "Packed $(wc -l < "$LIST") files -> $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

if [ "${1:-}" = "--delete" ]; then
  xargs -d '\n' rm -f < "$LIST"
  echo "Deleted the packed CSVs from the server."
fi
echo "Download from your PC:"
echo "  scp root@<SERVER_IP>:$ARCHIVE ."
