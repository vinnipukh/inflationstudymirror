#!/usr/bin/env bash
# One-time (re-runnable) server setup for the TechnologicalProducts scrapers.
# Run as root from /root/scraper:   bash setup.sh
set -euo pipefail

ROOT=/root/scraper
cd "$ROOT"
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }

echo "== 1/6 normalise files copied from Windows"
sed -i 's/\r$//' setup.sh crontab.txt requirements.txt bin/*.sh
chmod +x bin/*.sh
mkdir -p logs export InflationItems/Datas

echo "== 2/6 time zone -> Europe/Istanbul"
timedatectl set-timezone Europe/Istanbul
timedatectl | grep -i 'time zone'

echo "== 3/6 system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q curl ca-certificates gnupg cron util-linux procps coreutils

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
if [ ! -x /root/.local/bin/uv ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV=/root/.local/bin/uv
if [ -x venv/bin/python ] && ! venv/bin/python -c 'import sys; sys.exit(sys.version_info[:2] != (3, 11))'; then
  echo "existing venv is not Python 3.11 -> moved to venv.old"
  rm -rf venv.old && mv venv venv.old
fi
[ -x venv/bin/python ] || "$UV" venv --python 3.11 venv
"$UV" pip install --python venv/bin/python -r requirements.txt
venv/bin/python -c 'import requests, bs4, lxml, pandas, curl_cffi, undetected_chromedriver; print("python packages OK")'

echo "== 6/6 crontab (replaces only our block, keeps your other jobs)"
{
  crontab -l 2>/dev/null | sed '/# BEGIN inflation-scrapers/,/# END inflation-scrapers/d' || true
  sed -n '/# BEGIN inflation-scrapers/,/# END inflation-scrapers/p' crontab.txt
} | crontab -
systemctl enable --now cron >/dev/null 2>&1 || true
crontab -l | sed -n '/# BEGIN inflation-scrapers/,/# END inflation-scrapers/p'

echo
echo "Setup done. Free RAM / disk:"
free -m | head -3
df -h "$ROOT" | tail -1
echo "Quick check (takes ~30 s):  bin/run_scraper.sh huawei && tail -3 log.txt"
