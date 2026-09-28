#!/usr/bin/env bash
# One-time (re-runnable) server setup for the TechnologicalProducts scrapers.
# Works both from a git clone (<repo-root>/deploy/scraper-server/setup.sh)
# and from the extracted tarball (<repo-root>/setup.sh):   bash setup.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$HERE/../../InflationItems" ]; then
  ROOT="$(cd "$HERE/../.." && pwd)"   # git clone
else
  ROOT="$HERE"                          # tarball
fi
echo "project root: $ROOT"
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
[ -d "$ROOT/InflationItems/Codes/TechnologicalProducts" ] || { echo "scraper code not found under $ROOT"; exit 1; }
cd "$ROOT"

echo "== 1/6 install run scripts into $ROOT/bin"
if [ "$HERE" != "$ROOT" ]; then
  mkdir -p "$ROOT/bin"
  cp "$HERE"/bin/*.sh "$ROOT/bin/"
fi
# files copied from Windows may carry CRLF
sed -i 's/\r$//' "$ROOT"/bin/*.sh
chmod +x "$ROOT"/bin/*.sh
mkdir -p server_logs export InflationItems/Datas/TechnologicalProducts

echo "== 2/6 time zone -> Europe/Istanbul"
timedatectl set-timezone Europe/Istanbul
timedatectl | grep -i 'time zone'

echo "== 3/6 system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q curl ca-certificates gnupg cron util-linux procps coreutils git

echo "== 4/6 Google Chrome (only Koctas and the Beymen fallback use it)"
if ! command -v google-chrome >/dev/null 2>&1; then
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor --yes -o /usr/share/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  apt-get update -q
  apt-get install -y -q google-chrome-stable
fi
google-chrome --version

echo "== 5/6 Python 3.11 venv with pinned packages (uv)"
UV="$HOME/.local/bin/uv"
if [ ! -x "$UV" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if [ -x venv/bin/python ] && ! venv/bin/python -c 'import sys; sys.exit(sys.version_info[:2] != (3, 11))'; then
  echo "existing venv is not Python 3.11 -> moved to venv.old"
  rm -rf venv.old && mv venv venv.old
fi
[ -x venv/bin/python ] || "$UV" venv --python 3.11 venv
"$UV" pip install --python venv/bin/python -r "$HERE/requirements.txt"
venv/bin/python -c 'import requests, bs4, lxml, pandas, curl_cffi, undetected_chromedriver; print("python packages OK")'

echo "== 6/6 crontab (replaces only our block, keeps your other jobs)"
{
  crontab -l 2>/dev/null | sed '/# BEGIN inflation-scrapers/,/# END inflation-scrapers/d' || true
  sed -n '/# BEGIN inflation-scrapers/,/# END inflation-scrapers/p' "$HERE/crontab.txt" \
    | sed -e 's/\r$//' -e "s|@ROOT@|$ROOT|g"
} | crontab -
systemctl enable --now cron >/dev/null 2>&1 || true
crontab -l | sed -n '/# BEGIN inflation-scrapers/,/# END inflation-scrapers/p'

echo
echo "Setup done. Free RAM / disk:"
free -m | head -3
df -h "$ROOT" | tail -1
echo "Quick check (takes ~30 s):  bin/run_scraper.sh huawei && tail -3 log.txt"
